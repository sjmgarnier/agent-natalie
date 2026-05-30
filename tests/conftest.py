import pytest

from natalie.config import load_config
from natalie.db import get_db, init_db


@pytest.fixture
def vault(tmp_path):
    """Minimal vault for testing: .natalie/ directory + initialized DB."""
    (tmp_path / ".natalie").mkdir()
    (tmp_path / "Natalie").mkdir()
    (tmp_path / "Natalie" / "personas").mkdir()
    (tmp_path / "Natalie" / "Documents").mkdir()
    (tmp_path / "Natalie" / "Contacts").mkdir()
    init_db(tmp_path)
    return tmp_path


@pytest.fixture
def config(vault):
    return load_config(vault)


@pytest.fixture
def db(vault):
    return get_db(vault)
