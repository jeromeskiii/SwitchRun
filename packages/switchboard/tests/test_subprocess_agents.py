# Copyright 2026 Human Systems. MIT License.
"""Integration tests for subprocess-based agents.

These tests verify the ABI contract between Python callers and the
subprocess targets (MasterAlpha CLI, Nexus router CLI). They use
a known offline/mock invocation so no live LLM or running service
is required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ECOSYSTEM_ROOT = Path(__file__).resolve().parents[3]
VENV_PYTHON = str(Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python3")
SWITCHBOARD_OFFLINE_ENV = {**os.environ, "SWITCHBOARD_OFFLINE": "1"}


# ── MasterAlpha subprocess ABI ────────────────────────────────────────────────

class TestMasterAlphaSubprocessABI:
    """Verify that MasterAlpha CLI emits expected JSON structure.

    Uses --sims 3 to keep the test fast and offline-safe (simulated executor).
    """

    MASTER_ALPHA_DIR = ECOSYSTEM_ROOT / "MasterAlpha"
    CLI_MODULE = "apps.cli.main"

    @pytest.fixture(autouse=True)
    def skip_if_no_venv(self):
        if not Path(VENV_PYTHON).exists():
            pytest.skip("Shared venv not found; skipping subprocess ABI test")

    def _run_cli(self, prompt: str, sims: int = 3) -> subprocess.CompletedProcess:
        return subprocess.run(
            [VENV_PYTHON, "-m", self.CLI_MODULE, prompt, "--sims", str(sims)],
            capture_output=True,
            text=True,
            cwd=str(self.MASTER_ALPHA_DIR),
            env=SWITCHBOARD_OFFLINE_ENV,
            timeout=30,
        )

    def test_cli_exits_zero(self):
        result = self._run_cli("health check")
        assert result.returncode == 0, f"stderr: {result.stderr[:500]}"

    def test_cli_emits_json(self):
        result = self._run_cli("analyze this")
        assert result.returncode == 0
        stdout = result.stdout.strip()
        assert stdout, "CLI produced no stdout"
        data = json.loads(stdout)
        assert isinstance(data, dict)

    def test_json_has_selected_action(self):
        result = self._run_cli("write python code")
        data = json.loads(result.stdout.strip())
        assert "selected_action" in data, f"Missing selected_action. Keys: {list(data.keys())}"

    def test_json_has_reward(self):
        result = self._run_cli("data analysis task")
        data = json.loads(result.stdout.strip())
        assert "reward" in data or "metrics" in data, \
            f"Missing reward/metrics. Keys: {list(data.keys())}"

    def test_json_has_output_field(self):
        result = self._run_cli("implement a feature")
        data = json.loads(result.stdout.strip())
        assert "output" in data, f"Missing output field. Keys: {list(data.keys())}"


# ── NexusAgent subprocess ABI ─────────────────────────────────────────────────

class TestNexusAgentSubprocessABI:
    """Verify that Nexus router CLI responds to known commands.

    Tests are gated on the dist/ bundle being built and nexus_core being reachable.
    We only test the CLI layer (list-backends / status) which requires no live server.
    """

    NEXUS_ROUTER_DIST = ECOSYSTEM_ROOT / "Nexus" / "router" / "dist" / "cli.js"

    @pytest.fixture(autouse=True)
    def skip_if_no_dist(self):
        if not self.NEXUS_ROUTER_DIST.exists():
            pytest.skip("Nexus router dist not built; skipping subprocess ABI test")

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["node", str(self.NEXUS_ROUTER_DIST), *args],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "NEXUS_CORE_URL": "http://localhost:9999"},  # deliberately unreachable
        )

    def test_cli_backends_command_exits(self):
        """CLI 'backends' command should not crash regardless of server availability."""
        result = self._run_cli("backends")
        # Accept either 0 (all good) or any non-crash exit code
        assert result.returncode in (0, 1), \
            f"Unexpected exit code {result.returncode}. stderr: {result.stderr[:300]}"

    def test_cli_status_command_exits(self):
        result = self._run_cli("status")
        assert result.returncode in (0, 1)

    def test_cli_select_command_produces_output(self):
        result = self._run_cli("select", "--task", "write code", "--framework", "coder")
        # May fail due to unreachable server, but must not segfault
        assert result.returncode in (0, 1)
        # Output should be non-empty (error message or JSON)
        assert result.stdout.strip() or result.stderr.strip()


# ── MasterAlphaAgent unit-level mock test ────────────────────────────────────

class TestMasterAlphaAgentUnit:
    """Unit tests for MasterAlphaAgent that mock subprocess.run."""

    def _make_agent(self):
        from switchboard.agents import MasterAlphaAgent
        return MasterAlphaAgent()

    def test_successful_json_output_parsed(self):
        fake_output = json.dumps({
            "task": "test",
            "selected_action": "llm:claude-sonnet",
            "reward": 0.75,
            "output": "Done",
            "metrics": {"quality": 0.8},
        })
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = fake_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            agent = self._make_agent()
            result = agent.run("test task")
            assert result.success
            assert "Done" in result.output or result.output

    def test_nonzero_exit_produces_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: something failed"

        with patch("subprocess.run", return_value=mock_result):
            agent = self._make_agent()
            result = agent.run("test task")
            assert not result.success
            assert result.error is not None

    def test_malformed_json_does_not_crash(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json {"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            agent = self._make_agent()
            # Should not raise; returns either success with raw output or graceful failure
            result = agent.run("test task")
            assert result is not None

    def test_timeout_produces_failure(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 120)):
            agent = self._make_agent()
            result = agent.run("test task")
            assert not result.success
            assert result.error is not None
