from src.services.notifier import _chunks


def test_chunks_preserves_blank_lines() -> None:
    # Blank lines (paragraph separators) must survive — they're content, not nothing.
    assert _chunks("\nabc") == ["\nabc"]
    assert _chunks("a\n\nb") == ["a\n\nb"]


def test_chunks_respects_limit_and_splits_long_lines() -> None:
    text = "line1\n" + "x" * 25 + "\nline3"
    chunks = _chunks(text, limit=10)
    assert all(len(c) <= 10 for c in chunks)
    # No content lost: the 25 x's all survive across chunks.
    assert "".join(chunks).count("x") == 25


def test_chunks_empty_string() -> None:
    assert _chunks("") == [""]
