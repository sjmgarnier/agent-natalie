import sqlite3
from pathlib import Path

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
"""


def get_db(vault: Path) -> sqlite3.Connection:
    db_path = vault / ".natalie" / "natalie.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(vault: Path) -> sqlite3.Connection:
    (vault / ".natalie").mkdir(parents=True, exist_ok=True)
    conn = get_db(vault)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
