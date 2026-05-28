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


def test_init_writes_mcp_entry_to_mcp_json(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)])
    import json
    mcp_json = json.loads((tmp_path / ".mcp.json").read_text())
    assert "natalie" in mcp_json.get("mcpServers", {})


def test_init_preserves_existing_mcp_entries(tmp_path):
    """natalie init must not destroy pre-existing MCP servers in .mcp.json."""
    import json
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text(json.dumps({
        "mcpServers": {
            "github": {"command": "github-mcp", "args": [], "type": "stdio"}
        }
    }))
    runner.invoke(app, ["init", str(tmp_path)])
    result = json.loads(mcp_path.read_text())
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


def test_init_does_not_overwrite_existing_claude_md(tmp_path):
    """natalie init must not overwrite CLAUDE.md if it already exists."""
    existing = tmp_path / "CLAUDE.md"
    existing.write_text("# My custom instructions\n")
    runner.invoke(app, ["init", str(tmp_path)])
    assert existing.read_text() == "# My custom instructions\n"


def test_init_force_overwrites_claude_md(tmp_path):
    """natalie init --force must regenerate CLAUDE.md."""
    existing = tmp_path / "CLAUDE.md"
    existing.write_text("# My custom instructions\n")
    runner.invoke(app, ["init", str(tmp_path), "--force"])
    content = existing.read_text()
    assert "agent-natalie:persona:start" in content


def test_init_writes_rich_dashboard(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)])
    content = (tmp_path / "Dashboard.md").read_text()
    assert "multi-column" in content
    assert "banner" in content


def test_init_skips_existing_dashboard(tmp_path):
    existing = tmp_path / "Dashboard.md"
    existing.write_text("# My custom dashboard\n")
    runner.invoke(app, ["init", str(tmp_path)])
    assert existing.read_text() == "# My custom dashboard\n"


def test_init_copies_css_snippets(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)])
    snippets_dir = tmp_path / ".obsidian" / "snippets"
    assert (snippets_dir / "natalie-dashboard.css").exists()
    assert (snippets_dir / "MCL Multi Column.css").exists()
    assert (snippets_dir / "MCL Wide Views.css").exists()


def test_init_skips_existing_css(tmp_path):
    snippets_dir = tmp_path / ".obsidian" / "snippets"
    snippets_dir.mkdir(parents=True)
    sentinel = "/* sentinel */"
    (snippets_dir / "natalie-dashboard.css").write_text(sentinel)
    runner.invoke(app, ["init", str(tmp_path)])
    assert (snippets_dir / "natalie-dashboard.css").read_text() == sentinel
