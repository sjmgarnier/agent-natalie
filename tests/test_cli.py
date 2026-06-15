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
        result = runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    assert result.exit_code == 0
    assert (tmp_path / ".natalie" / "natalie.db").exists()
    assert (tmp_path / "Natalie" / "config.toml").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / "opencode.json").exists()


def test_init_writes_mcp_entry_to_mcp_json(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
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
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    result = json.loads(mcp_path.read_text())
    assert "github" in result["mcpServers"]
    assert "natalie" in result["mcpServers"]


def test_init_preserves_existing_opencode_mcp(tmp_path):
    """natalie init must not destroy pre-existing MCPs in opencode.json."""
    import json

    oc_path = tmp_path / "opencode.json"
    oc_path.write_text(json.dumps({"mcp": {"other-tool": {"command": "other", "enabled": True}}}))
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    result = json.loads(oc_path.read_text())
    assert "other-tool" in result["mcp"]
    assert "natalie" in result["mcp"]


def test_init_does_not_overwrite_existing_claude_md(tmp_path):
    """natalie init must not overwrite CLAUDE.md if it already exists."""
    existing = tmp_path / "CLAUDE.md"
    existing.write_text("# My custom instructions\n")
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    assert existing.read_text() == "# My custom instructions\n"


def test_init_force_overwrites_claude_md(tmp_path):
    """natalie init --force must regenerate CLAUDE.md."""
    existing = tmp_path / "CLAUDE.md"
    existing.write_text("# My custom instructions\n")
    runner.invoke(app, ["init", str(tmp_path), "--force"], input="y\n")
    content = existing.read_text()
    assert "agent-natalie:persona:start" in content


def test_init_writes_rich_dashboard(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    content = (tmp_path / "Dashboard.md").read_text()
    assert "multi-column" in content
    assert "banner" in content


def test_init_skips_existing_dashboard(tmp_path):
    existing = tmp_path / "Dashboard.md"
    existing.write_text("# My custom dashboard\n")
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    assert existing.read_text() == "# My custom dashboard\n"


def test_init_copies_css_snippets(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    snippets_dir = tmp_path / ".obsidian" / "snippets"
    assert (snippets_dir / "natalie-dashboard.css").exists()
    assert (snippets_dir / "MCL Multi Column.css").exists()
    assert (snippets_dir / "MCL Wide Views.css").exists()


def test_init_skips_existing_css(tmp_path):
    snippets_dir = tmp_path / ".obsidian" / "snippets"
    snippets_dir.mkdir(parents=True)
    sentinel = "/* sentinel */"
    (snippets_dir / "natalie-dashboard.css").write_text(sentinel)
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    assert (snippets_dir / "natalie-dashboard.css").read_text() == sentinel


def test_init_enables_css_snippets(tmp_path):
    import json

    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
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
    result = runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    assert result.exit_code == 0
    sync_line = next(line for line in result.output.splitlines() if "natalie sync --full" in line)
    assert str(tmp_path) in sync_line


def test_init_existing_vault_omits_full_sync_recommendation(tmp_path, monkeypatch):
    """Re-running init on an existing vault should not recommend 'natalie sync --full'."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")  # creates db
    result = runner.invoke(app, ["init", str(tmp_path)], input="y\n")  # upgrade run
    assert result.exit_code == 0
    assert "natalie sync --full" not in result.output
    assert "reconfigured" in result.output


def test_init_merges_existing_appearance_json(tmp_path):
    import json

    appearance_path = tmp_path / ".obsidian" / "appearance.json"
    appearance_path.parent.mkdir(parents=True, exist_ok=True)
    appearance_path.write_text(
        json.dumps({"theme": "Minimal", "enabledCssSnippets": ["my-existing-snippet"]})
    )
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
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

    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    hooks = settings.get("hooks", {}).get("PostToolUse", [])
    assert len(hooks) == 1, f"Expected 1 PostToolUse hook entry, got {len(hooks)}: {hooks}"


def test_init_preserves_non_natalie_hooks(tmp_path):
    """natalie init must not wipe user-defined hooks from other tools."""
    import json

    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {
        "hooks": {
            "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo done"}]}],
            "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "echo pre"}]}],
        }
    }
    settings_path.write_text(json.dumps(existing), encoding="utf-8")

    runner.invoke(app, ["init", str(tmp_path)], input="y\n")

    settings = json.loads(settings_path.read_text())
    post = settings.get("hooks", {}).get("PostToolUse", [])
    pre = settings.get("hooks", {}).get("PreToolUse", [])
    commands = [h.get("command", "") for entry in post for h in entry.get("hooks", [])]
    assert any("natalie" in c for c in commands), "natalie hook missing"
    assert any("echo done" in c for c in commands), "existing PostToolUse hook was wiped"
    assert len(pre) == 1, "PreToolUse hooks were wiped"


# ---------------------------------------------------------------------------
# Mistral Vibe integration
# ---------------------------------------------------------------------------

import tomllib as _tomllib  # noqa: E402


def test_init_creates_vibe_directory(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    assert (tmp_path / ".vibe").is_dir()


def test_init_creates_vibe_config_with_mcp_entry(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    cfg_path = tmp_path / ".vibe" / "config.toml"
    assert cfg_path.exists()
    with open(cfg_path, "rb") as f:
        cfg = _tomllib.load(f)
    servers = {s["name"]: s for s in cfg.get("mcp_servers", [])}
    assert "natalie" in servers
    assert servers["natalie"]["transport"] == "stdio"


def test_init_vibe_config_excludes_skill_paths(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    with open(tmp_path / ".vibe" / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    assert "skill_paths" not in cfg.get("skills", {})


def test_init_creates_vibe_hooks_when_enabled(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    hooks_path = tmp_path / ".vibe" / "hooks.toml"
    assert hooks_path.exists()
    with open(hooks_path, "rb") as f:
        hooks_cfg = _tomllib.load(f)
    hooks = {h["name"]: h for h in hooks_cfg.get("hooks", [])}
    assert "natalie-sync" in hooks
    assert hooks["natalie-sync"]["type"] == "post_agent_turn"


def test_init_vibe_hooks_sets_experimental_flag_when_enabled(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    with open(tmp_path / ".vibe" / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    assert cfg.get("enable_experimental_hooks") is True


def test_init_no_vibe_hooks_when_disabled(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="n\n")
    assert not (tmp_path / ".vibe" / "hooks.toml").exists()


def test_init_vibe_no_experimental_flag_when_disabled(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="n\n")
    with open(tmp_path / ".vibe" / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    assert not cfg.get("enable_experimental_hooks")


def test_init_preserves_existing_vibe_mcp_entries(tmp_path):
    import tomli_w

    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    existing = {"mcp_servers": [{"name": "other-tool", "transport": "stdio", "command": "other"}]}
    (vibe_dir / "config.toml").write_bytes(tomli_w.dumps(existing).encode())
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    with open(vibe_dir / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    servers = {s["name"]: s for s in cfg.get("mcp_servers", [])}
    assert "other-tool" in servers
    assert "natalie" in servers


def test_init_does_not_duplicate_vibe_mcp(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")  # no prompt: hooks already enabled
    with open(tmp_path / ".vibe" / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    natalie_entries = [s for s in cfg.get("mcp_servers", []) if s.get("name") == "natalie"]
    assert len(natalie_entries) == 1


def test_init_does_not_duplicate_vibe_hooks(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")  # no prompt: hooks already enabled
    with open(tmp_path / ".vibe" / "hooks.toml", "rb") as f:
        hooks_cfg = _tomllib.load(f)
    natalie_hooks = [h for h in hooks_cfg.get("hooks", []) if h.get("name") == "natalie-sync"]
    assert len(natalie_hooks) == 1


def test_init_carries_global_vibe_mcp_servers(tmp_path, monkeypatch):
    """Global ~/.vibe/config.toml settings (including mcp_servers) must survive into the project config."""
    from pathlib import Path

    import tomli_w

    # Fake a global ~/.vibe/config.toml with a non-natalie MCP
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    global_vibe = fake_home / ".vibe"
    global_vibe.mkdir()
    (global_vibe / "config.toml").write_bytes(
        tomli_w.dumps(
            {"mcp_servers": [{"name": "github", "transport": "stdio", "command": "github-mcp"}]}
        ).encode()
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    runner.invoke(app, ["init", str(tmp_path)], input="y\n")

    with open(tmp_path / ".vibe" / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    servers = {s["name"]: s for s in cfg.get("mcp_servers", [])}
    assert "natalie" in servers, "natalie MCP missing"
    assert "github" in servers, "global github MCP was dropped"


def test_init_global_vibe_mcp_does_not_override_natalie(tmp_path, monkeypatch):
    """A global entry named 'natalie' must not overwrite the project's natalie entry."""
    from pathlib import Path

    import tomli_w

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    global_vibe = fake_home / ".vibe"
    global_vibe.mkdir()
    (global_vibe / "config.toml").write_bytes(
        tomli_w.dumps(
            {"mcp_servers": [{"name": "natalie", "transport": "stdio", "command": "wrong-path"}]}
        ).encode()
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    runner.invoke(app, ["init", str(tmp_path), "--venv-path", "/my/venv"], input="y\n")

    with open(tmp_path / ".vibe" / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    servers = {s["name"]: s for s in cfg.get("mcp_servers", [])}
    assert servers["natalie"]["command"] != "wrong-path", "global natalie entry overwrote project entry"


def test_init_carries_global_vibe_non_mcp_settings(tmp_path, monkeypatch):
    """Global ~/.vibe/config.toml settings beyond mcp_servers (e.g. model) must survive."""
    from pathlib import Path

    import tomli_w

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    global_vibe = fake_home / ".vibe"
    global_vibe.mkdir()
    (global_vibe / "config.toml").write_bytes(
        tomli_w.dumps({"model": "mistral-large-latest", "temperature": 0.3}).encode()
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    runner.invoke(app, ["init", str(tmp_path)], input="y\n")

    with open(tmp_path / ".vibe" / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    assert cfg.get("model") == "mistral-large-latest", "global model setting was dropped"
    assert cfg.get("temperature") == 0.3, "global temperature setting was dropped"


def test_init_skips_hooks_prompt_when_already_enabled(tmp_path):
    """Second run must detect enable_experimental_hooks=true and skip the prompt."""
    import tomli_w

    vibe_dir = tmp_path / ".vibe"
    vibe_dir.mkdir()
    (vibe_dir / "config.toml").write_bytes(tomli_w.dumps({"enable_experimental_hooks": True}).encode())
    # Provide no input — if the prompt were shown, CliRunner would use the default
    # and the test would still pass, but we also verify the flag stays true.
    result = runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    assert result.exit_code == 0
    with open(vibe_dir / "config.toml", "rb") as f:
        cfg = _tomllib.load(f)
    assert cfg.get("enable_experimental_hooks") is True


def test_init_copies_skills_to_agents_skills(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    agents_skills = tmp_path / ".agents" / "skills"
    assert agents_skills.is_dir()
    skill_dirs = [p.name for p in agents_skills.iterdir() if p.is_dir()]
    assert "natalie-contact-enrichment" in skill_dirs


def test_init_creates_claude_skills_symlink(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    link = tmp_path / ".claude" / "skills"
    assert link.is_symlink()
    assert link.resolve() == (tmp_path / ".agents" / "skills").resolve()


def test_init_claude_skills_symlink_is_idempotent(tmp_path):
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    runner.invoke(app, ["init", str(tmp_path)], input="y\n")
    link = tmp_path / ".claude" / "skills"
    assert link.is_symlink()
    assert link.resolve() == (tmp_path / ".agents" / "skills").resolve()
