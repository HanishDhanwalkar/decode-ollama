"""Build the ``decode`` Pydantic AI agent on the configured **LLM Provider**.

The provider seam lives in :mod:`decode.agent.llm_providers`; everything else in
:func:`build_agent` is provider-agnostic, and the loop owns all runtime behaviour. Tools come from
the flat :mod:`decode.tools.registry` (the single source of truth); ``output_type=[str,
DeferredToolRequests]`` wires the permission gate's deferred-tool seam. See ADR-0002 §1-2 and ADR-0005.
"""

from __future__ import annotations

import logging

from pydantic_ai import Agent, DeferredToolRequests, RunContext
from pydantic_ai.agent import AgentRetries

from decode.agent import llm_providers
from decode.agent.deps import AgentDeps
from decode.config.settings import settings
from decode.memory.service import assemble_memory
from decode.skills.catalog import assemble_skills_catalog
from decode.tools.agent import set_main_agent
from decode.tools.registry import register_tools

logger = logging.getLogger(__name__)

# Static base system prompt; memory-file injection is layered on top by the instructions hook.
_BASE_INSTRUCTIONS = (
    "You are Decode, a terminal coding agent that helps a developer in their working "
    "directory. You are concise and precise: answer directly, prefer running the work over "
    "describing it, and never invent file contents or command output you have not seen. "
    "When you do not have a tool for something yet, say so plainly rather than pretending."
)


def build_agent(*, model: str | None = None) -> Agent[AgentDeps, str | DeferredToolRequests]:
    """Construct the agent on the configured LLM Provider + register the flat tools (ADR-0002 §1-3,7).

    One build for every caller — the REPL and the headless runner alike (ADR-0019 §1). The provider
    key always comes from ``Settings`` (ADR-0015 §4). ``model`` is the Model Override: it overrides
    only the active provider's model id, never the provider.
    """
    built_model = llm_providers._build_model(model=model)
    agent: Agent[AgentDeps, str | DeferredToolRequests] = Agent(
        built_model,
        deps_type=AgentDeps,
        output_type=[str, DeferredToolRequests],
        # Per-category retry budgets, one dict since pydantic-ai 2.x (``AgentRetries``):
        # - output: Gemini 2.5 sometimes returns empty/thinking-only turns after a tool call; the
        #   default budget of 1 then aborts real multi-turn runs. Give it a few attempts.
        # - tools: tools coach the model with ModelRetry (edit "old_string not found", grep "no
        #   matches"); the default per-tool budget of 1 turns the SECOND consecutive nag into
        #   UnexpectedModelBehavior, killing the whole turn. The counter only resets when the tool
        #   *succeeds* — a re-read between two mis-aimed edits doesn't help — so give real headroom.
        retries=AgentRetries(output=3, tools=5),
    )
    register_tools(agent)
    _register_instructions(agent)
    # Subagent-spawn seam (ADR-0013 §6): the ``agent`` tool re-enters this Agent for every Explore
    # child, reusing its model + client; one ``agent.override(model=…)`` covers parent + children.
    set_main_agent(agent)
    logger.debug("built agent on llm_provider=%s", settings.llm_provider)
    return agent


def _register_instructions(agent: Agent[AgentDeps, str | DeferredToolRequests]) -> None:
    """Assemble the whole system prompt as ONE instructions block (ADR-0002 §8, ADR-0003 §6-7, ADR-0004 §1,§9).

    Four parts (base, persona prompt, memory, Skills Catalog) join into a SINGLE instructions
    source because ``OpenAIChatModel`` emits one ``system`` message per source and strict
    OpenAI-compatible servers (vLLM behind Modal, some OpenRouter models) reject more than one.
    It stays a dynamic per-run hook so persona/memory/skills are read fresh each turn with no
    agent rebuild; empty parts are dropped.
    """

    @agent.instructions
    def assemble_instructions(ctx: RunContext[AgentDeps]) -> str:
        # Memory + skills are HARNESS artifacts: they read harness_home (the launch cwd), not
        # cwd — in a sandbox mode cwd is the Workspace (ADR-0012 §6).
        harness_home = ctx.deps.harness_home or ctx.deps.cwd
        parts = (
            _BASE_INSTRUCTIONS,
            ctx.deps.active_agent.prompt,
            assemble_memory(harness_home),
            assemble_skills_catalog(harness_home),
        )
        return "\n\n".join(part for part in parts if part)
