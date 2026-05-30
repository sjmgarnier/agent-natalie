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
    assert {"notes", "embeddings", "conventions"}.issubset(tables)
    assert "machines" not in tables


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
