import pytest

from natalie.utils import safe_join


def test_safe_join_allows_normal_path(tmp_path):
    result = safe_join(tmp_path, "subdir/file.md")
    assert result == (tmp_path / "subdir" / "file.md").resolve()


def test_safe_join_raises_on_absolute_path(tmp_path):
    with pytest.raises(ValueError, match="escapes base directory"):
        safe_join(tmp_path, "/etc/passwd")


def test_safe_join_raises_on_traversal(tmp_path):
    with pytest.raises(ValueError, match="escapes base directory"):
        safe_join(tmp_path, "../../etc/passwd")


def test_capture_task_raises_on_traversal(vault):
    from natalie.features.tasks import capture_task

    with pytest.raises(ValueError, match="escapes base directory"):
        capture_task(vault, "../../etc/crontab", "malicious task")


def test_complete_task_raises_on_traversal(vault):
    from natalie.features.tasks import complete_task

    with pytest.raises(ValueError, match="escapes base directory"):
        complete_task(vault, "../../etc/passwd", "some task")


def test_file_document_raises_on_traversal(vault, config, db):
    from natalie.features.documents import file_document

    with pytest.raises(ValueError, match="escapes base directory"):
        file_document(vault, config, db, "../../../etc/evil.txt", "a description")


def test_contact_path_raises_on_traversal(vault, config):
    from natalie.features.contacts import get_contact

    with pytest.raises(ValueError, match="escapes base directory"):
        get_contact(vault, config, "../../etc/passwd")


def test_safe_join_rejects_natalie_config(tmp_path):
    (tmp_path / ".natalie").mkdir()
    with pytest.raises(ValueError, match="protected internal file"):
        safe_join(tmp_path, ".natalie/config.toml")


def test_safe_join_rejects_natalie_db(tmp_path):
    (tmp_path / ".natalie").mkdir()
    with pytest.raises(ValueError, match="protected internal file"):
        safe_join(tmp_path, ".natalie/natalie.db")


def test_safe_join_allows_natalie_entries(tmp_path):
    (tmp_path / ".natalie").mkdir()
    result = safe_join(tmp_path, ".natalie/entries/somemac/note-abcd1234.md")
    assert result == (tmp_path / ".natalie" / "entries" / "somemac" / "note-abcd1234.md").resolve()


def test_capture_task_raises_on_natalie_internal_target(vault):
    from natalie.features.tasks import capture_task

    with pytest.raises(ValueError, match="protected internal file"):
        capture_task(vault, ".natalie/config.toml", "malicious task")


def test_complete_task_raises_on_natalie_internal_target(vault):
    from natalie.features.tasks import complete_task

    with pytest.raises(ValueError, match="protected internal file"):
        complete_task(vault, ".natalie/natalie.db", "some task")


def test_update_task_raises_on_natalie_internal_target(vault):
    from natalie.features.tasks import update_task

    with pytest.raises(ValueError, match="protected internal file"):
        update_task(vault, ".natalie/config.toml", "some task", new_text="edited task")


def test_memory_store_default_path_still_writes_into_natalie_entries(vault, db, monkeypatch):
    """memory_store's own default path (no explicit `path` arg) must keep working."""
    import threading

    import natalie.server as srv
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", NatalieConfig())

    result = srv.memory_store(content="hello")

    assert result["stored"] is True
    assert result["path"].startswith(".natalie/entries/")


def test_memory_store_rejects_explicit_natalie_internal_path(vault, db, monkeypatch):
    import threading

    import natalie.server as srv
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", NatalieConfig())

    with pytest.raises(ValueError, match="protected internal file"):
        srv.memory_store(content="malicious", path=".natalie/natalie.db")


def test_note_write_indexes_canonical_path(vault, db, monkeypatch):
    """note_write must store the resolved path so it matches what sync_vault would store.

    A path with '..' segments must be resolved before being passed to index_note,
    otherwise the DB row has a non-canonical key that sync_vault's deletion pass
    won't recognise and will never clean up.
    """
    import threading

    import natalie.server as srv
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", NatalieConfig())

    # Create subdirectory so the path with '..' is valid inside the vault
    (vault / "notes").mkdir(exist_ok=True)
    path_with_dotdot = "notes/../notes/canon.md"

    srv.note_write(path=path_with_dotdot, content="hello")

    # The DB must store the canonical relative path, not the raw one
    rows = db.execute("SELECT path FROM notes WHERE body = 'hello'").fetchall()
    assert len(rows) == 1
    assert ".." not in rows[0]["path"]
