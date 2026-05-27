import pytest
from pathlib import Path
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


def test_file_document_raises_on_traversal(vault, config):
    from natalie.features.documents import file_document
    with pytest.raises(ValueError):
        file_document(vault, config, "../../../etc/evil.txt", "content")


def test_retrieve_document_raises_on_traversal(vault, config):
    from natalie.features.documents import retrieve_document
    with pytest.raises(ValueError):
        retrieve_document(vault, config, "../../etc/passwd")


def test_contact_path_raises_on_traversal(vault, config):
    from natalie.features.contacts import get_contact
    with pytest.raises(ValueError):
        get_contact(vault, config, "../../etc/passwd")
