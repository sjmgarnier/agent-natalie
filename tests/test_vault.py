import pytest

from natalie.vault import find_vault, require_vault


def test_find_vault_finds_db_at_given_path(tmp_path):
    db_dir = tmp_path / ".natalie"
    db_dir.mkdir()
    (db_dir / "natalie.db").touch()
    assert find_vault(tmp_path) == tmp_path


def test_find_vault_walks_up_from_subdirectory(tmp_path):
    (tmp_path / ".natalie").mkdir()
    (tmp_path / ".natalie" / "natalie.db").touch()
    deep = tmp_path / "sub" / "sub2"
    deep.mkdir(parents=True)
    assert find_vault(deep) == tmp_path


def test_find_vault_returns_none_when_not_found(tmp_path):
    assert find_vault(tmp_path) is None


def test_require_vault_raises_when_not_found(tmp_path):
    with pytest.raises(RuntimeError, match="No Natalie vault found"):
        require_vault(tmp_path)


def test_require_vault_returns_path_when_found(tmp_path):
    (tmp_path / ".natalie").mkdir()
    (tmp_path / ".natalie" / "natalie.db").touch()
    assert require_vault(tmp_path) == tmp_path
