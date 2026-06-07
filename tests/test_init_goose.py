import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from typer.testing import CliRunner

from natalie.cli import __version__, _merge_yaml, app

runner = CliRunner()


def _load_yaml(path: Path) -> dict:  # type: ignore[type-arg]
    yaml = YAML()
    with open(path) as f:
        return yaml.load(f) or {}  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# _merge_yaml unit tests
# ---------------------------------------------------------------------------


def test_merge_yaml_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True}}})
    assert target.exists()
    data = _load_yaml(target)
    assert data["extensions"]["natalie"]["enabled"] is True


def test_merge_yaml_merges_into_existing(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    yaml = YAML()
    with open(target, "w") as f:
        yaml.dump({"GOOSE_PROVIDER": "anthropic", "extensions": {"developer": {"enabled": True}}}, f)
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True}}})
    data = _load_yaml(target)
    assert data["GOOSE_PROVIDER"] == "anthropic"
    assert data["extensions"]["developer"]["enabled"] is True
    assert data["extensions"]["natalie"]["enabled"] is True


def test_merge_yaml_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    update = {"extensions": {"natalie": {"enabled": True, "cmd": "/bin/natalie-server"}}}
    _merge_yaml(target, update)
    _merge_yaml(target, update)
    data = _load_yaml(target)
    assert isinstance(data["extensions"]["natalie"], dict)
    assert data["extensions"]["natalie"]["cmd"] == "/bin/natalie-server"


def test_merge_yaml_updates_existing_extension(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    yaml = YAML()
    with open(target, "w") as f:
        yaml.dump({"extensions": {"natalie": {"enabled": False, "cmd": "/old/path"}}}, f)
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True, "cmd": "/new/path"}}})
    data = _load_yaml(target)
    assert data["extensions"]["natalie"]["enabled"] is True
    assert data["extensions"]["natalie"]["cmd"] == "/new/path"


def test_merge_yaml_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "config.yaml"
    _merge_yaml(target, {"key": "value"})
    assert target.exists()
    data = _load_yaml(target)
    assert data["key"] == "value"


def test_merge_yaml_handles_corrupt_file(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("{{invalid: yaml: [}", encoding="utf-8")
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True}}})
    data = _load_yaml(target)
    assert data["extensions"]["natalie"]["enabled"] is True


# ---------------------------------------------------------------------------
# natalie init — Goose integration tests
# ---------------------------------------------------------------------------


def test_init_creates_goose_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    goose_cfg = tmp_path / "home" / ".config" / "goose" / "config.yaml"
    assert goose_cfg.exists()
    data = _load_yaml(goose_cfg)
    assert "natalie" in data["extensions"]
    ext = data["extensions"]["natalie"]
    assert ext["enabled"] is True
    assert ext["type"] == "stdio"
    assert ext["timeout"] == 300


def test_init_goose_config_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    runner.invoke(app, ["init", str(vault)], input="y\n")
    goose_cfg = tmp_path / "home" / ".config" / "goose" / "config.yaml"
    data = _load_yaml(goose_cfg)
    assert isinstance(data["extensions"]["natalie"], dict)


def test_init_writes_plugin_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    plugin_json = vault / ".agents" / "plugins" / "natalie" / "plugin.json"
    assert plugin_json.exists()
    data = json.loads(plugin_json.read_text())
    assert data["name"] == "natalie"
    assert data["version"] == __version__


def test_init_writes_hooks_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    hooks_json = vault / ".agents" / "plugins" / "natalie" / "hooks" / "hooks.json"
    assert hooks_json.exists()
    data = json.loads(hooks_json.read_text())
    assert "PostToolUse" in data["hooks"]
    rule = data["hooks"]["PostToolUse"][0]
    assert rule["matcher"] == ".*"
    assert any("natalie" in h.get("command", "") for h in rule["hooks"])


def test_init_copies_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    skill = vault / ".agents" / "plugins" / "natalie" / "skills" / "natalie-contact-enrichment" / "SKILL.md"
    assert skill.exists()
    assert "natalie-contact-enrichment" in skill.read_text()


def test_init_goose_preserves_existing_goose_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    home = tmp_path / "home"
    goose_cfg_path = home / ".config" / "goose" / "config.yaml"
    goose_cfg_path.parent.mkdir(parents=True)
    yaml = YAML()
    with open(goose_cfg_path, "w") as f:
        yaml.dump({"GOOSE_PROVIDER": "openai", "extensions": {"developer": {"enabled": True}}}, f)
    monkeypatch.setenv("HOME", str(home))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    data = _load_yaml(goose_cfg_path)
    assert data["GOOSE_PROVIDER"] == "openai"
    assert data["extensions"]["developer"]["enabled"] is True
    assert "natalie" in data["extensions"]
