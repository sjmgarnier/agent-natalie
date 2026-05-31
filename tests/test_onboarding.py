import pytest

from natalie.features.onboarding import get_onboarding_status, set_onboarding_complete


def test_get_onboarding_status_returns_not_completed_when_absent(db):
    status = get_onboarding_status(db)
    assert status["completed"] is False
    assert status["completed_at"] is None


def test_get_onboarding_status_is_idempotent(db):
    get_onboarding_status(db)
    status = get_onboarding_status(db)
    assert status["completed"] is False
    assert status["completed_at"] is None


def test_set_onboarding_complete_returns_completed_true(db):
    status = set_onboarding_complete(db)
    assert status["completed"] is True
    assert status["completed_at"] is not None


def test_set_onboarding_complete_persists(db):
    set_onboarding_complete(db)
    status = get_onboarding_status(db)
    assert status["completed"] is True
    assert status["completed_at"] is not None


def test_set_onboarding_complete_is_idempotent(db):
    set_onboarding_complete(db)
    second = set_onboarding_complete(db)
    assert second["completed"] is True
    assert second["completed_at"] is not None


def test_singleton_row_rejects_second_id(db):
    with pytest.raises(Exception):
        db.execute("INSERT INTO onboarding (id, completed_at) VALUES (2, NULL)")
        db.commit()
