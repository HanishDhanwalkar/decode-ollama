"""Unit tests for decode.sponsors.types."""

import pytest

from decode.sponsors.types import (
    FORBIDDEN_METADATA_KEYS,
    ClientMetadata,
    HarnessState,
    SponsorCampaign,
)


def test_client_metadata_construction_and_to_dict():
    """ClientMetadata captures anonymized platform attributes and serializes cleanly."""
    meta = ClientMetadata(
        client_version="0.2.0",
        os_type="linux",
        python_version="3.12",
    )
    d = meta.to_dict()
    assert d == {
        "client_version": "0.2.0",
        "os_type": "linux",
        "python_version": "3.12",
    }


def test_client_metadata_validation_types():
    """ClientMetadata rejects non-string values."""
    with pytest.raises(TypeError, match="must be a str"):
        ClientMetadata(client_version=123, os_type="linux", python_version="3.12")  # type: ignore[arg-type]


def test_client_metadata_validation_length():
    """ClientMetadata rejects abnormally long payloads (preventing data stuffing)."""
    with pytest.raises(ValueError, match="exceeds maximum allowed length"):
        ClientMetadata(client_version="a" * 101, os_type="linux", python_version="3.12")


def test_forbidden_metadata_keys_definition():
    """Verify that FORBIDDEN_METADATA_KEYS covers code, files, prompts, and credentials."""
    critical_forbidden = {
        "prompt",
        "prompt_text",
        "code",
        "diff",
        "git_diff",
        "file_content",
        "path",
        "api_key",
        "secret",
        "env",
    }
    assert critical_forbidden.issubset(FORBIDDEN_METADATA_KEYS)


def test_sponsor_campaign_format_tagline_with_distinct_name():
    """SponsorCampaign formats tagline with 'Sponsored by <name>: <tagline>'."""
    campaign = SponsorCampaign(
        campaign_id="c1",
        sponsor_name="Datadog",
        tagline="Monitor LLM latency and token costs in real time",
    )
    assert (
        campaign.format_tagline()
        == "Sponsored by Datadog: Monitor LLM latency and token costs in real time"
    )


def test_sponsor_campaign_format_tagline_when_already_prefixed():
    """SponsorCampaign formats cleanly when tagline already starts with sponsor name."""
    campaign = SponsorCampaign(
        campaign_id="c2",
        sponsor_name="Neon",
        tagline="Neon serverless Postgres for AI agents",
    )
    assert campaign.format_tagline() == "Sponsored: Neon serverless Postgres for AI agents"


def test_sponsor_campaign_format_tagline_single_line_guarantee():
    """SponsorCampaign ensures multiline text is squashed into a single line."""
    campaign = SponsorCampaign(
        campaign_id="c3",
        sponsor_name="Warp",
        tagline="Fast terminal built for teams.\nWith AI built-in.\r\nCollaborative workflows.",
    )
    tagline = campaign.format_tagline()
    assert "\n" not in tagline
    assert "\r" not in tagline
    assert (
        tagline
        == "Sponsored by Warp: Fast terminal built for teams. With AI built-in. Collaborative workflows."
    )


def test_harness_state_enum_values():
    """HarnessState contains the expected states."""
    assert HarnessState.IDLE.value == "idle"
    assert HarnessState.DISPATCHING.value == "dispatching"
    assert HarnessState.THINKING.value == "thinking"
    assert HarnessState.EXECUTING.value == "executing"
