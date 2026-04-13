"""Security and secret-store facade."""

from .secret_store import (
    SecureStorageUnavailableError,
    get_api_key,
    set_api_key,
)

__all__ = ["SecureStorageUnavailableError", "get_api_key", "set_api_key"]
