"""Round-trip tests for the EncryptedString column on UserModel.github_access_token.

conftest uses in-memory SQLite. We monkeypatch ``settings.token_encryption_key``
so the TypeDecorator (which reads the key at bind/result time) sees a key or not.
We assert on the *raw* stored bytes via a type-bypassing ``text()`` query to prove
encryption actually happens at rest, and re-read through the ORM to prove decryption.
"""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.core import config
from src.models.postgres.users import UserModel
from src.repositories.users import UserRepository

TOKEN = "gho_super_secret_token_value_123"


async def _raw_stored_token(session: AsyncSession, github_id: str) -> str | None:
    """Read the column as a plain string, bypassing EncryptedString result processing."""
    result = await session.execute(
        text("SELECT github_access_token FROM users WHERE github_id = :gid"),
        {"gid": github_id},
    )
    return result.scalar_one()


async def test_token_round_trips_and_is_encrypted_at_rest(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(config.settings, "token_encryption_key", key)

    repo = UserRepository(db_session)
    user, created = await repo.upsert_github_user(
        github_id="42", username="octocat", access_token=TOKEN, avatar_url=None
    )
    assert created is True

    user_id = user.id

    # Stored value (raw) must be ciphertext, not the plaintext token.
    raw = await _raw_stored_token(db_session, "42")
    assert raw is not None
    assert raw != TOKEN
    # And it must be a valid Fernet token decryptable with the configured key.
    assert Fernet(key.encode()).decrypt(raw.encode()).decode() == TOKEN

    # Re-read through the ORM (force a DB round-trip) -> decrypted transparently.
    db_session.expunge_all()
    reloaded = (await db_session.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one()
    assert reloaded.github_access_token == TOKEN


async def test_plaintext_when_no_key(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "token_encryption_key", "")

    repo = UserRepository(db_session)
    user, _ = await repo.upsert_github_user(github_id="7", username="hubot", access_token=TOKEN, avatar_url=None)

    user_id = user.id

    # No key -> stored as plaintext unchanged.
    raw = await _raw_stored_token(db_session, "7")
    assert raw == TOKEN

    db_session.expunge_all()
    reloaded = (await db_session.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one()
    assert reloaded.github_access_token == TOKEN


async def test_legacy_plaintext_passes_through_with_key_set(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a pre-encryption row: write plaintext directly into the column.
    user = UserModel(github_id="99", github_username="legacy")
    db_session.add(user)
    await db_session.commit()
    user_id = user.id
    await db_session.execute(
        text("UPDATE users SET github_access_token = :tok WHERE github_id = :gid"),
        {"tok": TOKEN, "gid": "99"},
    )
    await db_session.commit()

    # Now enable encryption and read -> the non-Fernet value should pass through, not raise.
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(config.settings, "token_encryption_key", key)

    db_session.expunge_all()
    reloaded = (await db_session.execute(select(UserModel).where(UserModel.id == user_id))).scalar_one()
    assert reloaded.github_access_token == TOKEN
