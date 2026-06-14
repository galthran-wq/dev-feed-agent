"""``EncryptedString``: opt-in Fernet-at-rest column.

Opt-in (no ``TOKEN_ENCRYPTION_KEY`` -> plaintext) to mirror the rest of the app. The key is read lazily
at bind/result time so a missing key never breaks model import and tests can monkeypatch it. On decrypt
we fall back to the raw value rather than raising, so legacy/plaintext rows survive once a key is set.
"""

import base64
import binascii
from functools import lru_cache

import structlog
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator

logger = structlog.get_logger()


@lru_cache(maxsize=8)
def _fernet_for(key: str) -> Fernet:
    """Cached so we don't re-parse the key per bind/result; keyed by string so a changed key yields a fresh one."""
    return Fernet(key.encode())


def _looks_like_fernet(value: str) -> bool:
    """Distinguishes genuine legacy plaintext (pass through silently) from Fernet-shaped-but-undecryptable
    (key mismatch/rotation — worth warning). 0x80 is the Fernet version marker."""
    try:
        return base64.urlsafe_b64decode(value.encode())[:1] == b"\x80"
    except (binascii.Error, ValueError):
        return False


def _current_key() -> str:
    # Lazy import so we don't pin a settings instance at import time and tests can monkeypatch the key.
    from src.core.config import settings

    return settings.token_encryption_key


class EncryptedString(TypeDecorator[str]):
    """A ``String`` column Fernet-encrypted at rest. Unbounded (TEXT) because ciphertext is longer than plaintext."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        key = _current_key()
        if not key:
            # Encryption disabled -> store plaintext unchanged.
            return value
        return _fernet_for(key).encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        key = _current_key()
        if not key:
            # Encryption disabled -> assume plaintext.
            return value
        try:
            return _fernet_for(key).decrypt(value.encode()).decode()
        except InvalidToken:
            # Legacy plaintext or wrong/rotated key. Never raise (a hard-failing read is worse), so return raw;
            # warn if it looks Fernet-shaped so a silent rotation mismatch stays observable.
            if _looks_like_fernet(value):
                logger.warning("encrypted_token_undecryptable", reason="key_mismatch_or_rotation")
            return value
        except Exception:
            # Honor the never-raise contract for any unexpected decode error on arbitrary legacy content.
            logger.warning("encrypted_token_decrypt_error")
            return value
