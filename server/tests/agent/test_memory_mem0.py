"""Unit tests for the mem0 wiring (recall, sentinel-strip, background extract, tools). mem0 is
mocked — these never touch the network."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, SystemPromptPart, TextPart, UserPromptPart
from src.agent import runtime
from src.agent.tools import memory_crud


class FakeMem:
    """Stand-in for mem0's AsyncMemory: records add() calls, returns a canned search result."""

    def __init__(self, search_result: object = None) -> None:
        self.added: list[dict[str, object]] = []
        self._search_result = search_result if search_result is not None else {"results": []}

    async def search(self, query: str, filters: dict[str, str], top_k: int) -> object:
        self.searched = {"query": query, "filters": filters, "top_k": top_k}
        return self._search_result

    async def add(self, messages: list[dict[str, str]], user_id: str) -> None:
        self.added.append({"messages": messages, "user_id": user_id})


# --- _prime_history: strips system parts AND any leaked recall block ---------------------------


def test_prime_history_strips_system_and_recall_block() -> None:
    sentinel_block = f"{runtime._FACTS_SENTINEL}\n## Relevant facts about the user\n- likes Rust"
    history = [
        ModelRequest(parts=[SystemPromptPart(content="stale system"), UserPromptPart(content="hello")]),
        ModelResponse(parts=[TextPart(content="hi there")]),
        ModelRequest(parts=[UserPromptPart(content=sentinel_block)]),  # a leaked recall block
    ]

    primed = runtime._prime_history(history, "FRESH SYSTEM")

    # Leads with exactly the fresh system prompt.
    assert isinstance(primed[0].parts[0], SystemPromptPart)
    assert primed[0].parts[0].content == "FRESH SYSTEM"

    user_contents = [p.content for m in primed for p in getattr(m, "parts", []) if isinstance(p, UserPromptPart)]
    assert "hello" in user_contents  # real user turn survives
    assert sentinel_block not in user_contents  # leaked recall block is gone — no accumulation
    # Only the one fresh system part exists.
    systems = [p for m in primed for p in getattr(m, "parts", []) if isinstance(p, SystemPromptPart)]
    assert len(systems) == 1


# --- _append_facts: ephemeral tail placement --------------------------------------------------


def test_append_facts_appends_at_tail() -> None:
    primed = [ModelRequest(parts=[SystemPromptPart(content="sys")])]
    out = runtime._append_facts(primed, "FACTS")
    assert len(out) == 2
    assert isinstance(out[-1].parts[0], UserPromptPart)
    assert out[-1].parts[0].content == "FACTS"


def test_append_facts_noop_when_none() -> None:
    primed = [ModelRequest(parts=[SystemPromptPart(content="sys")])]
    assert runtime._append_facts(primed, None) is primed


# --- _recall ----------------------------------------------------------------------------------


async def test_recall_renders_block_with_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMem({"results": [{"memory": "likes Rust"}, {"memory": "avoids crypto"}]})
    monkeypatch.setattr(runtime, "get_mem0", lambda: fake)

    uid = uuid4()
    block = await runtime._recall(uid, "what's new in rust")

    assert block is not None
    assert block.startswith(runtime._FACTS_SENTINEL)
    assert "- likes Rust" in block
    assert "- avoids crypto" in block
    assert fake.searched["filters"] == {"user_id": str(uid)}


async def test_recall_handles_list_results(monkeypatch: pytest.MonkeyPatch) -> None:
    # Some mem0 versions return a bare list rather than {"results": [...]}.
    fake = FakeMem([{"memory": "uses asyncio"}])
    monkeypatch.setattr(runtime, "get_mem0", lambda: fake)
    block = await runtime._recall(uuid4(), "async")
    assert block is not None
    assert "- uses asyncio" in block


async def test_recall_none_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "get_mem0", lambda: None)
    assert await runtime._recall(uuid4(), "anything") is None


async def test_recall_none_on_empty_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "get_mem0", lambda: FakeMem({"results": [{"memory": "x"}]}))
    assert await runtime._recall(uuid4(), "   ") is None


async def test_recall_none_when_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "get_mem0", lambda: FakeMem({"results": []}))
    assert await runtime._recall(uuid4(), "query") is None


# --- _remember (background extraction) --------------------------------------------------------


async def _drain_bg() -> None:
    await asyncio.gather(*list(runtime._bg_tasks))


async def test_remember_schedules_add(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMem()
    monkeypatch.setattr(runtime, "get_mem0", lambda: fake)
    uid = uuid4()

    runtime._remember(uid, "I love Rust", "Nice, here are rust repos")
    await _drain_bg()

    assert len(fake.added) == 1
    call = fake.added[0]
    assert call["user_id"] == str(uid)
    roles = [m["role"] for m in call["messages"]]  # type: ignore[index]
    assert roles == ["user", "assistant"]


async def test_remember_noop_when_assistant_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMem()
    monkeypatch.setattr(runtime, "get_mem0", lambda: fake)
    runtime._remember(uuid4(), "I love Rust", "   ")
    await _drain_bg()
    assert fake.added == []


async def test_remember_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "get_mem0", lambda: None)
    runtime._remember(uuid4(), "user", "assistant")  # must not raise
    await _drain_bg()


# --- tools: add_memory / search_memory --------------------------------------------------------


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(deps=SimpleNamespace(user_id=uuid4()))


async def test_add_memory_routes_to_mem0(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMem()
    monkeypatch.setattr(memory_crud, "get_mem0", lambda: fake)
    out = await memory_crud.add_memory(_ctx(), "remember I use NixOS")
    assert out == "Saved."
    assert fake.added[0]["messages"] == [{"role": "user", "content": "remember I use NixOS"}]


async def test_add_memory_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_crud, "get_mem0", lambda: None)
    out = await memory_crud.add_memory(_ctx(), "x")
    assert "not configured" in out


async def test_search_memory_returns_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeMem({"results": [{"id": "m1", "memory": "uses Kafka"}]})
    monkeypatch.setattr(memory_crud, "get_mem0", lambda: fake)
    out = await memory_crud.search_memory(_ctx(), "kafka")
    assert '"uses Kafka"' in out
    assert '"m1"' in out


async def test_search_memory_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_crud, "get_mem0", lambda: None)
    assert await memory_crud.search_memory(_ctx(), "x") == "[]"
