import json
import tomllib
from pathlib import Path

import pytest
import tomli_w
from typer.testing import CliRunner

from natalie.cli import app

runner = CliRunner()


def _init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, venv: str = "/opt/natalie") -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    vault = tmp_path / "vault"
    result = runner.invoke(
        app,
        ["init", str(vault), "--client", "codex", "--venv-path", venv],
    )
    assert result.exit_code == 0, result.output
    return vault


def test_init_codex_writes_exact_mcp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _init(tmp_path, monkeypatch)
    with open(vault / ".codex" / "config.toml", "rb") as f:
        config = tomllib.load(f)
    natalie = config["mcp_servers"]["natalie"]
    assert natalie == {
        "command": "/opt/natalie/bin/natalie-server",
        "args": [],
        "cwd": str(vault.resolve()),
        "enabled": True,
    }


def test_init_codex_preserves_unrelated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    vault = tmp_path / "vault"
    codex_dir = vault / ".codex"
    codex_dir.mkdir(parents=True)
    (codex_dir / "config.toml").write_bytes(
        tomli_w.dumps(
            {
                "model_reasoning_effort": "high",
                "mcp_servers": {"other": {"command": "other-mcp", "args": ["serve"]}},
            }
        ).encode()
    )
    runner.invoke(app, ["init", str(vault), "--client", "codex", "--venv-path", "/new"])
    with open(codex_dir / "config.toml", "rb") as f:
        config = tomllib.load(f)
    assert config["model_reasoning_effort"] == "high"
    assert config["mcp_servers"]["other"]["command"] == "other-mcp"
    assert config["mcp_servers"]["natalie"]["command"] == "/new/bin/natalie-server"


def test_init_codex_updates_managed_paths_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _init(tmp_path, monkeypatch, "/old")
    runner.invoke(app, ["init", str(vault), "--client", "codex", "--venv-path", "/new"])
    runner.invoke(app, ["init", str(vault), "--client", "codex", "--venv-path", "/new"])
    with open(vault / ".codex" / "config.toml", "rb") as f:
        config = tomllib.load(f)
    assert list(config["mcp_servers"]).count("natalie") == 1
    assert config["mcp_servers"]["natalie"]["command"] == "/new/bin/natalie-server"


def test_init_codex_writes_one_stop_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _init(tmp_path, monkeypatch)
    data = json.loads((vault / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    stop = data["hooks"]["Stop"]
    assert len(stop) == 1
    assert stop[0]["hooks"][0]["command"] == "/opt/natalie/bin/natalie sync --quiet"


def test_init_codex_hook_preserves_unrelated_and_replaces_old_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _init(tmp_path, monkeypatch, "/old")
    hooks_path = vault / ".codex" / "hooks.json"
    data = json.loads(hooks_path.read_text(encoding="utf-8"))
    data["hooks"]["SessionStart"] = [{"hooks": [{"type": "command", "command": "echo hi"}]}]
    hooks_path.write_text(json.dumps(data), encoding="utf-8")
    runner.invoke(app, ["init", str(vault), "--client", "codex", "--venv-path", "/new"])
    updated = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert updated["hooks"]["SessionStart"] == data["hooks"]["SessionStart"]
    stop_commands = [h["command"] for entry in updated["hooks"]["Stop"] for h in entry["hooks"]]
    assert stop_commands == ["/new/bin/natalie sync --quiet"]


def test_init_codex_installs_inheriting_assistant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _init(tmp_path, monkeypatch)
    path = vault / ".codex" / "agents" / "natalie-assistant.toml"
    with open(path, "rb") as f:
        agent = tomllib.load(f)
    assert agent["name"] == "natalie-assistant"
    instructions = agent["developer_instructions"]
    for phrase in ("Do not ask", "Store every", "Verify", "completion summary"):
        assert phrase in instructions
    for field in ("model", "model_reasoning_effort", "sandbox_mode", "approval_policy", "mcp_servers"):
        assert field not in agent


def test_init_codex_preserves_unrelated_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = _init(tmp_path, monkeypatch)
    other = vault / ".codex" / "agents" / "other.toml"
    other.write_text('name = "other"\n', encoding="utf-8")
    runner.invoke(app, ["init", str(vault), "--client", "codex"])
    assert other.read_text(encoding="utf-8") == 'name = "other"\n'


def test_init_codex_prints_trust_reminder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    result = runner.invoke(app, ["init", str(tmp_path / "vault"), "--client", "codex"])
    assert result.exit_code == 0
    for phrase in ("Trust this project", "/hooks", "/mcp", "restart Codex"):
        assert phrase in result.output
