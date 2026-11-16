"""Unit tests for decode.sponsors.rotator."""

from decode.sponsors.rotator import SponsorRotator
from decode.sponsors.types import SponsorCampaign


def test_rotator_empty_campaigns():
    """Rotator returns fallback when no campaigns are configured."""
    rotator = SponsorRotator([])
    assert not rotator.has_campaigns
    assert rotator.current_campaign() is None
    assert rotator.current_tagline(fallback="working…") == "working…"
    assert rotator.advance() is None


def test_rotator_single_campaign():
    """Rotator with 1 campaign always returns that campaign."""
    camp = SponsorCampaign(campaign_id="1", sponsor_name="Supabase", tagline="Build in a weekend")
    rotator = SponsorRotator([camp])
    assert rotator.has_campaigns
    assert rotator.current_campaign() == camp
    assert rotator.current_tagline() == "Sponsored by Supabase: Build in a weekend"
    assert rotator.advance() == camp


def test_rotator_advance_cycles_through_campaigns():
    """Explicit advance() cycles campaigns sequentially and wraps."""
    c1 = SponsorCampaign(campaign_id="1", sponsor_name="A", tagline="Tagline A")
    c2 = SponsorCampaign(campaign_id="2", sponsor_name="B", tagline="Tagline B")
    c3 = SponsorCampaign(campaign_id="3", sponsor_name="C", tagline="Tagline C")

    rotator = SponsorRotator([c1, c2, c3])
    assert rotator.current_campaign() == c1

    # Advance to next
    assert rotator.advance() == c2
    assert rotator.current_campaign() == c2

    assert rotator.advance() == c3
    assert rotator.current_campaign() == c3

    # Wraps back to 1
    assert rotator.advance() == c1
    assert rotator.current_campaign() == c1


def test_rotator_time_based_rotation(monkeypatch):
    """Rotator steps to next campaign after rotation_interval_s has elapsed."""
    c1 = SponsorCampaign(campaign_id="1", sponsor_name="A", tagline="Tagline A")
    c2 = SponsorCampaign(campaign_id="2", sponsor_name="B", tagline="Tagline B")

    fake_time = 100.0
    monkeypatch.setattr("time.monotonic", lambda: fake_time)

    rotator = SponsorRotator([c1, c2], rotation_interval_s=5.0)
    assert rotator.current_campaign() == c1

    # Advance simulated time past interval
    fake_time += 5.1
    assert rotator.current_campaign() == c2


def test_rotator_update_campaigns():
    """Updating campaigns refreshes list and resets index if out of range."""
    c1 = SponsorCampaign(campaign_id="1", sponsor_name="A", tagline="Tagline A")
    c2 = SponsorCampaign(campaign_id="2", sponsor_name="B", tagline="Tagline B")

    rotator = SponsorRotator([c1, c2])
    rotator.advance()  # index = 1

    new_c = [SponsorCampaign(campaign_id="3", sponsor_name="C", tagline="Tagline C")]
    rotator.update_campaigns(new_c)
    assert rotator.current_campaign() == new_c[0]
