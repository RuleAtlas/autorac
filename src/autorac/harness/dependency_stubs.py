"""Shared planning and materialization for canonical dependency stubs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ResolvedDefinedTerm:
    """One canonical legal term resolved to an import target."""

    term: str
    import_target: str
    symbol: str
    citation: str
    entity: str
    period: str
    dtype: str
    label: str


_REGISTERED_DEFINED_TERM_PATTERNS: tuple[tuple[re.Pattern[str], ResolvedDefinedTerm], ...] = (
    (
        re.compile(r"\bmixed-age couple\b", re.IGNORECASE),
        ResolvedDefinedTerm(
            term="mixed-age couple",
            import_target="legislation/ukpga/2002/16/section/3ZA/3#is_member_of_mixed_age_couple",
            symbol="is_member_of_mixed_age_couple",
            citation="State Pension Credit Act 2002 section 3ZA(3)",
            entity="Person",
            period="Day",
            dtype="Boolean",
            label=(
                "`mixed-age couple` -> import "
                "`legislation/ukpga/2002/16/section/3ZA/3#is_member_of_mixed_age_couple` "
                "(State Pension Credit Act 2002 section 3ZA(3))"
            ),
        ),
    ),
)

_REGISTERED_STUBS_BY_KEY = {
    (term.import_target.split("#", 1)[0], term.symbol): term
    for _, term in _REGISTERED_DEFINED_TERM_PATTERNS
}


def resolve_defined_terms_from_text(text: str) -> list[ResolvedDefinedTerm]:
    """Resolve registered legally-defined terms mentioned in source text."""
    resolved: list[ResolvedDefinedTerm] = []
    for pattern, term in _REGISTERED_DEFINED_TERM_PATTERNS:
        if pattern.search(text) and term not in resolved:
            resolved.append(term)
    return resolved


def find_registered_stub_specs(
    import_path: str,
    symbol_names: Sequence[str],
) -> list[ResolvedDefinedTerm]:
    """Return registered canonical stub specs for one unresolved import target."""
    normalized_import = import_path.strip().strip('"').strip("'").removesuffix(".rac")
    specs: list[ResolvedDefinedTerm] = []
    for symbol in symbol_names:
        spec = _REGISTERED_STUBS_BY_KEY.get((normalized_import, symbol))
        if spec is None:
            return []
        specs.append(spec)
    return specs


def import_target_to_relative_rac_path(import_target: str) -> Path:
    """Convert an import target like legislation/...#name into a .rac path."""
    normalized = import_target.strip().strip('"').strip("'").split("#", 1)[0]
    if normalized.endswith(".rac"):
        return Path(normalized)
    return Path(f"{normalized}.rac")


def build_registered_stub_content(specs: Sequence[ResolvedDefinedTerm]) -> str:
    """Return deterministic stub file content for one registered dependency file."""
    if not specs:
        raise ValueError("At least one stub spec is required")

    base_paths = {
        spec.import_target.split("#", 1)[0].removesuffix(".rac") for spec in specs
    }
    if len(base_paths) != 1:
        raise ValueError("All registered stub specs must belong to the same target file")

    if len(specs) == 1:
        header = (
            f'"""\nCanonical definition stub for `{specs[0].term}`.\n'
            f"Resolved to {specs[0].citation}.\n"
            '"""\n\n'
        )
    else:
        citations = ", ".join(sorted({spec.citation for spec in specs}))
        header = (
            '"""\nCanonical definition stubs.\n'
            f"Resolved to {citations}.\n"
            '"""\n\n'
        )

    blocks = []
    for spec in specs:
        blocks.append(
            "\n".join(
                [
                    f"{spec.symbol}:",
                    f"    stub_for: {spec.import_target}",
                    f"    entity: {spec.entity}",
                    f"    period: {spec.period}",
                    f"    dtype: {spec.dtype}",
                ]
            )
        )

    return header + "status: stub\n\n" + "\n\n".join(blocks) + "\n"


def materialize_registered_stub(
    root: Path,
    specs: Sequence[ResolvedDefinedTerm],
    *,
    prefix: Path | None = None,
) -> Path:
    """Write one deterministic canonical stub file under the given root."""
    if not specs:
        raise ValueError("At least one stub spec is required")

    relative_path = import_target_to_relative_rac_path(specs[0].import_target)
    target = root / prefix / relative_path if prefix is not None else root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_registered_stub_content(specs))
    return target
