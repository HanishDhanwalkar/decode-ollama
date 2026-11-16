"""Unit tests for decode.sponsors.hook."""

import pytest

from decode.config.settings import Settings
from decode.entities import events
from decode.harness.runner import Phase
from decode.sponsors.client import SponsorClient
from decode.sponsors.hook import SponsorStateMachineHook
from decode.sponsors.rotator import SponsorRotator
from decode.sponsors.types import HarnessState, SponsorCampaign


@pytest.fixture
def mock_campaigns() -> list[SponsorCampaign]:
    return [
        SponsorCampaign(
            campaign_id="c1",
            sponsor_name="PostHog",
            tagline="Product analytics for modern developers",
        ),
        SponsorCampaign(
            campaign_id="c2",
            sponsor_name="Neon",
            tagline="Serverless Postgres for AI agents",
        ),
    ]


def test_hook_state_machine_phase_transitions(mock_campaigns):
    """Hook tracks Runner Phase transitions properly."""
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    rotator = SponsorRotator(mock_campaigns)
    hook = SponsorStateMachineHook(settings, rotator=rotator)

    assert hook.state == HarnessState.IDLE

    # IDLE -> DISPATCHING
    hook.on_phase_change(Phase.IDLE, Phase.DISPATCHING)
    assert hook.state == HarnessState.DISPATCHING

    # DISPATCHING -> RUNNING
    hook.on_phase_change(Phase.DISPATCHING, Phase.RUNNING)
    assert hook.state == HarnessState.THINKING

    # RUNNING -> IDLE
    hook.on_phase_change(Phase.RUNNING, Phase.IDLE)
    assert hook.state == HarnessState.IDLE


def test_hook_state_machine_events(mock_campaigns):
    """Hook responds to TurnStarted, ThinkingDelta, ToolCallStarted, and TurnFinished events."""
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    rotator = SponsorRotator(mock_campaigns)
    hook = SponsorStateMachineHook(settings, rotator=rotator)

    # TurnStarted
    hook.on_event(events.TurnStarted(turn_id=1, prompt="test"))
    assert hook.state == HarnessState.THINKING

    # ThinkingDelta
    hook.on_event(events.ThinkingDelta(text="reasoning..."))
    assert hook.state == HarnessState.THINKING

    # ToolCallStarted (executing)
    hook.on_event(
        events.ToolCallStarted(tool_call_id="call-1", name="bash", args='{"command": "ls"}')
    )
    assert hook.state == HarnessState.EXECUTING

    # TurnFinished -> returns to IDLE
    hook.on_event(events.TurnFinished(turn_id=1, aborted=False))
    assert hook.state == HarnessState.IDLE


def test_hook_spinner_text_idle():
    """When the runner phase is IDLE, spinner_text is empty."""
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    hook = SponsorStateMachineHook(settings)
    assert hook.spinner_text(Phase.IDLE) == ""


def test_hook_spinner_text_when_disabled():
    """When disabled via no_ads_flag, spinner_text falls back to the default message."""
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    hook = SponsorStateMachineHook(settings, no_ads_flag=True)
    assert not hook.is_enabled
    assert hook.spinner_text(Phase.RUNNING, default="working…") == "working…"


def test_hook_spinner_text_active_campaign(mock_campaigns):
    """When active, spinner_text shows a formatted sponsor tagline."""
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    rotator = SponsorRotator(
        mock_campaigns, weighted=False
    )  # Use round-robin for deterministic test
    hook = SponsorStateMachineHook(settings, rotator=rotator)

    text = hook.spinner_text(Phase.RUNNING)
    # With round-robin, first call returns first campaign
    assert "Sponsored by PostHog: Product analytics for modern developers" in text

    # Advance to next campaign via phase change
    hook.on_phase_change(Phase.IDLE, Phase.DISPATCHING)
    text2 = hook.spinner_text(Phase.RUNNING)
    # Second call returns second campaign
    assert "Sponsored by Neon: Serverless Postgres for AI agents" in text2


def test_hook_spinner_text_fallback_when_campaigns_empty():
    """When active but no campaigns are loaded, spinner_text falls back silently."""
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    rotator = SponsorRotator([])
    hook = SponsorStateMachineHook(settings, rotator=rotator)

    assert hook.spinner_text(Phase.RUNNING, default="Analyzing codebase…") == "Analyzing codebase…"


async def test_hook_background_refresh_on_turn_start():
    """Hook triggers background prefetch if endpoint is configured and cache is stale."""
    import httpx

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[{"campaign_id": "c-bg", "sponsor_name": "BgSponsor", "tagline": "Bg Tagline"}],
        )
    )
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/v1/campaigns",
            http_client=http_client,
        )
        rotator = SponsorRotator([])
        hook = SponsorStateMachineHook(settings, client=client, rotator=rotator)

        # Calling _on_turn_start schedules background refresh
        hook._on_turn_start()
        assert hook._bg_task is not None
        await hook._bg_task

        # Verify campaigns were refreshed in rotator
        assert rotator.has_campaigns
        assert rotator.current_campaign().sponsor_name == "BgSponsor"
