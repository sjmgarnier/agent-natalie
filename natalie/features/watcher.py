from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, cast

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..db import get_db
from .memory import index_note, remove_note
from .tasks import index_tasks


class _VaultEventHandler(FileSystemEventHandler):
    def __init__(self, vault: Path, db_vault: Path) -> None:
        super().__init__()
        self._vault = vault.resolve()
        self._db_vault = db_vault
        self._local: threading.local = threading.local()

    def _db(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = get_db(self._db_vault)
        return cast(sqlite3.Connection, self._local.conn)

    def _is_vault_md(self, path: str) -> bool:
        p = Path(path).resolve()
        try:
            rel = p.relative_to(self._vault)
        except ValueError:
            return False
        return p.suffix == ".md" and not any(part.startswith(".") for part in rel.parts)

    def _index_file(self, src_path: str) -> None:
        p = Path(src_path).resolve()
        if not p.exists():
            return
        db = self._db()
        index_note(db, self._vault, p)
        index_tasks(db, self._vault, p)

    def _remove_file(self, src_path: str) -> None:
        p = Path(src_path).resolve()
        try:
            rel = p.relative_to(self._vault).as_posix()
        except ValueError:
            return
        db = self._db()
        remove_note(db, rel)
        db.execute("DELETE FROM tasks WHERE path = ?", (rel,))
        db.commit()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_vault_md(str(event.src_path)):
            try:
                self._index_file(str(event.src_path))
            except Exception:
                pass

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_vault_md(str(event.src_path)):
            try:
                self._index_file(str(event.src_path))
            except Exception:
                pass

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._is_vault_md(str(event.src_path)):
            try:
                self._remove_file(str(event.src_path))
            except Exception:
                pass

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        try:
            if self._is_vault_md(str(event.src_path)):
                self._remove_file(str(event.src_path))
            if self._is_vault_md(str(event.dest_path)):
                self._index_file(str(event.dest_path))
        except Exception:
            pass


def start_watcher(vault: Path, db_vault: Path) -> Any:
    """Start a daemon thread watching vault .md files for create/modify/delete/move events."""
    handler = _VaultEventHandler(vault, db_vault)
    observer = Observer()
    observer.schedule(handler, str(vault), recursive=True)
    observer.daemon = True
    observer.start()
    return observer
