"""Tests for encoding context injection in Orchestrator prompts."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autorac.harness.orchestrator import Backend, Orchestrator, SubsectionTask


@pytest.fixture
def cli_orchestrator(temp_db_path):
    """CLI-backend orchestrator with a temp DB."""
    return Orchestrator(backend=Backend.CLI, db_path=temp_db_path)


@pytest.fixture
def api_orchestrator():
    """API-backend orchestrator (no DB needed for this test)."""
    return Orchestrator(backend=Backend.API, api_key="test-key")


class TestBuildContextSection:
    def test_cli_backend_returns_context(self, cli_orchestrator):
        result = cli_orchestrator._build_context_section()
        assert "Past encoding reference" in result
        assert "encoding_runs" in result
        assert "sqlite3" in result
        assert ".rac files" in result

    def test_cli_backend_includes_db_path(self, cli_orchestrator):
        result = cli_orchestrator._build_context_section()
        assert str(cli_orchestrator.encoding_db.db_path) in result

    def test_api_backend_returns_empty(self, api_orchestrator):
        result = api_orchestrator._build_context_section()
        assert result == ""

    def test_cli_no_db_uses_default_path(self):
        orch = Orchestrator(backend=Backend.CLI)
        result = orch._build_context_section()
        assert "encodings.db" in result
        assert "Past encoding reference" in result


class TestContextInPrompts:
    def test_subsection_prompt_includes_context_cli(self, cli_orchestrator):
        task = SubsectionTask(
            subsection_id="(a)",
            title="Allowance of credit",
            file_name="a.rac",
            dependencies=[],
        )
        prompt = cli_orchestrator._build_subsection_prompt(
            task=task,
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test statute text",
        )
        assert "Past encoding reference" in prompt

    def test_fallback_prompt_includes_context_cli(self, cli_orchestrator):
        prompt = cli_orchestrator._build_fallback_encode_prompt(
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test statute text",
        )
        assert "Past encoding reference" in prompt

    def test_subsection_prompt_no_context_api(self, api_orchestrator):
        task = SubsectionTask(
            subsection_id="(a)",
            title="Allowance of credit",
            file_name="a.rac",
            dependencies=[],
        )
        prompt = api_orchestrator._build_subsection_prompt(
            task=task,
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test statute text",
        )
        assert "Past encoding reference" not in prompt

    def test_fallback_prompt_no_context_api(self, api_orchestrator):
        prompt = api_orchestrator._build_fallback_encode_prompt(
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test statute text",
        )
        assert "Past encoding reference" not in prompt


class TestCriticalRulesInPrompts:
    """Tests that the 4 P0 rules appear in both prompt builders."""

    def _make_task(self):
        return SubsectionTask(
            subsection_id="(a)",
            title="Allowance of credit",
            file_name="a.rac",
            dependencies=[],
        )

    def test_subsection_prompt_has_compile_preflight(self, cli_orchestrator):
        prompt = cli_orchestrator._build_subsection_prompt(
            task=self._make_task(),
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
        )
        assert "COMPILE PRE-FLIGHT" in prompt
        assert "autorac test" in prompt

    def test_subsection_prompt_has_write_tests(self, cli_orchestrator):
        prompt = cli_orchestrator._build_subsection_prompt(
            task=self._make_task(),
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
        )
        assert "WRITE TESTS" in prompt
        assert ".rac.test" in prompt

    def test_subsection_prompt_has_parent_imports(self, cli_orchestrator):
        prompt = cli_orchestrator._build_subsection_prompt(
            task=self._make_task(),
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
        )
        assert "PARENT IMPORTS FROM CHILDREN" in prompt
        assert "from ./{child}" in prompt

    def test_subsection_prompt_has_indexed_by(self, cli_orchestrator):
        prompt = cli_orchestrator._build_subsection_prompt(
            task=self._make_task(),
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
        )
        assert "INDEXED_BY FOR INFLATION" in prompt
        assert "indexed_by:" in prompt

    def test_fallback_prompt_has_compile_preflight(self, cli_orchestrator):
        prompt = cli_orchestrator._build_fallback_encode_prompt(
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test text",
        )
        assert "COMPILE PRE-FLIGHT" in prompt
        assert "autorac test" in prompt

    def test_fallback_prompt_has_write_tests(self, cli_orchestrator):
        prompt = cli_orchestrator._build_fallback_encode_prompt(
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test text",
        )
        assert "WRITE TESTS" in prompt
        assert ".rac.test" in prompt

    def test_fallback_prompt_has_parent_imports(self, cli_orchestrator):
        prompt = cli_orchestrator._build_fallback_encode_prompt(
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test text",
        )
        assert "PARENT IMPORTS FROM CHILDREN" in prompt

    def test_fallback_prompt_has_indexed_by(self, cli_orchestrator):
        prompt = cli_orchestrator._build_fallback_encode_prompt(
            citation="26 USC 21",
            output_path=Path("/tmp/test"),
            statute_text="Test text",
        )
        assert "INDEXED_BY FOR INFLATION" in prompt
        assert "indexed_by:" in prompt


class TestLogAgentRunNoTruncation:
    """Tests that _log_agent_run does not truncate prompt or result content."""

    def test_long_prompt_not_truncated(self, cli_orchestrator):
        """Prompts longer than 2000 chars should be stored in full."""
        from autorac.harness.orchestrator import AgentRun, Phase

        long_prompt = "x" * 5000
        agent_run = AgentRun(
            agent_type="encoder",
            prompt=long_prompt,
            phase=Phase.ENCODING,
            result="short result",
        )

        cli_orchestrator.encoding_db.start_session(session_id="trunc-test")
        cli_orchestrator._log_agent_run("trunc-test", agent_run)

        events = cli_orchestrator.encoding_db.get_session_events("trunc-test")
        start_event = [e for e in events if e.event_type == "agent_start"][0]
        assert len(start_event.content) == 5000

    def test_long_result_not_truncated(self, cli_orchestrator):
        """Results longer than 2000 chars should be stored in full."""
        from autorac.harness.orchestrator import AgentRun, Phase

        long_result = "y" * 5000
        agent_run = AgentRun(
            agent_type="rac_reviewer",
            prompt="short prompt",
            phase=Phase.REVIEW,
            result=long_result,
        )

        cli_orchestrator.encoding_db.start_session(session_id="trunc-test-2")
        cli_orchestrator._log_agent_run("trunc-test-2", agent_run)

        events = cli_orchestrator.encoding_db.get_session_events("trunc-test-2")
        end_event = [e for e in events if e.event_type == "agent_end"][0]
        assert len(end_event.content) == 5000
