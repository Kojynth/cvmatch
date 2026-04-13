from __future__ import annotations

import pytest

from app.utils import api_key_store


def test_get_api_key_ignores_legacy_plaintext_without_keyring(monkeypatch) -> None:
    monkeypatch.setattr(api_key_store, "_import_keyring", lambda: None)
    monkeypatch.setattr(api_key_store, "_read_legacy", lambda name: "legacy-secret")

    assert api_key_store.get_api_key("jooble_api_key") is None


def test_set_api_key_requires_secure_storage(monkeypatch) -> None:
    monkeypatch.setattr(api_key_store, "_import_keyring", lambda: None)

    with pytest.raises(api_key_store.SecureStorageUnavailableError):
        api_key_store.set_api_key("jooble_api_key", "secret")


def test_get_api_key_returns_none_when_keyring_backend_raises(monkeypatch) -> None:
    class _BrokenKeyring:
        @staticmethod
        def get_password(service, source_name):
            raise RuntimeError("backend unavailable")

    monkeypatch.setattr(api_key_store, "_import_keyring", lambda: _BrokenKeyring)

    assert api_key_store.get_api_key("jooble_api_key") is None
