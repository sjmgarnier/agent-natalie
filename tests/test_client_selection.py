import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from natalie.cli import app
from natalie.config import LEGACY_CLIENTS, SUPPORTED_CLIENTS

runner = CliRunner()


def _clients(vault: Path) -> list[str]:
    with open(vault / "Natalie" / "config.toml", "rb") as f:
        return tomllib.load(f)["clients"]["enabled"]


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return home


def test_select_one_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--client", "codex"])
    assert result.exit_code == 0, result.output
    assert _clients(vault) == ["codex"]


def test_select_multiple_clients_normalizes_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    result = runner.invoke(
        app,
        ["init", str(vault), "--client", "codex", "--client", "claude", "--client", "codex"],
    )
    assert result.exit_code == 0, result.output
    assert _clients(vault) == ["claude", "codex"]


def test_select_all_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--client", "all"], input="y\n")
    assert result.exit_code == 0, result.output
    assert _clients(vault) == list(SUPPORTED_CLIENTS)
    assert (vault / ".codex" / "config.toml").exists()


@pytest.mark.parametrize("clients", [["unknown"], ["all", "codex"]])
def test_rejects_invalid_client_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clients: list[str]
) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    args = ["init", str(vault)]
    for client in clients:
        args.extend(["--client", client])
    result = runner.invoke(app, args)
    assert result.exit_code != 0
    assert not (vault / ".codex").exists()
    assert not (vault / ".claude").exists()


def test_stored_selection_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault), "--client", "codex"])
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code == 0, result.output
    assert _clients(vault) == ["codex"]
    assert not (vault / ".mcp.json").exists()


def test_explicit_selection_replaces_stored_without_deleting_old_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault), "--client", "codex"])
    codex_config = vault / ".codex" / "config.toml"
    original = codex_config.read_text(encoding="utf-8")
    result = runner.invoke(app, ["init", str(vault), "--client", "claude"])
    assert result.exit_code == 0, result.output
    assert _clients(vault) == ["claude"]
    assert codex_config.read_text(encoding="utf-8") == original
    assert (vault / ".mcp.json").exists()


def test_legacy_fallback_excludes_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault)], input="y\n")
    assert result.exit_code == 0, result.output
    assert _clients(vault) == list(LEGACY_CLIENTS)
    assert (vault / ".mcp.json").exists()
    assert (vault / "opencode.json").exists()
    assert (vault / ".vibe").exists()
    assert (home / ".config" / "goose" / "config.yaml").exists()
    assert not (vault / ".codex").exists()


def test_codex_only_skips_other_clients_and_vibe_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    result = runner.invoke(app, ["init", str(vault), "--client", "codex"])
    assert result.exit_code == 0, result.output
    assert "experimental post-agent-turn" not in result.output
    assert not (vault / ".claude").exists()
    assert not (vault / ".opencode").exists()
    assert not (vault / ".vibe").exists()
    assert not (vault / "opencode.json").exists()
    assert not (home / ".config" / "goose").exists()
    assert (vault / "AGENTS.md").exists()
    assert (vault / ".agents" / "skills" / "natalie-delegate" / "SKILL.md").exists()


def test_invalid_stored_selection_fails_before_client_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    (vault / "Natalie").mkdir(parents=True)
    (vault / "Natalie" / "config.toml").write_text('[clients]\nenabled = ["invalid"]\n')
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code != 0
    assert not (vault / ".codex").exists()
    assert not (vault / ".claude").exists()


def test_rerun_with_unchanged_selection_preserves_config_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault), "--client", "codex"])
    config_path = vault / "Natalie" / "config.toml"
    config_path.write_text(config_path.read_text(encoding="utf-8") + "\n# hand-written note, keep me\n")
    result = runner.invoke(app, ["init", str(vault)])
    assert result.exit_code == 0, result.output
    assert "# hand-written note, keep me" in config_path.read_text(encoding="utf-8")


def test_rerun_with_changed_selection_still_persists_new_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _home(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    runner.invoke(app, ["init", str(vault), "--client", "codex"])
    result = runner.invoke(app, ["init", str(vault), "--client", "claude"])
    assert result.exit_code == 0, result.output
    assert _clients(vault) == ["claude"]
