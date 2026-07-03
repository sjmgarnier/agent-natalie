import sqlite3

import pytest

from natalie.db import get_db, init_db


def test_init_db_creates_natalie_db_file(tmp_path):
    (tmp_path / ".natalie").mkdir()
    init_db(tmp_path)
    assert (tmp_path / ".natalie" / "natalie.db").exists()


def test_init_db_creates_notes_table(vault):
    conn = get_db(vault)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "notes" in tables


def test_init_db_creates_fts_table(vault):
    conn = get_db(vault)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "notes_fts" in tables


def test_init_db_creates_all_tables(vault):
    conn = get_db(vault)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"notes", "embeddings", "conventions", "onboarding"}.issubset(tables)
    assert "machines" not in tables


def test_init_db_creates_onboarding_table(vault):
    conn = get_db(vault)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "onboarding" in tables


def test_notes_fts_triggers_on_insert(vault):
    conn = get_db(vault)
    conn.execute(
        "INSERT INTO notes (path, title, body, collection) VALUES (?, ?, ?, ?)",
        ("/test.md", "Test Note", "Hello world", "global"),
    )
    conn.commit()
    rows = conn.execute("SELECT * FROM notes_fts WHERE notes_fts MATCH 'hello'").fetchall()
    assert len(rows) == 1


def test_init_db_is_idempotent(vault):
    init_db(vault)  # second call on already-initialized vault
    conn = get_db(vault)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "notes" in tables


class _FlakyConnection(sqlite3.Connection):
    """Connection subclass that simulates a non-'duplicate column' failure on the tags migration."""

    def execute(self, sql, *args, **kwargs):  # type: ignore[override]
        if isinstance(sql, str) and sql.strip().startswith("ALTER TABLE tasks ADD COLUMN tags"):
            raise sqlite3.OperationalError("database is locked")
        return super().execute(sql, *args, **kwargs)


def test_init_db_reraises_unexpected_operational_error_on_migration(tmp_path, monkeypatch):
    """Only 'duplicate column' should be swallowed; any other OperationalError must propagate."""
    (tmp_path / ".natalie").mkdir()
    original_connect = sqlite3.connect

    def fake_connect(*args, **kwargs):
        kwargs["factory"] = _FlakyConnection
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fake_connect)

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        init_db(tmp_path)


# ---------------------------------------------------------------------------
# Thread safety — C7 + C3
# ---------------------------------------------------------------------------


def test_get_db_sets_busy_timeout(tmp_path):
    """C7: get_db() must set busy_timeout so concurrent callers wait instead of failing instantly."""
    (tmp_path / ".natalie").mkdir()
    conn = get_db(tmp_path)
    result = conn.execute("PRAGMA busy_timeout").fetchone()
    assert result[0] == 5000
    conn.close()


def test_init_db_creates_tasks_table(vault):
    conn = get_db(vault)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "tasks" in tables


def test_tasks_table_has_expected_columns(vault):
    conn = get_db(vault)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    assert cols == {"id", "path", "line", "text", "done", "due_date", "priority", "recurrence", "tags"}


def test_tasks_path_index_exists(vault):
    conn = get_db(vault)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    assert "tasks_path_idx" in {r[0] for r in rows}


def test_get_db_connection_usable_from_non_creating_thread(tmp_path):
    """C3: connections must work from any thread — FastMCP dispatches tool handlers to a thread pool."""
    import threading

    (tmp_path / ".natalie").mkdir()
    conn = get_db(tmp_path)
    errors: list[Exception] = []

    def query_from_worker() -> None:
        try:
            conn.execute("SELECT 1").fetchone()
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=query_from_worker)
    t.start()
    t.join()
    conn.close()

    assert errors == [], f"Cross-thread DB use raised: {errors}"
