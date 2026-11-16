"""Campaign rotator for presenting 1-line developer sponsor taglines.

Rotates smoothly across campaigns on a time or turn interval while maintaining
developer flow state. Strictly 1-line text with zero interruptions.
"""

from __future__ import annotations

import time

from decode.sponsors.types import SponsorCampaign


class SponsorRotator:
    """Rotates active sponsor campaigns on a configurable interval."""

    def __init__(
        self,
        campaigns: list[SponsorCampaign] | None = None,
        rotation_interval_s: float = 8.0,
    ) -> None:
        self._campaigns: list[SponsorCampaign] = list(campaigns) if campaigns else []
        self._index: int = 0
        self._last_rotation_time: float = time.monotonic()
        self.rotation_interval_s = rotation_interval_s

    def update_campaigns(self, campaigns: list[SponsorCampaign]) -> None:
        """Update the active campaign list."""
        self._campaigns = list(campaigns)
        if self._index >= len(self._campaigns):
            self._index = 0

    @property
    def has_campaigns(self) -> bool:
        """True if there is at least one active campaign."""
        return len(self._campaigns) > 0

    def current_campaign(self) -> SponsorCampaign | None:
        """Return the current campaign, advancing if rotation_interval_s has elapsed."""
        if not self._campaigns:
            return None

        now = time.monotonic()
        if (now - self._last_rotation_time) >= self.rotation_interval_s:
            self._index = (self._index + 1) % len(self._campaigns)
            self._last_rotation_time = now

        return self._campaigns[self._index]

    def advance(self) -> SponsorCampaign | None:
        """Explicitly step to the next campaign (e.g. at the start of a turn)."""
        if not self._campaigns:
            return None
        self._index = (self._index + 1) % len(self._campaigns)
        self._last_rotation_time = time.monotonic()
        return self._campaigns[self._index]

    def current_tagline(self, fallback: str = "working…") -> str:
        """Get the current 1-line tagline or the default fallback."""
        campaign = self.current_campaign()
        if campaign is None:
            return fallback
        return campaign.format_tagline()
