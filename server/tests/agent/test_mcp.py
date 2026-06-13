"""Tolerance to unreachable MCP sources (issue #6).

The probe (`_probe_one`) is mocked so no network is touched. We assert that
`reachable_mcp_servers` keeps only the sources whose probe succeeded, logs/drops the
rest, and yields an empty toolset (never raises) when every source is unreachable.
"""

from typing import Any

import pytest
import structlog
from src.agent import mcp


class _FakeServer:
    """Stand-in for MCPServerStreamableHTTP — only `url` is used by the probe/log path."""

    def __init__(self, url: str) -> None:
        self.url = url


@pytest.fixture
def captured_logs() -> Any:
    """Capture structlog events emitted during a test (no real log output needed)."""
    events: list[dict[str, Any]] = []

    def _capture(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        events.append(dict(event_dict))
        # Drop the event so it never reaches the underlying (render-less) logger.
        raise structlog.DropEvent

    old = structlog.get_config()["processors"]
    structlog.configure(processors=[_capture])
    try:
        yield events
    finally:
        structlog.configure(processors=old)


def _patch_probe(monkeypatch: pytest.MonkeyPatch, reachable_urls: set[str]) -> None:
    async def fake_probe(server: Any, timeout: float) -> bool:
        ok = server.url in reachable_urls
        if not ok:
            # Mirror the real probe's drop log so the warning assertion stays meaningful.
            mcp.logger.warning("mcp_source_unreachable", url=server.url, error="mocked")
        return ok

    monkeypatch.setattr(mcp, "_probe_one", fake_probe)


async def test_drops_unreachable_keeps_reachable(
    monkeypatch: pytest.MonkeyPatch, captured_logs: list[dict[str, Any]]
) -> None:
    alive = _FakeServer("http://alive/mcp")
    dead = _FakeServer("http://dead/mcp")
    _patch_probe(monkeypatch, reachable_urls={alive.url})

    result = await mcp.reachable_mcp_servers([alive, dead])  # type: ignore[list-item]

    assert result == [alive]
    # The dead source was logged as unreachable, with its URL.
    unreachable = [e for e in captured_logs if e.get("event") == "mcp_source_unreachable"]
    assert any(e["url"] == dead.url for e in unreachable)
    # And a summary drop log was emitted.
    assert any(e.get("event") == "mcp_sources_dropped" and e["dropped"] == 1 for e in captured_logs)


async def test_all_unreachable_yields_empty(
    monkeypatch: pytest.MonkeyPatch, captured_logs: list[dict[str, Any]]
) -> None:
    a = _FakeServer("http://a/mcp")
    b = _FakeServer("http://b/mcp")
    _patch_probe(monkeypatch, reachable_urls=set())

    # Must not raise — an all-dead set just means "run without MCP tools".
    result = await mcp.reachable_mcp_servers([a, b])  # type: ignore[list-item]

    assert result == []
    assert any(e.get("event") == "mcp_sources_dropped" and e["dropped"] == 2 for e in captured_logs)


async def test_all_reachable_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    servers = [_FakeServer(f"http://s{i}/mcp") for i in range(3)]
    _patch_probe(monkeypatch, reachable_urls={s.url for s in servers})

    result = await mcp.reachable_mcp_servers(servers)  # type: ignore[arg-type]

    assert result == servers


async def test_no_configured_servers_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty configured set short-circuits without probing.
    called = False

    async def fake_probe(server: Any, timeout: float) -> bool:
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(mcp, "_probe_one", fake_probe)

    assert await mcp.reachable_mcp_servers([]) == []
    assert called is False


async def test_probe_one_swallows_errors() -> None:
    """A server whose context manager raises must probe as False, not propagate."""

    class _Boom:
        url = "http://boom/mcp"

        async def __aenter__(self) -> "Any":
            raise ConnectionError("refused")

        async def __aexit__(self, *args: Any) -> None:
            return None

    assert await mcp._probe_one(_Boom(), timeout=0.1) is False  # type: ignore[arg-type]
