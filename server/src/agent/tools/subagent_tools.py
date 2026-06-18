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
    quick checks and to verify what it reports. A sub-agent cannot message the user — YOU relay
    or act on what it returns.

    kind: which specialist to run.
        - "profile_build": investigate the user's GitHub footprint and fill their interest
          profile (call when read_profile is empty).
        - "feed_gather": gather fresh feed candidates for ONE slice described by `task` (a
          source, optionally a focus/angle) and return them as a compact list. For a feed, spawn
          SEVERAL of these in PARALLEL (one per source, or multiple angles per source) in a
          single step, then consolidate their results yourself.
    task: the instruction for this sub-agent. For feed_gather, make it focused, e.g.
        "GitHub: good-first-issues in Rust async runtimes" or "arXiv: recent retrieval/RAG papers".
    session_id: pass back the id returned by an earlier call to resume that same sub-agent
        (it keeps its full memory); omit to start fresh.
    """
    # Lazy import: tools are imported by agents; subagents imports agents — avoid the cycle.
    from src.agent.subagents import run_subagent

    result, sid = await run_subagent(
        kind,
        user_id=ctx.deps.user_id,
        github_token=ctx.deps.github_token,
        github_username=ctx.deps.github_username,
        task=task,
        session_id=session_id,
        tracer=ctx.deps.tracer,  # share the live trace so the sub-agent's steps show in the same view
    )
    return f"sub-agent '{kind}' (session_id={sid}) returned:\n{result}"


SUBAGENT_TOOLS = [spawn_subagent]
