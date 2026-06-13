"""Sanitize agent message history before it is persisted for replay.

Chat and the scheduled feed share one persisted message history (``agent_messages``),
replayed via ``message_history=``. Both runs store the *raw* results of external tools
(GitHub issue bodies, Reddit/HN posts, arXiv text). Replaying those raw payloads into
later authenticated chat turns — where the agent also has ``update_profile_section`` and
every source tool — amplifies prompt-injection (#5) and causes mode-bleed between the feed
and the conversation.

This module truncates large tool-*result* payloads before they are written to storage,
keeping tool *calls* and assistant/user text intact. Crucially it does **not** drop any
parts: pydantic-ai requires every ``ToolCallPart`` to be paired with a matching
``ToolReturnPart`` (same ``tool_call_id``) for valid replay, so we only shrink the
*content*, leaving a short placeholder. The live run still sees the full tool output —
only what gets persisted for future replay is trimmed.
"""

from dataclasses import replace

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolReturnPart,
)

_TRUNC_PREFIX = "[tool result truncated from history: {n} chars]"


def _stringify(content: object) -> str:
    """Best-effort string form of a tool-result content (str or structured)."""
    if isinstance(content, str):
        return content
    return str(content)


def _truncate(text: str, max_chars: int) -> str:
    """Return a placeholder for ``text`` capped at ``max_chars``.

    ``max_chars <= 0`` strips to the placeholder only; otherwise the first ``max_chars``
    characters are kept followed by the placeholder noting the original length.
    """
    placeholder = _TRUNC_PREFIX.format(n=len(text))
    if max_chars <= 0:
        return placeholder
    return f"{text[:max_chars]}\n{placeholder}"


def sanitize_messages_for_storage(messages: list[ModelMessage], max_chars: int) -> list[ModelMessage]:
    """Return copies of ``messages`` with oversized tool-result payloads truncated.

    Each ``ToolReturnPart.content`` (and ``RetryPromptPart`` string content) whose stringified
    length exceeds ``max_chars`` is replaced with a short placeholder, preserving ``tool_name``
    and ``tool_call_id`` so the call/return pairing stays valid for replay. Everything else —
    ``TextPart``, ``ToolCallPart``, ``UserPromptPart``, ``SystemPromptPart``, ``ModelResponse``,
    timestamps, etc. — is preserved verbatim. ``max_chars <= 0`` strips matching payloads to the
    placeholder only.

    Parts are immutable-style dataclasses, so we build new instances via ``dataclasses.replace``
    rather than mutating in place.
    """
    sanitized: list[ModelMessage] = []
    for message in messages:
        # Only ModelRequest carries tool-result / retry parts; ModelResponse holds the
        # assistant's text + tool *calls*, which we keep verbatim.
        if not isinstance(message, ModelRequest):
            sanitized.append(message)
            continue

        new_parts = []
        changed = False
        for part in message.parts:
            if isinstance(part, ToolReturnPart):
                text = _stringify(part.content)
                if len(text) > max_chars or max_chars <= 0:
                    new_parts.append(replace(part, content=_truncate(text, max_chars)))
                    changed = True
                    continue
            elif isinstance(part, RetryPromptPart) and isinstance(part.content, str):
                if len(part.content) > max_chars or max_chars <= 0:
                    new_parts.append(replace(part, content=_truncate(part.content, max_chars)))
                    changed = True
                    continue
            new_parts.append(part)

        sanitized.append(replace(message, parts=new_parts) if changed else message)
    return sanitized
