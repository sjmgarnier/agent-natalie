from unittest.mock import patch

from typer.testing import CliRunner

from natalie.cli import app

runner = CliRunner()


def test_version_flag():
    from importlib.metadata import version

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert version("agent-natalie") in result.output


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "natalie" in result.output.lower()


def test_config_persona_writes_claude_md(vault):
    with (
        patch("natalie.cli.require_vault", return_value=vault),
        patch("natalie.cli.load_config") as mock_cfg,
    ):
        from natalie.config import NatalieConfig, PersonaConfig

        mock_cfg.return_value = NatalieConfig(persona=PersonaConfig(name="natalie"))
        result = runner.invoke(app, ["config", "--persona", "natalie"])
    assert result.exit_code == 0
    assert (vault / "CLAUDE.md").exists()
    assert (vault / "AGENTS.md").exists()


def test_config_persona_writes_persona_markers(vault):
    with (
        patch("natalie.cli.require_vault", return_value=vault),
        patch("natalie.cli.load_config") as mock_cfg,
    ):
        from natalie.config import NatalieConfig, PersonaConfig

        mock_cfg.return_value = NatalieConfig(persona=PersonaConfig(name="natalie"))
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
    mcp_path.write_text(
        json.dumps({"mcpServers": {"github": {"command": "github-mcp", "args": [], "type": "stdio"}}})
    )
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


def test_init_enables_css_snippets(tmp_path):
    import json

    runner.invoke(app, ["init", str(tmp_path)])
    appearance = json.loads((tmp_path / ".obsidian" / "appearance.json").read_text())
    snippets = appearance.get("enabledCssSnippets", [])
    assert "natalie-dashboard" in snippets
    assert "MCL Multi Column" in snippets
    assert "MCL Wide Views" in snippets


def test_config_no_args_does_not_regenerate_files(vault):
    """natalie config with no arguments must not overwrite CLAUDE.md — I1."""
    existing = vault / "CLAUDE.md"
    existing.write_text("# sentinel content\n")
    with (
        patch("natalie.cli.require_vault", return_value=vault),
        patch("natalie.cli.load_config") as mock_cfg,
    ):
        from natalie.config import NatalieConfig, PersonaConfig

        mock_cfg.return_value = NatalieConfig(persona=PersonaConfig(name="natalie"))
        runner.invoke(app, ["config"])
    assert existing.read_text() == "# sentinel content\n"


def test_config_regen_flag_regenerates_files(vault):
    """natalie config --regen must regenerate CLAUDE.md without changing persona — I1."""
    existing = vault / "CLAUDE.md"
    existing.write_text("# sentinel content\n")
    with (
        patch("natalie.cli.require_vault", return_value=vault),
        patch("natalie.cli.load_config") as mock_cfg,
    ):
        from natalie.config import NatalieConfig, PersonaConfig

        mock_cfg.return_value = NatalieConfig(persona=PersonaConfig(name="natalie"))
        result = runner.invoke(app, ["config", "--regen"])
    assert result.exit_code == 0
    assert existing.read_text() != "# sentinel content\n"
    assert "agent-natalie:persona:start" in existing.read_text()


def test_init_completion_message_mentions_vault_directory(tmp_path):
    """The sync instruction must tell the user to run from the vault directory — I4."""
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    sync_line = next(line for line in result.output.splitlines() if "sync" in line)
    assert str(tmp_path) in sync_line


def test_init_merges_existing_appearance_json(tmp_path):
    import json

    appearance_path = tmp_path / ".obsidian" / "appearance.json"
    appearance_path.parent.mkdir(parents=True, exist_ok=True)
    appearance_path.write_text(
        json.dumps({"theme": "Minimal", "enabledCssSnippets": ["my-existing-snippet"]})
    )
    runner.invoke(app, ["init", str(tmp_path)])
    result = json.loads(appearance_path.read_text())
    assert result.get("theme") == "Minimal"
    snippets = result.get("enabledCssSnippets", [])
    assert "my-existing-snippet" in snippets
    assert "natalie-dashboard" in snippets
    assert "MCL Multi Column" in snippets
    assert "MCL Wide Views" in snippets


def test_init_does_not_duplicate_hooks(tmp_path):
    """Repeated natalie init must not accumulate duplicate PostToolUse hooks — B5."""
    import json

    runner.invoke(app, ["init", str(tmp_path)])
    runner.invoke(app, ["init", str(tmp_path)])
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    hooks = settings.get("hooks", {}).get("PostToolUse", [])
    assert len(hooks) == 1, f"Expected 1 PostToolUse hook entry, got {len(hooks)}: {hooks}"
