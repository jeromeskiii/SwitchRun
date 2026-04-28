import subprocess
import sys
from pathlib import Path

from switchboard import Router, execute, route


PROJECT_PARENT = Path(__file__).resolve().parents[3]


def test_public_api_exports_work_for_local_imports():
    assert route("write python code").plan.steps[0].agent_name == "coding"
    assert (
        Router().route("document the API").plan.steps[0].agent_name == "documentation"
    )
    assert execute("write python code").success is True


def test_module_entrypoint_runs_from_parent_directory():
    result = subprocess.run(
        [sys.executable, "-m", "switchboard", "--input", "write python code"],
        cwd=PROJECT_PARENT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    # Agent now returns real LLM output (not placeholder)
    assert "python" in result.stdout.lower() or "code" in result.stdout.lower()


def test_module_entrypoint_without_input_prints_demo_when_stdin_is_empty():
    result = subprocess.run(
        [sys.executable, "-m", "switchboard"],
        cwd=PROJECT_PARENT,
        capture_output=True,
        text=True,
        check=False,
        input="",
    )

    assert result.returncode == 0
    assert "Switchboard Router v1" in result.stdout
    assert "📝 Input: analyze this dataset" in result.stdout
