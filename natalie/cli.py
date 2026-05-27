import json
import sys
import typer
from pathlib import Path

from .vault import require_vault
from .config import load_config
from .db import get_db
from .generate import render_instructions

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
        None, "--version", "-V", callback=_version_callback, is_eager=True,
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
    db = get_db(vault)
    from .features.sync import sync_vault
    result = sync_vault(db, vault, config, full=full, model_name=config.memory.embedding_model)
    typer.echo(f"Synced: {result['indexed']} indexed, {result['removed']} removed, {result['embedded']} embedded.")


@app.command()
def config(
    persona: str | None = typer.Option(None, "--persona", help="Persona name to activate."),
) -> None:
    """Update vault configuration and regenerate CLAUDE.md / AGENTS.md."""
    vault = require_vault()
    cfg = load_config(vault)
    if persona:
        cfg.persona.name = persona
        config_path = vault / "Natalie" / "config.toml"
        try:
            import tomllib
            with open(config_path, "rb") as f:
                data = dict(tomllib.load(f))
        except FileNotFoundError:
            data = {}
        data.setdefault("persona", {})["name"] = persona
        import tomli_w
        config_path.write_bytes(tomli_w.dumps(data).encode())
    claude_content = render_instructions(cfg, vault, target="claude")
    agents_content = render_instructions(cfg, vault, target="agents")
    (vault / "CLAUDE.md").write_text(claude_content, encoding="utf-8")
    (vault / "AGENTS.md").write_text(agents_content, encoding="utf-8")
    typer.echo(f"Generated CLAUDE.md and AGENTS.md with persona: {cfg.persona.name}")


_DEFAULT_CONFIG_TOML = """\
[persona]
name = "{persona}"

[memory]
embedding_provider = "{embedding_provider}"
embedding_model    = "BAAI/bge-small-en-v1.5"

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

[features.sync]
tag          = "natalie"
subdirectory = "Natalie"
"""

_DASHBOARD_MD = """\
# Natalie Dashboard

Welcome to your Natalie vault.

## Today

## Open Tasks

## Recent Documents
"""


def _deep_merge(base: dict, update: dict) -> None:
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


def _merge_json(path: Path, update: dict) -> None:
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
    embedding_provider: str = typer.Option(
        "fastembed",
        "--embedding-provider",
        help="Embedding provider: fastembed, openai, or anthropic.",
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
            _DEFAULT_CONFIG_TOML.format(persona=persona, embedding_provider=embedding_provider),
            encoding="utf-8",
        )

    dashboard = vault / "Dashboard.md"
    if not dashboard.exists():
        dashboard.write_text(_DASHBOARD_MD, encoding="utf-8")

    from .db import init_db
    init_db(vault)

    from .config import load_config as _load_config
    cfg = _load_config(vault)
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

    # .claude/settings.json — hooks only; preserve existing entries
    settings = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": f"{natalie_bin} sync"}],
                }
            ]
        },
    }
    _merge_json(vault / ".claude" / "settings.json", settings)

    opencode_cfg = {
        "mcp": {
            "natalie": {
                "command": server_bin,
                "args": [],
                "enabled": True,
                "type": "local",
            }
        }
    }
    # opencode.json — merge so other MCP entries are preserved
    _merge_json(vault / "opencode.json", opencode_cfg)

    hooks_cfg = {
        "tool.execute.after": {
            "command": f"{natalie_bin} sync"
        }
    }
    # .opencode/hooks.json — merge
    _merge_json(vault / ".opencode" / "hooks.json", hooks_cfg)

    typer.echo(f"Vault initialized at: {vault}")
    typer.echo(f"Next step: run 'natalie sync --full' to build the initial search index.")


if __name__ == "__main__":
    app()
