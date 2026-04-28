import os

from switchboard.env import load_environment


def test_load_environment_skips_empty_values_and_uses_later_file(tmp_path, monkeypatch):
    first = tmp_path / "switchboard.env"
    second = tmp_path / "nexus.env"
    first.write_text("OPENAI_API_KEY=\nANTHROPIC_API_KEY=first-anthropic\n")
    second.write_text("OPENAI_API_KEY=second-openai\n")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    load_environment((first, second))

    assert os.environ["OPENAI_API_KEY"] == "second-openai"
    assert os.environ["ANTHROPIC_API_KEY"] == "first-anthropic"


def test_load_environment_preserves_existing_shell_vars(tmp_path, monkeypatch):
    env_file = tmp_path / "switchboard.env"
    env_file.write_text("OPENAI_API_KEY=file-openai\n")

    monkeypatch.setenv("OPENAI_API_KEY", "shell-openai")

    load_environment((env_file,))

    assert os.environ["OPENAI_API_KEY"] == "shell-openai"