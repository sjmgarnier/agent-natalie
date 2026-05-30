import json
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
import typer

from .config import load_config
from .db import init_db
from .features.memory import DEFAULT_EMBEDDING_MODEL
from .generate import render_instructions
from .vault import require_vault

app = typer.Typer(
    name="natalie",
    help="Natalie — personal assistant CLI",
    add_completion=False,
)

__version__ = "0.1.0"


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
    db = init_db(vault)
    from .features.sync import sync_vault

    result = sync_vault(db, vault, full=full, model_name=config.memory.embedding_model)
    typer.echo(
        f"Synced: {result['indexed']} indexed, {result['removed']} removed, {result['embedded']} embedded."
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

    # .claude/settings.json — always replace hooks to prevent duplicate accumulation
    settings_path = vault / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            existing_settings: dict[str, Any] = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_settings = {}
    else:
        existing_settings = {}
    existing_settings["hooks"] = {
        "PostToolUse": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": f"{natalie_bin} sync"}],
            }
        ]
    }
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

    typer.echo(f"Vault initialized at: {vault}")
    typer.echo(f"Next step: from {vault}, run 'natalie sync --full' to build the initial search index.")


if __name__ == "__main__":
    app()
