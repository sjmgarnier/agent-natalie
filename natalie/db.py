# Stub — DB schema implemented in a later task
from pathlib import Path


def init_db(vault_path: Path) -> None:
    """Create the .natalie directory if needed. Full schema setup in a later task."""
    db_dir = vault_path / ".natalie"
    db_dir.mkdir(exist_ok=True)


def get_db(vault_path: Path):
    raise NotImplementedError("natalie.db not yet implemented")
