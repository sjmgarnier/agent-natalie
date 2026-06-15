import json
import shutil
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

import tomli_w
import typer
from ruamel.yaml import YAML as _YAML

from .config import load_config
from .db import get_db, init_db
from .features.memory import DEFAULT_EMBEDDING_MODEL
from .generate import render_instructions
from .vault import require_vault

app = typer.Typer(
    name="natalie",
    help="Natalie — personal assistant CLI",
    add_completion=False,
)

try:
    __version__ = _pkg_version("agent-natalie")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"natalie {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass


@app.command()
def sync(
    full: bool = typer.Option(False, "--full", help="Rebuild the entire index from scratch."),
) -> None:
    """Sync the vault index (incremental by default)."""
    vault = require_vault()
    config = load_config(vault)
    init_db(vault)
    db = get_db(vault)
    from .features.sync import sync_vault

    if full:
        typer.echo("Building full index... (first run downloads ~130 MB model; a progress bar will appear)")
    try:
        result = sync_vault(db, vault, full=full, model_name=config.memory.embedding_model)
    finally:
        db.close()
    if full:
        typer.echo(f"Full rebuild: {result['embedded']} embedded, {result['removed']} removed.")
    else:
        typer.echo(
            f"Synced: {result['indexed']} indexed, "
            f"{result['removed']} removed, {result['embedded']} embedded."
        )


@app.command()
def config(
    persona: str | None = typer.Option(None, "--persona", help="Persona name to activate."),
    regen: bool = typer.Option(
        False,
        "--regen",
        help="Regenerate CLAUDE.md / AGENTS.md without changing persona.",
    ),
) -> None:
    """Update vault configuration and regenerate CLAUDE.md / AGENTS.md."""
    vault = require_vault()
    cfg = load_config(vault)
    if persona:
        cfg.persona.name = persona
        config_path = vault / "Natalie" / "config.toml"
        try:
            with open(config_path, "rb") as f:
                data = dict(tomllib.load(f))
        except FileNotFoundError:
            data = {}
        data.setdefault("persona", {})["name"] = persona
        config_path.write_bytes(tomli_w.dumps(data).encode())
    if persona or regen:
        claude_content = render_instructions(cfg, vault, target="claude")
        agents_content = render_instructions(cfg, vault, target="agents")
        (vault / "CLAUDE.md").write_text(claude_content, encoding="utf-8")
        (vault / "AGENTS.md").write_text(agents_content, encoding="utf-8")
        typer.echo(f"Generated CLAUDE.md and AGENTS.md with persona: {cfg.persona.name}")
    else:
        typer.echo("No changes. Use --persona to change persona or --regen to regenerate.")


_DEFAULT_CONFIG_TOML = """\
[persona]
name = "{persona}"

[memory]
embedding_model = "{embedding_model}"

[skills]
preferred = []
denied    = []

[mcps]
preferred = []
denied    = []

[features.documents]
directory = "Natalie/Documents"

[features.contacts]
directory = "Natalie/Contacts"

[features.tasks]
note = "Tasks.md"
"""


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> None:
    """Recursively merge update into base in-place."""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        elif key in base and isinstance(base[key], list) and isinstance(value, list):
            # For lists, append items not already present (by equality)
            for item in value:
                if item not in base[key]:
                    base[key].append(item)
        else:
            base[key] = value


def _merge_json(path: Path, update: dict[str, Any]) -> None:
    """Read existing JSON if present, deep-merge update into it, write back."""
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}
    _deep_merge(existing, update)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _deep_merge_toml(base: dict[str, Any], update: dict[str, Any]) -> None:
    """Recursively merge *update* into *base* in-place.

    Arrays of dicts with a ``name`` key are merged by that key so repeated
    ``natalie init`` runs never accumulate duplicate entries. Other lists
    append unique items.
    """
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge_toml(base[key], value)
        elif key in base and isinstance(base[key], list) and isinstance(value, list):
            if value and isinstance(value[0], dict) and "name" in value[0]:
                existing_by_name = {
                    item["name"]: idx
                    for idx, item in enumerate(base[key])
                    if isinstance(item, dict) and "name" in item
                }
                for item in value:
                    name = item.get("name")
                    if name in existing_by_name:
                        base[key][existing_by_name[name]].update(item)
                    else:
                        base[key].append(item)
            else:
                for item in value:
                    if item not in base[key]:
                        base[key].append(item)
        else:
            base[key] = value


def _merge_toml(path: Path, update: dict[str, Any]) -> None:
    """Read existing TOML if present, deep-merge *update* into it, write back."""
    if path.exists():
        try:
            with open(path, "rb") as f:
                existing: dict[str, Any] = dict(tomllib.load(f))
        except (tomllib.TOMLDecodeError, OSError):
            existing = {}
    else:
        existing = {}
    _deep_merge_toml(existing, update)
    path.write_bytes(tomli_w.dumps(existing).encode())


def _merge_yaml(path: Path, update: dict[str, Any]) -> None:
    """Read existing YAML if present, deep-merge update into it, write back.

    Uses ruamel.yaml in round-trip mode to preserve user comments and formatting.
    """
    yaml = _YAML()
    yaml.preserve_quotes = True
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                existing: Any = yaml.load(f) or {}
        except Exception:  # noqa: BLE001
            existing = {}
    else:
        existing = {}
    _deep_merge(existing, update)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f)


@app.command()
def init(
    vault_path: str = typer.Argument(..., help="Path to the Obsidian vault (created if missing)."),
    persona: str = typer.Option("natalie", "--persona", help="Persona to activate."),
    venv_path: str = typer.Option(
        str(Path.home() / ".natalie" / ".venv"),
        "--venv-path",
        help="Path to the Python virtual environment.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing CLAUDE.md/AGENTS.md."),
) -> None:
    """Scaffold a vault and write host configuration files."""
    vault = Path(vault_path).expanduser().resolve()

    for d in [
        vault / ".natalie",
        vault / ".claude",
        vault / ".opencode",
        vault / "Natalie" / "personas",
        vault / "Natalie" / "Documents",
        vault / "Natalie" / "Contacts",
        vault / ".agents" / "plugins" / "natalie" / "hooks",
        vault / ".agents" / "plugins" / "natalie" / "skills" / "natalie-contact-enrichment",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    config_path = vault / "Natalie" / "config.toml"
    if not config_path.exists():
        config_path.write_text(
            _DEFAULT_CONFIG_TOML.format(persona=persona, embedding_model=DEFAULT_EMBEDDING_MODEL),
            encoding="utf-8",
        )

    dashboard = vault / "Dashboard.md"
    if not dashboard.exists():
        _dashboard_src = Path(__file__).parent / "templates" / "Dashboard.md"
        dashboard.write_text(_dashboard_src.read_text(encoding="utf-8"), encoding="utf-8")

    for _stub_name, _stub_content in [
        ("Today", "*Add your daily plan here.*\n"),
        ("Briefing", "*Add your briefing notes here.*\n"),
        ("Links", "*Add your links here.*\n"),
    ]:
        _stub = vault / "Natalie" / f"{_stub_name}.md"
        if not _stub.exists():
            _stub.write_text(_stub_content, encoding="utf-8")

    (vault / ".obsidian" / "snippets").mkdir(parents=True, exist_ok=True)
    _snippets_src = Path(__file__).parent / "snippets"
    for css in _snippets_src.glob("*.css"):
        dest = vault / ".obsidian" / "snippets" / css.name
        if not dest.exists():
            dest.write_bytes(css.read_bytes())
    snippet_names = [p.stem for p in _snippets_src.glob("*.css")]
    _merge_json(
        vault / ".obsidian" / "appearance.json",
        {"enabledCssSnippets": snippet_names},
    )

    _is_new_vault = not (vault / ".natalie" / "natalie.db").exists()
    init_db(vault)

    cfg = load_config(vault)
    claude_md = vault / "CLAUDE.md"
    if not claude_md.exists() or force:
        claude_md.write_text(render_instructions(cfg, vault, target="claude"), encoding="utf-8")
    agents_md = vault / "AGENTS.md"
    if not agents_md.exists() or force:
        agents_md.write_text(render_instructions(cfg, vault, target="agents"), encoding="utf-8")

    venv = Path(venv_path).expanduser().resolve()
    server_bin = str(venv / "bin" / "natalie-server")
    natalie_bin = str(venv / "bin" / "natalie")

    # .mcp.json — canonical Claude Code project-level MCP config (no "type" field)
    mcp_json = {
        "mcpServers": {
            "natalie": {
                "command": server_bin,
                "args": [],
            }
        }
    }
    _merge_json(vault / ".mcp.json", mcp_json)

    # .claude/settings.json — merge natalie PostToolUse hook, preserve all other hooks
    settings_path = vault / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            existing_settings: dict[str, Any] = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_settings = {}
    else:
        existing_settings = {}
    natalie_hook_entry: dict[str, Any] = {
        "matcher": "*",
        "hooks": [{"type": "command", "command": f"{natalie_bin} sync"}],
    }
    existing_hooks = existing_settings.setdefault("hooks", {})
    post_tool_use: list[Any] = existing_hooks.setdefault("PostToolUse", [])
    natalie_idx = next(
        (
            i
            for i, entry in enumerate(post_tool_use)
            if isinstance(entry, dict)
            and any(isinstance(h, dict) and "natalie" in h.get("command", "") for h in entry.get("hooks", []))
        ),
        None,
    )
    if natalie_idx is not None:
        post_tool_use[natalie_idx] = natalie_hook_entry
    else:
        post_tool_use.append(natalie_hook_entry)
    settings_path.write_text(json.dumps(existing_settings, indent=2), encoding="utf-8")

    opencode_cfg = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "natalie": {
                "type": "local",
                "command": [server_bin],
                "enabled": True,
            }
        },
    }
    # opencode.json — merge so other MCP entries are preserved
    _merge_json(vault / "opencode.json", opencode_cfg)

    hooks_cfg = {"tool.execute.after": {"command": f"{natalie_bin} sync"}}
    # .opencode/hooks.json — merge
    _merge_json(vault / ".opencode" / "hooks.json", hooks_cfg)

    # .vibe/ — Mistral Vibe
    (vault / ".vibe").mkdir(parents=True, exist_ok=True)

    vibe_config_path = vault / ".vibe" / "config.toml"
    existing_vibe_cfg: dict[str, Any] = {}
    if vibe_config_path.exists():
        try:
            with open(vibe_config_path, "rb") as f:
                existing_vibe_cfg = dict(tomllib.load(f))
        except (tomllib.TOMLDecodeError, OSError):
            pass

    if existing_vibe_cfg.get("enable_experimental_hooks"):
        enable_vibe_hooks = True
    else:
        typer.echo(
            "\nMistral Vibe supports an experimental post-agent-turn hook system (v2.9.0+).\n"
            "  Enabled:  Natalie auto-indexes the vault after every agent turn.\n"
            "  Disabled: You must run 'natalie sync' manually after Mistral Vibe\n"
            "            edits vault files for changes to appear in search results."
        )
        enable_vibe_hooks = typer.confirm("Enable experimental Mistral Vibe hooks?", default=True)

    vibe_cfg: dict[str, Any] = {
        "mcp_servers": [{"name": "natalie", "transport": "stdio", "command": server_bin}],
    }
    if enable_vibe_hooks:
        vibe_cfg["enable_experimental_hooks"] = True

    # Mistral Vibe gives the project config full precedence with no fallback
    # merge — the global ~/.vibe/config.toml is silently ignored when a project
    # config exists.  We compensate by copying the global config as the base so
    # all user settings (models, providers, mcp_servers, etc.) are preserved.
    # Layering: global → existing project config (user overrides) → natalie's additions.
    global_vibe_path = Path.home() / ".vibe" / "config.toml"
    if global_vibe_path.exists() and global_vibe_path != vibe_config_path:
        try:
            with open(global_vibe_path, "rb") as f:
                global_vibe_cfg: dict[str, Any] = dict(tomllib.load(f))
        except (tomllib.TOMLDecodeError, OSError):
            global_vibe_cfg = {}
    else:
        global_vibe_cfg = {}

    new_vibe_cfg = dict(global_vibe_cfg)
    _deep_merge_toml(new_vibe_cfg, existing_vibe_cfg)
    _deep_merge_toml(new_vibe_cfg, vibe_cfg)
    vibe_config_path.write_bytes(tomli_w.dumps(new_vibe_cfg).encode())

    if enable_vibe_hooks:
        _merge_toml(
            vault / ".vibe" / "hooks.toml",
            {
                "hooks": [
                    {"name": "natalie-sync", "type": "post_agent_turn", "command": f"{natalie_bin} sync"}
                ]
            },
        )

    # Goose — global ~/.config/goose/config.yaml (MCP extension)
    goose_config_dir = Path.home() / ".config" / "goose"
    goose_config_dir.mkdir(parents=True, exist_ok=True)
    goose_ext: dict[str, Any] = {
        "extensions": {
            "natalie": {
                "name": "natalie",
                "cmd": server_bin,
                "args": [],
                "enabled": True,
                "type": "stdio",
                "timeout": 300,
            }
        }
    }
    _merge_yaml(goose_config_dir / "config.yaml", goose_ext)

    # Goose — project plugin: plugin.json
    goose_plugin_dir = vault / ".agents" / "plugins" / "natalie"
    goose_plugin_manifest: dict[str, Any] = {
        "name": "natalie",
        "version": __version__,
        "description": "Natalie personal assistant — sync hook and skills for Goose",
    }
    (goose_plugin_dir / "plugin.json").write_text(
        json.dumps(goose_plugin_manifest, indent=2), encoding="utf-8"
    )

    # Goose — project plugin: hooks/hooks.json
    goose_hooks: dict[str, Any] = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [{"type": "command", "command": f"{natalie_bin} sync", "timeout": 30}],
                }
            ]
        }
    }
    _merge_json(goose_plugin_dir / "hooks" / "hooks.json", goose_hooks)

    # Goose — project plugin: companion skill (copy from installed package)
    skill_src = Path(__file__).parent / "skills" / "natalie-contact-enrichment" / "SKILL.md"
    skill_dst = goose_plugin_dir / "skills" / "natalie-contact-enrichment" / "SKILL.md"
    skill_dst.write_text(skill_src.read_text(encoding="utf-8"), encoding="utf-8")

    # Companion skills — copy all skills to <vault>/.agents/skills/ (shared auto-discovery path).
    # Mistral Vibe discovers from .agents/skills/; Claude Code discovers via the symlink below.
    skills_pkg = Path(__file__).parent / "skills"
    agents_skills = vault / ".agents" / "skills"
    agents_skills.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(skills_pkg.iterdir()):
        if skill_dir.is_dir():
            shutil.copytree(skill_dir, agents_skills / skill_dir.name, dirs_exist_ok=True)

    # .claude/skills → ../.agents/skills — Claude Code project-level skills auto-discovery
    claude_skills_link = vault / ".claude" / "skills"
    if claude_skills_link.is_symlink():
        claude_skills_link.unlink()
    if not claude_skills_link.exists():
        claude_skills_link.symlink_to(Path("..") / ".agents" / "skills")

    typer.echo(f"Vault initialized at: {vault}")
    if _is_new_vault:
        typer.echo(f"Next step: from {vault}, run 'natalie sync --full' to build the initial search index.")
    else:
        typer.echo(f"Vault reconfigured at: {vault}")


if __name__ == "__main__":
    app()
