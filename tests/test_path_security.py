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

    with pytest.raises(ValueError):
        capture_task(vault, "../../etc/crontab", "malicious task")


def test_complete_task_raises_on_traversal(vault):
    from natalie.features.tasks import complete_task

    with pytest.raises(ValueError):
        complete_task(vault, "../../etc/passwd", "some task")


def test_file_document_raises_on_traversal(vault, config, db):
    from natalie.features.documents import file_document

    with pytest.raises(ValueError):
        file_document(vault, config, db, "../../../etc/evil.txt", "a description")


def test_contact_path_raises_on_traversal(vault, config):
    from natalie.features.contacts import get_contact

    with pytest.raises(ValueError):
        get_contact(vault, config, "../../etc/passwd")


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
