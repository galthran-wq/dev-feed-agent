"""The single, generic sub-agent spawn tool — the main agent's one lever for delegation.
(The function docstring below is the tool description the LLM sees — keep it.)"""

from pydantic_ai import RunContext
from src.agent.deps import AgentDeps


async def spawn_subagent(
    ctx: RunContext[AgentDeps], kind: str, task: str | None = None, session_id: str | None = None
) -> str:
    """Delegate heavy or multi-step work to a specialized sub-agent and get a short result back.

    Use this to keep your own context lean — the sub-agent does the deep investigation in its
    own session; only its summary returns to you. You still have all your direct tools for
    quick checks and to verify what it reports.

    kind: which specialist to run. Currently: "profile_build" — investigates the user's GitHub
        footprint and fills in their interest profile (call this when read_profile is empty).
    task: optional override of the default instruction for that kind.
    session_id: pass back the id returned by an earlier call to resume that same sub-agent
        (it keeps its full memory); omit to start fresh.
    """
    # Lazy import: tools are imported by agents; subagents imports agents — avoid the cycle.
    from src.agent.subagents import run_subagent

    # NOTE: must not hold ctx.deps.db_lock here — run_subagent reuses it (non-reentrant) and the
    # sub-agent's own tools acquire it. This tool does no direct DB work, so it doesn't.
    result, sid = await run_subagent(
        kind,
        session=ctx.deps.session,
        user_id=ctx.deps.user_id,
        github_token=ctx.deps.github_token,
        github_username=ctx.deps.github_username,
        channel=ctx.deps.channel,
        task=task,
        session_id=session_id,
        parent_db_lock=ctx.deps.db_lock,
    )
    return f"sub-agent '{kind}' (session_id={sid}) returned:\n{result}"


SUBAGENT_TOOLS = [spawn_subagent]
