"""Campaign rotator for presenting 1-line developer sponsor taglines.

Rotates smoothly across campaigns on a time or turn interval while maintaining
developer flow state. Strictly 1-line text with zero interruptions.

Supports two rotation modes:
- Round-robin: sequential rotation (old behavior)
- Weighted random: frequency proportional to campaign priority (new, default)
"""

from __future__ import annotations

import random
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
        self._weights: list[float] | None = None
        self._update_weights()

    def _update_weights(self) -> None:
        """Compute normalized weights for weighted random selection."""
        if not self._campaigns:
            self._weights = None
            return

        priorities = [
            float(getattr(c, "weight", getattr(c, "priority", 1.0))) for c in self._campaigns
        ]
        total = sum(priorities) or 1.0
        self._weights = [p / total for p in priorities]

    def update_campaigns(self, campaigns: list[SponsorCampaign]) -> None:
        """Update the active campaign list."""
        self._campaigns = list(campaigns)
        if self._index >= len(self._campaigns):
            self._index = 0
        # Clear cached current campaign so next call to current_campaign() uses updated list
        if hasattr(self, "_current_campaign"):
            delattr(self, "_current_campaign")
        self._update_weights()

    @property
    def has_campaigns(self) -> bool:
        """True if there is at least one active campaign."""
        return len(self._campaigns) > 0

    def current_campaign(self) -> SponsorCampaign | None:
        """Return the current campaign, advancing if rotation_interval_s has elapsed.

        With weighted=True, uses random selection weighted by priority.
        With weighted=False, uses round-robin selection.
        """
        if not self._campaigns:
            return None

        now = time.monotonic()
        if (now - self._last_rotation_time) >= self.rotation_interval_s:
            if self._weights:
                # Weighted random: pick next campaign proportional to weight
                self._current_campaign = random.choices(
                    self._campaigns, weights=self._weights, k=1
                )[0]
            else:
                # Round-robin: pick next in sequence
                self._index = (self._index + 1) % len(self._campaigns)
                self._current_campaign = self._campaigns[self._index]
            self._last_rotation_time = now

        return getattr(self, "_current_campaign", self._campaigns[0] if self._campaigns else None)

    def advance(self) -> SponsorCampaign | None:
        """Explicitly step to the next campaign (e.g. at the start of a turn)."""
        if not self._campaigns:
            return None

        if self._weights:
            self._current_campaign = random.choices(self._campaigns, weights=self._weights, k=1)[0]
        else:
            self._index = (self._index + 1) % len(self._campaigns)
            self._current_campaign = self._campaigns[self._index]

        self._last_rotation_time = time.monotonic()
        return self._current_campaign

    def current_tagline(self, fallback: str = "working…") -> str:
        """Get the current 1-line tagline or the default fallback."""
        campaign = self.current_campaign()
        if campaign is None:
            return fallback
        return campaign.format_tagline()
