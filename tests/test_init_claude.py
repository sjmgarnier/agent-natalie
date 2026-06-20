"""Task 13.2 — natalie init writes Claude Code subagent definition."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from natalie.cli import app

runner = CliRunner()


def test_init_writes_claude_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    agent_file = vault / ".claude" / "agents" / "natalie-assistant.md"
    assert agent_file.exists()


def test_init_claude_agent_has_expected_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    content = (vault / ".claude" / "agents" / "natalie-assistant.md").read_text(encoding="utf-8")
    assert "natalie-assistant" in content
    assert "natalie-contact-enrichment" in content


def test_init_claude_agent_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    runner.invoke(app, ["init", str(vault)], input="y\n")
    agent_file = vault / ".claude" / "agents" / "natalie-assistant.md"
    assert agent_file.exists()
    assert "natalie-assistant" in agent_file.read_text(encoding="utf-8")


def test_init_creates_claude_agents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    assert (vault / ".claude" / "agents").is_dir()
