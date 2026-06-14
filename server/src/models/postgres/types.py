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
    """Build (and cache) a Fernet for a given key. Cached so we don't re-parse
    the key on every bind/result; keyed by the key string so a changed key
    (e.g. in tests) yields a fresh instance."""
    return Fernet(key.encode())


def _looks_like_fernet(value: str) -> bool:
    """Heuristic: does ``value`` have the shape of a Fernet token? A Fernet token
    is urlsafe-base64 whose first decoded byte is the version marker ``0x80``.
    Used only to distinguish "genuine legacy plaintext" (pass through silently)
    from "Fernet-shaped but undecryptable" (key mismatch/rotation — worth warning)."""
    try:
        return base64.urlsafe_b64decode(value.encode())[:1] == b"\x80"
    except (binascii.Error, ValueError):
        return False


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
            # Either genuine legacy plaintext (written before encryption / while the
            # key was disabled) or a Fernet token we can't decrypt (wrong key — e.g.
            # the key was rotated). We must not raise (the column is opaque to callers
            # and hard-failing a read is worse), so return the raw value — but if it
            # *looks* like a Fernet token, surface a warning so a silent rotation
            # mismatch is observable instead of handing out ciphertext-as-token.
            if _looks_like_fernet(value):
                logger.warning("encrypted_token_undecryptable", reason="key_mismatch_or_rotation")
            return value
        except Exception:
            # Defensive: honor the never-raise contract for any unexpected decode
            # error on arbitrary legacy content.
            logger.warning("encrypted_token_decrypt_error")
            return value
