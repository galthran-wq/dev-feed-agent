"""Custom SQLAlchemy column types.

``EncryptedString`` transparently Fernet-encrypts a string on the way into the
database and decrypts it on the way out. It is **opt-in**, mirroring the rest of
this app: when no ``TOKEN_ENCRYPTION_KEY`` is configured the value is stored and
returned unchanged (plaintext). The key is read from ``settings`` lazily at
bind/result time (not import time) so it can be configured/monkeypatched after
the model class is defined, and so a missing key never breaks model import.

Backward compatibility: on decrypt we *try* Fernet and fall back to returning the
raw value if it isn't a valid Fernet token. This lets pre-encryption (legacy
plaintext) rows — or rows written while the key was disabled — pass through even
once a key is set, instead of raising ``InvalidToken``.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


@lru_cache(maxsize=8)
def _fernet_for(key: str) -> Fernet:
    """Build (and cache) a Fernet for a given key. Cached so we don't re-parse
    the key on every bind/result; keyed by the key string so a changed key
    (e.g. in tests) yields a fresh instance."""
    return Fernet(key.encode())


def _current_key() -> str:
    # Imported lazily so the type module doesn't pin a settings instance at
    # import time and so monkeypatching ``settings.token_encryption_key`` works.
    from src.core.config import settings

    return settings.token_encryption_key


class EncryptedString(TypeDecorator[str]):
    """A ``String`` column whose value is Fernet-encrypted at rest.

    Transparent to repositories: bind/result processing handles the crypto, so
    callers read/write plain ``str``. Stored as text; ciphertext is longer than
    the plaintext, so the underlying column is unbounded ``String`` (TEXT).
    """

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
            # Not a Fernet token (legacy plaintext / written while key disabled).
            # Tolerate it and return as-is rather than raising.
            return value
