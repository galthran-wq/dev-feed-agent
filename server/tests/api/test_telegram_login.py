import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.models.postgres.users import UserModel
from src.repositories.connections import ConnectionRepository
from src.services import github_oauth
from src.services import telegram as tg


def _enable_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "github_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "csecret")


def test_tg_link_token_roundtrip() -> None:
    tok = github_oauth.issue_tg_link_token("12345")
    assert github_oauth.read_tg_link_token(tok) == "12345"
    assert github_oauth.read_tg_link_token("garbage") is None


def test_state_carries_tg_chat() -> None:
    s = github_oauth.issue_state(tg_chat="999")
    assert github_oauth.verify_state(s) is True
    assert github_oauth.state_tg_chat(s) == "999"
    # A plain (web) login carries no chat.
    assert github_oauth.state_tg_chat(github_oauth.issue_state()) is None


async def test_link_chat_to_user_links_and_is_idempotent(db_session: AsyncSession, test_user: UserModel) -> None:
    repo = ConnectionRepository(db_session)
    assert await repo.link_chat_to_user(test_user.id, "chat-1") is True
    conn = await repo.get_by_user_id(test_user.id)
    assert conn is not None and conn.telegram_chat_id == "chat-1"
    # same user, same chat → still fine
    assert await repo.link_chat_to_user(test_user.id, "chat-1") is True


async def test_link_chat_repoints_same_user(db_session: AsyncSession, test_user: UserModel) -> None:
    # Logging in from a new chat moves delivery there (latest wins, one chat per user).
    repo = ConnectionRepository(db_session)
    assert await repo.link_chat_to_user(test_user.id, "chat-a") is True
    assert await repo.link_chat_to_user(test_user.id, "chat-b") is True
    conn = await repo.get_by_user_id(test_user.id)
    assert conn is not None and conn.telegram_chat_id == "chat-b"


async def test_link_chat_refuses_other_user(
    db_session: AsyncSession, test_user: UserModel, superuser: UserModel
) -> None:
    repo = ConnectionRepository(db_session)
    assert await repo.link_chat_to_user(test_user.id, "chat-9") is True
    # a different account cannot steal a chat already linked elsewhere
    assert await repo.link_chat_to_user(superuser.id, "chat-9") is False


async def test_send_login_prompt_builds_signed_button(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_oauth(monkeypatch)
    monkeypatch.setattr(settings, "app_base_url", "https://devfeed.fyi")

    sent: dict = {}

    class FakeBot:
        async def send_message(self, chat_id: str, text: str, reply_markup: object = None, **_: object) -> None:
            sent["chat_id"] = chat_id
            sent["markup"] = reply_markup

    monkeypatch.setattr(tg, "get_bot", lambda: FakeBot())
    await tg._send_login_prompt("777")

    assert sent["chat_id"] == "777"
    url = sent["markup"].inline_keyboard[0][0].url
    assert url.startswith("https://devfeed.fyi/api/auth/github/login?tg=")
    # the button's token round-trips back to this chat id
    token = url.split("tg=", 1)[1]
    assert github_oauth.read_tg_link_token(token) == "777"


async def test_typing_indicator_sends_chat_action(monkeypatch: pytest.MonkeyPatch) -> None:
    actions: list[tuple[str, str]] = []

    class FakeBot:
        async def send_chat_action(self, chat_id: str, action: str) -> None:
            actions.append((chat_id, action))

    monkeypatch.setattr(tg, "get_bot", lambda: FakeBot())
    async with tg._typing("777"):
        await asyncio.sleep(0.05)  # let the keeper fire once
    assert actions and actions[0] == ("777", "typing")


async def test_callback_links_telegram_chat(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_oauth(monkeypatch)

    async def _fake_exchange(code: str) -> str:
        return "gh-token"

    async def _fake_user(token: str) -> github_oauth.GithubUser:
        return github_oauth.GithubUser(github_id="42", username="octocat", avatar_url=None)

    async def _noop_send(self: object, text: str) -> None:  # avoid a real Telegram call in the bg task
        return None

    monkeypatch.setattr(github_oauth, "exchange_code", _fake_exchange)
    monkeypatch.setattr(github_oauth, "fetch_github_user", _fake_user)
    monkeypatch.setattr("src.agent.channels.telegram.TelegramChannel.send", _noop_send)

    state = github_oauth.issue_state(tg_chat="55501")
    client.cookies.set(github_oauth.STATE_COOKIE_NAME, github_oauth.state_cookie_value(state))
    resp = await client.get(f"/api/auth/github/callback?code=the-code&state={state}", follow_redirects=False)
    assert resp.status_code in (302, 307)

    user = (await db_session.execute(select(UserModel).where(UserModel.github_id == "42"))).scalar_one()
    conn = await ConnectionRepository(db_session).get_by_user_id(user.id)
    assert conn is not None and conn.telegram_chat_id == "55501"
