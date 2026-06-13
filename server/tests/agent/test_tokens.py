import pytest
from src.agent import tokens


def test_count_tokens_basic() -> None:
    assert tokens.count_tokens("hello world") > 0


def test_count_tokens_falls_back_when_encoder_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> object:
        raise RuntimeError("offline: no tiktoken vocab")

    monkeypatch.setattr(tokens, "_encoder", boom)
    # ~chars/4 heuristic, and crucially never raises.
    assert tokens.count_tokens("abcdefgh") == 2
