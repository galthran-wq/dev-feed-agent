"""Live run trace: a single, self-updating status message that shows what the agent is doing.

Wired via pydantic-ai's ``event_stream_handler`` — one cross-cutting hook fires a
``FunctionToolCallEvent`` for every tool call, so no per-tool changes are needed. One ``LiveTrace``
is threaded through the run (and into sub-agents) so their steps land in the same message.

Medium-agnostic: ``LiveTrace`` owns the step buffer + throttle; a ``TraceSink`` (e.g. Telegram's
edit-in-place message) does the actual rendering. Kept here, separate from any channel, so the
event-stream plumbing lives in one place."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Protocol

import structlog

if TYPE_CHECKING:
    from collections.abc import AsyncIterable, Awaitable, Callable

logger = structlog.get_logger()

# Last-N newest-first so the message can't grow unbounded (the ask: "limit 10 order by desc").
_MAX_STEPS = 10
# Telegram rate-limits edits to one message; coalesce bursts of parallel tool calls to ~this gap.
_MIN_RENDER_INTERVAL = 0.8
_LABEL_MAX = 90

Status = str  # "running" | "done" | "error"


class TraceSink(Protocol):
    """Where a trace renders. ``render`` must create-or-update ONE message (idempotent per call)."""

    async def render(self, steps: list[str], status: Status) -> None: ...


def _args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _first(a: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _mcp_label(tool_name: str) -> str:
    """MCP tools are named by their server; group them by source keyword, else prettify the name."""
    n = tool_name.lower()
    for needle, src in (
        ("arxiv", "arXiv"),
        ("reddit", "Reddit"),
        ("hacker", "Hacker News"),
        ("_hn", "Hacker News"),
        ("perplexity", "Perplexity"),
        ("hugging", "HuggingFace"),
        ("hf_", "HuggingFace"),
        ("model", "HuggingFace"),
        ("dataset", "HuggingFace"),
    ):
        if needle in n:
            return f"Searching {src}"
    return tool_name.replace("_", " ").strip().capitalize()


def _label_for(tool_name: str, raw_args: Any, prefix: str) -> str | None:
    """Turn a tool call into one readable English line, or None to skip it from the trace."""
    a = _args(raw_args)

    if tool_name == "search_github_repositories":
        q = _first(a, "query")
        label = f'Searching GitHub repos: "{q}"' if q else "Searching GitHub repos"
    elif tool_name == "find_github_issues":
        lbl = _first(a, "label") or "good first issue"
        lang = _first(a, "language")
        label = f"Searching GitHub issues: {lbl}" + (f" ({lang})" if lang else "")
    elif tool_name == "list_my_repos":
        label = "Reading your repos"
    elif tool_name == "list_my_starred":
        label = "Reading your stars"
    elif tool_name == "scan_repo_dependencies":
        label = "Scanning dependencies"
    elif tool_name == "read_profile":
        label = "Reading your profile"
    elif tool_name == "update_profile_section":
        sec = _first(a, "section", "name")
        label = f"Updating profile: {sec}" if sec else "Updating profile"
    elif tool_name == "list_recently_shown":
        label = "Checking already-shown items"
    elif tool_name == "record_feed_items":
        items = a.get("items")
        n = len(items) if isinstance(items, list) else None
        label = f"Recording {n} picks" if n is not None else "Recording feed picks"
    elif tool_name == "get_feed_schedule":
        label = "Checking feed schedule"
    elif tool_name in ("add_memory", "edit_memory", "delete_memory", "get_memory", "list_memories", "search_memories"):
        label = "Consulting memory"
    elif tool_name == "send_message":
        label = "Sending a message"
    elif tool_name == "spawn_subagent":
        kind = _first(a, "kind") or "sub-agent"
        task = _first(a, "task")
        label = f"→ {kind}: {task}" if task else f"→ delegating to {kind}"
    else:
        label = _mcp_label(tool_name)

    line = f"{prefix}{label}".strip()
    return line[: _LABEL_MAX - 1] + "…" if len(line) > _LABEL_MAX else line


class LiveTrace:
    """Accumulates step lines (newest first, capped) and pushes the current view to a sink.

    Concurrency-safe: sub-agents run their own event streams against this same instance, so
    ``step``/``finish`` may be called from several tasks at once — a lock serializes renders
    (and the single Telegram edit). Renders are throttled but ``finish`` always force-flushes,
    so the final state (incl. the last steps skipped by the throttle) is never lost."""

    def __init__(self, sink: TraceSink) -> None:
        self._sink = sink
        self._steps: deque[str] = deque(maxlen=_MAX_STEPS)
        self._lock = asyncio.Lock()
        self._last_render = 0.0

    async def step(self, label: str) -> None:
        async with self._lock:
            self._steps.appendleft(label)
            if time.monotonic() - self._last_render >= _MIN_RENDER_INTERVAL:
                await self._render("running")

    async def finish(self, ok: bool) -> None:
        async with self._lock:
            # No tool calls happened (e.g. the model answered directly) — never opened a trace, so
            # don't post a lone, contentless status bubble before the real reply.
            if not self._steps:
                return
            await self._render("done" if ok else "error")

    async def _render(self, status: Status) -> None:
        self._last_render = time.monotonic()
        try:
            await self._sink.render(list(self._steps), status)
        except Exception as exc:
            # The trace is observability, never load-bearing — a failed edit must not break the run.
            logger.warning("trace_render_failed", error=str(exc))

    def make_handler(self, prefix: str = "") -> Callable[[Any, AsyncIterable[Any]], Awaitable[None]]:
        """An ``event_stream_handler`` that records each tool call. ``prefix`` attributes
        sub-agent steps to their kind (e.g. ``"feed_gather ▸ "``)."""

        async def handler(ctx: Any, stream: AsyncIterable[Any]) -> None:
            async for event in stream:
                # Duck-typed (not isinstance) so a pydantic-ai event-class rename can't silently
                # turn the whole trace off; we only ever read .part.tool_name / .part.args.
                if getattr(event, "event_kind", None) != "function_tool_call":
                    continue
                try:
                    part = getattr(event, "part", None)
                    name = getattr(part, "tool_name", None)
                    if not name:
                        continue
                    label = _label_for(name, getattr(part, "args", None), prefix)
                    if label:
                        await self.step(label)
                except Exception as exc:
                    # pydantic-ai propagates a handler exception and ABORTS the run — the trace must
                    # never do that. Swallow per-event so a labeling bug can't kill the agent.
                    logger.warning("trace_handler_failed", error=str(exc))

        return handler
