from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlalchemy.ext.asyncio import AsyncSession
from src.agent import agents, subagents
from src.agent.tools import BASE_TOOLS, MAIN_TOOLS
from src.agent.tools.messaging_tools import send_message
from src.agent.tools.subagent_tools import spawn_subagent
from src.models.postgres.users import UserModel
from src.repositories.profiles import ProfileRepository
from src.repositories.subagent_sessions import SubagentSessionRepository


def _trace_json(text: str) -> bytes:
    msgs = [
        ModelRequest(parts=[UserPromptPart(content="task")]),
        ModelResponse(parts=[TextPart(content=text)]),
    ]
    return ModelMessagesTypeAdapter.dump_json(msgs)


# --- SubagentSessionRepository -------------------------------------------------------------


async def test_create_mints_id_and_empty_trace(db_session: AsyncSession, test_user: UserModel) -> None:
    repo = SubagentSessionRepository(db_session)
    sid = await repo.create(test_user.id, "profile_build")
    assert sid is not None
    assert await repo.load(sid) == []


async def test_save_overwrites_and_load_roundtrips(db_session: AsyncSession, test_user: UserModel) -> None:
    repo = SubagentSessionRepository(db_session)
    sid = await repo.create(test_user.id, "profile_build")

    await repo.save(sid, _trace_json("first"))
    first = await repo.load(sid)
    assert len(first) == 2  # request + response, intact

    # save is overwrite, not append
    await repo.save(sid, _trace_json("second"))
    second = await repo.load(sid)
    assert len(second) == 2


async def test_load_unknown_session_is_empty(db_session: AsyncSession) -> None:
    assert await SubagentSessionRepository(db_session).load(uuid4()) == []


# --- run_subagent (always owns its own session) --------------------------------------------


class _FakeResult:
    def __init__(self, output: str) -> None:
        self.output = output

    def all_messages_json(self) -> bytes:
        return _trace_json(self.output)


class _FakeAgent:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

    async def __aenter__(self) -> "_FakeAgent":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def run(self, task: str, message_history: list | None = None, deps: object = None) -> _FakeResult:
        self._captured["task"] = task
        self._captured["history"] = message_history or []
        self._captured["deps"] = deps
        return _FakeResult("Profile built: loves rust and retrieval.")


class _FakeSessionCtx:
    """Async-cm that hands run_subagent the test session and leaves it open (conftest owns it)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def _fake_make(monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession) -> dict:
    captured: dict = {}

    async def fake_make_subagent(prompt_file: str, model_name: str) -> _FakeAgent:
        captured["prompt_file"] = prompt_file
        captured["model_name"] = model_name
        return _FakeAgent(captured)

    monkeypatch.setattr(agents, "make_subagent", fake_make_subagent)
    # Force the sub-agent's "own" session to be the test session.
    monkeypatch.setattr(subagents, "AsyncSessionLocal", lambda: _FakeSessionCtx(db_session))
    return captured


async def test_run_subagent_new_session_marks_built_and_persists(
    _fake_make: dict, db_session: AsyncSession, test_user: UserModel
) -> None:
    result, sid = await subagents.run_subagent(
        "profile_build",
        user_id=test_user.id,
        github_token=None,
        github_username="octocat",
    )
    assert "loves rust" in result
    assert _fake_make["prompt_file"] == "profile_builder.md"
    assert "octocat" in _fake_make["task"]  # default task interpolates the username
    assert _fake_make["deps"].channel is None  # sub-agents never get a channel
    # full trace persisted to the minted session
    assert len(await SubagentSessionRepository(db_session).load(UUID(sid))) == 2
    # post-step ran on the sub-agent's own session
    assert await ProfileRepository(db_session).is_built(test_user.id) is True


async def test_run_subagent_resume_passes_history(
    _fake_make: dict, db_session: AsyncSession, test_user: UserModel
) -> None:
    repo = SubagentSessionRepository(db_session)
    sid = await repo.create(test_user.id, "profile_build")
    await repo.save(sid, _trace_json("earlier work"))

    await subagents.run_subagent(
        "profile_build",
        user_id=test_user.id,
        github_token=None,
        github_username="octocat",
        session_id=str(sid),
    )
    # resumed: the prior trace was loaded and replayed into the run
    assert len(_fake_make["history"]) == 2


async def test_run_subagent_unknown_kind_is_graceful(test_user: UserModel) -> None:
    result, _sid = await subagents.run_subagent(
        "nope",
        user_id=test_user.id,
        github_token=None,
        github_username=None,
    )
    assert "no such sub-agent" in result


async def test_feed_gather_kind_registered() -> None:
    spec = subagents._REGISTRY.get("feed_gather")
    assert spec is not None and spec.prompt_file == "feed_gather.md"


# --- wiring: only the main agent may message or spawn --------------------------------------


def test_today_note_grounds_the_real_date() -> None:
    from datetime import UTC, datetime

    from src.agent.agents import _today_note

    note = _today_note()
    assert datetime.now(UTC).strftime("%Y-%m-%d") in note  # real date, not invented
    assert "Never guess, invent, or advance" in note


def test_main_only_tools_are_excluded_from_subagents() -> None:
    # send_message: only the main agent talks to the user.
    assert send_message in MAIN_TOOLS
    assert send_message not in BASE_TOOLS
    # spawn_subagent: anti-recursion — a sub-agent can't spawn.
    assert spawn_subagent in MAIN_TOOLS
    assert spawn_subagent not in BASE_TOOLS
