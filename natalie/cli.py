import typer

from .vault import require_vault
from .config import load_config
from .db import get_db

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


if __name__ == "__main__":
    app()
