"""Task 13.3 — natalie init merges OpenCode subagent definition into opencode.json."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from natalie.cli import app

runner = CliRunner()


def test_init_creates_opencode_json_with_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    opencode_json = vault / "opencode.json"
    assert opencode_json.exists()
    data = json.loads(opencode_json.read_text(encoding="utf-8"))
    assert "agent" in data
    assert "natalie-assistant" in data["agent"]


def test_init_opencode_agent_has_required_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    data = json.loads((vault / "opencode.json").read_text(encoding="utf-8"))
    agent = data["agent"]["natalie-assistant"]
    assert agent["mode"] == "subagent"
    assert agent["hidden"] is True
    assert "prompt" in agent


def test_init_opencode_agent_merges_without_duplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    runner.invoke(app, ["init", str(vault)], input="y\n")
    data = json.loads((vault / "opencode.json").read_text(encoding="utf-8"))
    # "agent" should be a dict (not a list), so repeated runs cannot accumulate duplicates
    assert isinstance(data["agent"], dict)
    assert list(data["agent"].keys()).count("natalie-assistant") == 1


def test_init_opencode_preserves_existing_mcp_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (vault / "opencode.json").write_text(
        json.dumps({"mcp": {"other-tool": {"type": "local", "command": ["/usr/bin/other"]}}}),
        encoding="utf-8",
    )
    runner.invoke(app, ["init", str(vault)], input="y\n")
    data = json.loads((vault / "opencode.json").read_text(encoding="utf-8"))
    assert "other-tool" in data["mcp"]
    assert "natalie-assistant" in data["agent"]
