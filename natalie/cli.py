import typer

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


if __name__ == "__main__":
    app()
