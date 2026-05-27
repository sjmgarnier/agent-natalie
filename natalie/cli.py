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
embedding_provider = "fastembed"
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


@app.command()
def init(
    vault_path: str = typer.Argument(..., help="Path to the Obsidian vault (created if missing)."),
    persona: str = typer.Option("natalie", "--persona", help="Persona to activate."),
    venv_path: str = typer.Option(
        str(Path.home() / ".natalie" / ".venv"),
        "--venv-path",
        help="Path to the Python virtual environment.",
    ),
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
        config_path.write_text(_DEFAULT_CONFIG_TOML.format(persona=persona), encoding="utf-8")

    dashboard = vault / "Dashboard.md"
    if not dashboard.exists():
        dashboard.write_text(_DASHBOARD_MD, encoding="utf-8")

    from .db import init_db
    init_db(vault)

    from .config import load_config as _load_config
    cfg = _load_config(vault)
    claude_content = render_instructions(cfg, vault, target="claude")
    agents_content = render_instructions(cfg, vault, target="agents")
    (vault / "CLAUDE.md").write_text(claude_content, encoding="utf-8")
    (vault / "AGENTS.md").write_text(agents_content, encoding="utf-8")

    venv = Path(venv_path).expanduser().resolve()
    server_bin = str(venv / "bin" / "natalie-server")
    natalie_bin = str(venv / "bin" / "natalie")
    settings = {
        "mcpServers": {
            "natalie": {
                "command": server_bin,
                "args": [],
                "type": "stdio",
            }
        },
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": f"{natalie_bin} sync"}],
                }
            ]
        },
    }
    (vault / ".claude" / "settings.json").write_text(
        json.dumps(settings, indent=2), encoding="utf-8"
    )

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
    (vault / "opencode.json").write_text(
        json.dumps(opencode_cfg, indent=2), encoding="utf-8"
    )

    hooks_cfg = {
        "tool.execute.after": {
            "command": f"{natalie_bin} sync"
        }
    }
    (vault / ".opencode" / "hooks.json").write_text(
        json.dumps(hooks_cfg, indent=2), encoding="utf-8"
    )

    typer.echo(f"Vault initialized at: {vault}")
    typer.echo(f"Next step: run 'natalie sync --full' to build the initial search index.")


if __name__ == "__main__":
    app()
