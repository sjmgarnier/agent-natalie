from __future__ import annotations

import sqlite3
from pathlib import Path

from ..config import NatalieConfig
from .memory import embed_notes, index_note, remove_note


def sync_vault(
    db: sqlite3.Connection,
    vault: Path,
    config: NatalieConfig,
    full: bool = False,
    model_name: str = "BAAI/bge-small-en-v1.5",
) -> dict:
    """Index new/changed vault notes; optionally remove stale entries.

    Returns: {indexed: int, removed: int, embedded: int}
    """
    md_files = {
        p for p in vault.rglob("*.md")
        if not any(part.startswith(".") for part in p.relative_to(vault).parts)
    }

    indexed = 0
    for p in md_files:
        index_note(db, vault, p)
        indexed += 1

    removed = 0
    if full:
        indexed_paths = {p.relative_to(vault).as_posix() for p in md_files}
        stored_paths = {
            r["path"]
            for r in db.execute(
                "SELECT path FROM notes WHERE machine_mac IS NULL"
            ).fetchall()
        }
        for stale in stored_paths - indexed_paths:
            remove_note(db, stale)
            removed += 1

    embedded = embed_notes(db, model_name=model_name)
    return {"indexed": indexed, "removed": removed, "embedded": embedded}
