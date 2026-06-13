"""Approximate token counting for bounding replayed history.

Uses tiktoken's ``cl100k_base`` — model-agnostic enough for a budget heuristic (the
agent runs against various OpenRouter models). Counting the serialized JSON slightly
over-counts vs the real message tokens, which is the safe direction for a budget.
"""

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _encoder() -> Any:
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Token count for ``text``. Falls back to a ~chars/4 heuristic if the tiktoken
    vocab can't load (e.g. offline) — this is only a budget, so it must never raise
    and disable history/feed/chat."""
    try:
        return len(_encoder().encode(text))
    except Exception:
        return len(text) // 4
