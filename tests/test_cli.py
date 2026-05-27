from unittest.mock import patch
from pathlib import Path

from typer.testing import CliRunner
from natalie.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "natalie" in result.output.lower()


def test_config_persona_writes_claude_md(vault):
    with patch("natalie.cli.require_vault", return_value=vault), \
         patch("natalie.cli.load_config") as mock_cfg:
        from natalie.config import NatalieConfig, PersonaConfig
        mock_cfg.return_value = NatalieConfig(vault=vault, persona=PersonaConfig(name="natalie"))
        result = runner.invoke(app, ["config", "--persona", "natalie"])
    assert result.exit_code == 0
    assert (vault / "CLAUDE.md").exists()
    assert (vault / "AGENTS.md").exists()


def test_config_persona_writes_persona_markers(vault):
    with patch("natalie.cli.require_vault", return_value=vault), \
         patch("natalie.cli.load_config") as mock_cfg:
        from natalie.config import NatalieConfig, PersonaConfig
        mock_cfg.return_value = NatalieConfig(vault=vault, persona=PersonaConfig(name="natalie"))
        runner.invoke(app, ["config", "--persona", "natalie"])
    content = (vault / "CLAUDE.md").read_text()
    assert "<!-- agent-natalie:persona:start -->" in content
    assert "<!-- agent-natalie:persona:end -->" in content


def test_init_creates_vault_structure(tmp_path):
    with patch("natalie.cli.require_vault", side_effect=RuntimeError("not found")):
        result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".natalie" / "natalie.db").exists()
    assert (tmp_path / "Natalie" / "config.toml").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / "opencode.json").exists()


def test_init_writes_mcp_entry_to_settings_json(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)])
    import json
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "natalie" in settings.get("mcpServers", {})


def test_init_preserves_existing_mcp_entries(tmp_path):
    """natalie init must not destroy pre-existing MCP servers in settings.json."""
    import json
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "mcpServers": {
            "github": {"command": "github-mcp", "args": [], "type": "stdio"}
        }
    }))
    runner.invoke(app, ["init", str(tmp_path)])
    result = json.loads(settings_path.read_text())
    assert "github" in result["mcpServers"]
    assert "natalie" in result["mcpServers"]


def test_init_preserves_existing_opencode_mcp(tmp_path):
    """natalie init must not destroy pre-existing MCPs in opencode.json."""
    import json
    oc_path = tmp_path / "opencode.json"
    oc_path.write_text(json.dumps({"mcp": {"other-tool": {"command": "other", "enabled": True}}}))
    runner.invoke(app, ["init", str(tmp_path)])
    result = json.loads(oc_path.read_text())
    assert "other-tool" in result["mcp"]
    assert "natalie" in result["mcp"]


def test_init_writes_embedding_provider_to_config(tmp_path):
    result = runner.invoke(app, ["init", str(tmp_path), "--embedding-provider", "openai"])
    assert result.exit_code == 0
    config_text = (tmp_path / "Natalie" / "config.toml").read_text()
    assert 'embedding_provider = "openai"' in config_text
