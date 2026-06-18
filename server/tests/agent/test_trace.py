"""LiveTrace: step buffer (cap + newest-first), status flush, tool→label mapping, event handler."""

from dataclasses import dataclass
from typing import Any

import pytest
from src.agent.trace import LiveTrace, _label_for


class _RecordingSink:
    """Captures every render frame so tests can assert what the live message would show."""

    def __init__(self) -> None:
        self.frames: list[tuple[list[str], str]] = []

    async def render(self, steps: list[str], status: str) -> None:
        self.frames.append((list(steps), status))


async def test_steps_are_newest_first_and_capped_at_ten() -> None:
    sink = _RecordingSink()
    trace = LiveTrace(sink)
    for i in range(13):
        await trace.step(f"step {i}")
    await trace.finish(ok=True)

    last_steps, status = sink.frames[-1]
    assert status == "done"
    assert last_steps[0] == "step 12"  # newest first
    assert len(last_steps) == 10  # older steps dropped
    assert "step 2" not in last_steps and "step 1" not in last_steps


async def test_finish_failure_flushes_error_status_with_latest_steps() -> None:
    sink = _RecordingSink()
    trace = LiveTrace(sink)
    await trace.step("Searching GitHub")
    await trace.finish(ok=False)

    steps, status = sink.frames[-1]
    assert status == "error"
    assert steps == ["Searching GitHub"]  # the step still shows even though the throttle skipped it


@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        ("search_github_repositories", {"query": "rust async"}, 'Searching GitHub repos: "rust async"'),
        (
            "find_github_issues",
            {"label": "good first issue", "language": "Rust"},
            "Searching GitHub issues: good first issue (Rust)",
        ),
        ("record_feed_items", {"items": [1, 2, 3]}, "Recording 3 picks"),
        ("read_profile", {}, "Reading your profile"),
        ("send_message", {"text": "hi"}, "Sending a message"),
        ("spawn_subagent", {"kind": "feed_gather", "task": "arXiv RAG"}, "→ feed_gather: arXiv RAG"),
    ],
)
def test_label_for_known_tools(tool: str, args: dict[str, Any], expected: str) -> None:
    assert _label_for(tool, args, "") == expected


def test_label_for_parses_json_string_args() -> None:
    # pydantic-ai may hand us args as a JSON string, not a dict.
    assert _label_for("search_github_repositories", '{"query": "k8s"}', "") == 'Searching GitHub repos: "k8s"'


def test_label_for_mcp_tool_groups_by_source_and_applies_prefix() -> None:
    assert _label_for("arxiv_search_papers", {}, "feed_gather ▸ ") == "feed_gather ▸ Searching arXiv"


async def test_handler_records_function_tool_calls_only() -> None:
    sink = _RecordingSink()
    trace = LiveTrace(sink)
    handler = trace.make_handler()

    @dataclass
    class _Part:
        tool_name: str
        args: dict[str, Any]

    @dataclass
    class _Event:
        event_kind: str
        part: Any

    async def stream() -> Any:
        yield _Event("function_tool_call", _Part("read_profile", {}))
        yield _Event("part_start", None)  # not a tool call → ignored
        yield _Event("function_tool_call", _Part("search_github_repositories", {"query": "vit"}))

    await handler(object(), stream())
    await trace.finish(ok=True)

    steps, _ = sink.frames[-1]
    assert steps == ['Searching GitHub repos: "vit"', "Reading your profile"]  # newest first, non-tool skipped
