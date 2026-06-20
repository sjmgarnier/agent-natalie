"""Task 13.4 — natalie init installs Mistral Vibe subagent files."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from natalie.cli import app

runner = CliRunner()


def test_init_writes_vibe_agent_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    toml_file = vault / ".vibe" / "agents" / "natalie-assistant.toml"
    assert toml_file.exists()


def test_init_creates_vibe_agents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    assert (vault / ".vibe" / "agents").is_dir()


def test_init_writes_vibe_system_prompt_to_user_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    prompt_file = home / ".vibe" / "prompts" / "natalie-assistant.md"
    assert prompt_file.exists()


def test_init_creates_vibe_prompts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    assert (home / ".vibe" / "prompts").is_dir()


def test_init_vibe_agent_toml_has_subagent_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tomllib

    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    with open(vault / ".vibe" / "agents" / "natalie-assistant.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["agent_type"] == "subagent"
    assert data["system_prompt_id"] == "natalie-assistant"


def test_init_vibe_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    runner.invoke(app, ["init", str(vault)], input="y\n")
    assert (vault / ".vibe" / "agents" / "natalie-assistant.toml").exists()
    assert (tmp_path / "home" / ".vibe" / "prompts" / "natalie-assistant.md").exists()
