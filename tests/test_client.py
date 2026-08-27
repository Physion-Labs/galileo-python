"""Construction, and the two things a caller gets wrong first."""

from __future__ import annotations

import pytest

from physionlabs import AuthenticationError, Galileo


def test_no_key_refuses_to_construct(monkeypatch):
    monkeypatch.delenv("GALILEO_API_KEY", raising=False)
    with pytest.raises(ValueError, match="No API key"):
        Galileo()


def test_key_can_come_from_the_environment(monkeypatch):
    # So it need not be written into a source file, which is how a key ends up in
    # somebody's git history.
    monkeypatch.setenv("GALILEO_API_KEY", "gk_live_env")
    with Galileo() as galileo:
        assert galileo.evaluations and galileo.videos and galileo.account


def test_errors_are_importable_and_are_exceptions():
    # Catching them by class is the whole reason they exist.
    error = AuthenticationError(
        status=401, type="authentication_error", code="invalid_api_key", message="nope"
    )
    assert isinstance(error, Exception)
    assert error.status == 401
    assert "invalid_api_key" in str(error)
