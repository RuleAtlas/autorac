#!/usr/bin/env python3
"""Run one mutate-score-keep iteration for the autoresearch pilot."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _default_output_root() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("/tmp") / f"autorac-autoresearch-iteration-{timestamp}"


def _run_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def main() -> int:
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))

    from autorac.harness.autoresearch_pilot import (
        autorac_repo_root,
        build_mutation_prompt,
        extract_autoresearch_score,
        load_autoresearch_report,
        pilot_editable_paths,
        program_path,
        shared_legislation_cache_root,
        should_keep_candidate,
    )

    parser = argparse.ArgumentParser(
        description=(
            "Run one real autoresearch iteration: mutate the prompt surface, "
            "score the candidate, and keep or discard it."
        )
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_default_output_root(),
        help="Directory for baseline, candidate, and decision artifacts",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        default=None,
        help="Existing autoresearch-pilot-report.json to use as the baseline",
    )
    parser.add_argument(
        "--gpt-backend",
        choices=["codex", "openai"],
        default=None,
        help="Override GPT runner backend for local-vs-API eval execution",
    )
    parser.add_argument(
        "--shared-legislation-cache-root",
        type=Path,
        default=None,
        help=(
            "Persistent directory for reusing legislation.gov.uk payloads across "
            "pilot runs. Defaults to AUTORAC_SHARED_LEGISLATION_CACHE or "
            "~/tmp/autorac-shared-legislation-cache."
        ),
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4",
        help="Model to use for the prompt-mutation step",
    )
    parser.add_argument(
        "--keep-on-tie",
        action="store_true",
        help="Keep the candidate if the score ties the baseline exactly",
    )
    args = parser.parse_args()

    repo_root = autorac_repo_root()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    legislation_cache_root = (
        args.shared_legislation_cache_root.resolve()
        if args.shared_legislation_cache_root is not None
        else shared_legislation_cache_root()
    )

    env = os.environ.copy()
    pythonpath_entries = [str(repo_root / "src")]
    if env.get("PYTHONPATH"):
        pythonpath_entries.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
    if args.gpt_backend:
        env["AUTORAC_GPT_BACKEND"] = args.gpt_backend

    editable_paths = pilot_editable_paths(repo_root)
    if len(editable_paths) != 1:
        raise SystemExit(
            f"Expected exactly one editable path, found {len(editable_paths)}"
        )
    editable_path = editable_paths[0]
    editable_relpath = editable_path.relative_to(repo_root)
    editable_before = editable_path.read_text()

    baseline_report_path = (
        args.baseline_report.resolve()
        if args.baseline_report is not None
        else output_root / "baseline" / "autoresearch-pilot-report.json"
    )
    if not baseline_report_path.exists():
        baseline_root = baseline_report_path.parent
        baseline_root.mkdir(parents=True, exist_ok=True)
        baseline_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "run_autoresearch_pilot.py"),
            "--output-root",
            str(baseline_root),
            "--shared-legislation-cache-root",
            str(legislation_cache_root),
        ]
        if args.gpt_backend:
            baseline_cmd.extend(["--gpt-backend", args.gpt_backend])
        baseline_process = _run_cmd(baseline_cmd, cwd=repo_root, env=env)
        (baseline_root / "run.stdout").write_text(baseline_process.stdout)
        (baseline_root / "run.stderr").write_text(baseline_process.stderr)
        if baseline_process.returncode != 0:
            raise SystemExit(
                f"Baseline pilot failed with exit code {baseline_process.returncode}"
            )

    baseline_report = load_autoresearch_report(baseline_report_path)
    baseline_score = extract_autoresearch_score(baseline_report)

    mutation_workspace = output_root / "mutation-workspace"
    mutation_workspace.mkdir(parents=True, exist_ok=True)
    mutation_editable_path = mutation_workspace / editable_relpath
    mutation_editable_path.parent.mkdir(parents=True, exist_ok=True)
    mutation_editable_path.write_text(editable_before)
    mutation_program_path = mutation_workspace / "program.md"
    shutil.copy2(program_path(repo_root), mutation_program_path)
    mutation_baseline_report_path = mutation_workspace / "baseline-report.json"
    shutil.copy2(baseline_report_path, mutation_baseline_report_path)
    mutation_last_message_path = mutation_workspace / ".codex-last-message.txt"

    mutation_prompt = build_mutation_prompt(
        editable_relpath=str(editable_relpath),
        program_relpath=mutation_program_path.relative_to(mutation_workspace).as_posix(),
        baseline_report_relpath=mutation_baseline_report_path.relative_to(
            mutation_workspace
        ).as_posix(),
    )
    mutation_cmd = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--model",
        args.model,
        "--cd",
        str(mutation_workspace),
        "--output-last-message",
        str(mutation_last_message_path),
        mutation_prompt,
    ]
    mutation_process = _run_cmd(mutation_cmd, cwd=repo_root, env=env)
    (output_root / "mutation.stdout").write_text(mutation_process.stdout)
    (output_root / "mutation.stderr").write_text(mutation_process.stderr)
    if mutation_process.returncode != 0:
        raise SystemExit(
            f"Mutation step failed with exit code {mutation_process.returncode}"
        )

    editable_after = mutation_editable_path.read_text()
    decision: dict[str, object] = {
        "program": str(program_path(repo_root)),
        "editable_file": str(editable_path),
        "baseline_report": str(baseline_report_path),
        "baseline_score": baseline_score,
        "mutation_workspace": str(mutation_workspace),
        "mutation_last_message": str(mutation_last_message_path),
        "mutation_changed_file": editable_after != editable_before,
        "candidate_kept": False,
    }

    if editable_after == editable_before:
        decision["reason"] = "mutation_left_file_unchanged"
        decision_path = output_root / "decision.json"
        decision_path.write_text(json.dumps(decision, indent=2) + "\n")
        print(json.dumps(decision, indent=2))
        return 0

    candidate_snapshot_path = output_root / "candidate-eval_prompt_surface.py"
    candidate_snapshot_path.write_text(editable_after)

    candidate_report_path = output_root / "candidate" / "autoresearch-pilot-report.json"
    candidate_root = candidate_report_path.parent
    candidate_root.mkdir(parents=True, exist_ok=True)

    editable_path.write_text(editable_after)
    try:
        candidate_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "run_autoresearch_pilot.py"),
            "--output-root",
            str(candidate_root),
            "--shared-legislation-cache-root",
            str(legislation_cache_root),
        ]
        if args.gpt_backend:
            candidate_cmd.extend(["--gpt-backend", args.gpt_backend])
        candidate_process = _run_cmd(candidate_cmd, cwd=repo_root, env=env)
        (candidate_root / "run.stdout").write_text(candidate_process.stdout)
        (candidate_root / "run.stderr").write_text(candidate_process.stderr)
        if candidate_process.returncode != 0:
            raise SystemExit(
                f"Candidate pilot failed with exit code {candidate_process.returncode}"
            )

        candidate_report = load_autoresearch_report(candidate_report_path)
        candidate_score = extract_autoresearch_score(candidate_report)
        keep = should_keep_candidate(
            baseline_score,
            candidate_score,
            keep_on_tie=args.keep_on_tie,
        )
        decision.update(
            {
                "candidate_report": str(candidate_report_path),
                "candidate_score": candidate_score,
                "candidate_kept": keep,
                "reason": "candidate_improved_score" if keep else "candidate_did_not_improve",
            }
        )
        if not keep:
            editable_path.write_text(editable_before)
    finally:
        if not decision["candidate_kept"] and editable_path.read_text() != editable_before:
            editable_path.write_text(editable_before)

    decision_path = output_root / "decision.json"
    decision_path.write_text(json.dumps(decision, indent=2) + "\n")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
