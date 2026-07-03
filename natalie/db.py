import logging
import sqlite3
from pathlib import Path

_log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT    NOT NULL UNIQUE,
    title         TEXT,
    tags          TEXT,
    frontmatter   TEXT,
    body          TEXT,
    last_modified REAL,
    collection    TEXT    NOT NULL DEFAULT 'global',
    machine_mac   TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    title,
    body,
    content='notes',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
    INSERT INTO notes_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
END;

CREATE TABLE IF NOT EXISTS embeddings (
    note_id INTEGER PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    vector  BLOB    NOT NULL
);

CREATE TABLE IF NOT EXISTS conventions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    domain     TEXT    NOT NULL,
    rule       TEXT    NOT NULL,
    source     TEXT    NOT NULL CHECK(source IN ('explicit', 'observed')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS onboarding (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path    TEXT    UNIQUE NOT NULL,
    sha256      TEXT,
    description TEXT    NOT NULL,
    project     TEXT,
    doc_type    TEXT,
    tags        TEXT,
    filed_at    TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS document_embeddings (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    vector BLOB    NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    description,
    content='documents',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS documents_fts_insert AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, description) VALUES (new.id, new.description);
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_update AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, description)
        VALUES ('delete', old.id, old.description);
    INSERT INTO documents_fts(rowid, description) VALUES (new.id, new.description);
END;

CREATE TRIGGER IF NOT EXISTS documents_fts_delete AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, description)
        VALUES ('delete', old.id, old.description);
END;

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    NOT NULL,
    line        INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    done        INTEGER NOT NULL DEFAULT 0,
    due_date    TEXT,
    priority    TEXT,
    recurrence  TEXT,
    tags        TEXT
);

CREATE INDEX IF NOT EXISTS tasks_path_idx ON tasks(path);
CREATE UNIQUE INDEX IF NOT EXISTS tasks_path_line_idx ON tasks(path, line);

CREATE TABLE IF NOT EXISTS sync_log (
    id        INTEGER PRIMARY KEY,
    synced_at REAL    NOT NULL,
    trigger   TEXT    NOT NULL CHECK(trigger IN ('startup', 'manual'))
);
"""


def get_db(vault: Path) -> sqlite3.Connection:
    db_path = vault / ".natalie" / "natalie.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(vault: Path) -> None:
    """Create the .natalie directory and initialise the DB schema if needed."""
    (vault / ".natalie").mkdir(parents=True, exist_ok=True)
    conn = get_db(vault)
    conn.executescript(_SCHEMA)
    conn.commit()
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN tags TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            _log.exception("db migration failed: unexpected error adding tasks.tags column")
            raise
        # column already exists on existing installations
    conn.close()
