"""State machine hook for the CLI status line and terminal spinner.

Integrates with the harness runner and TUI event stream to replace default
thinking / executing spinner text with rotating 1-line B2B sponsor taglines.
Maintains developer flow state: single transient line in bottom toolbar, zero pop-ups,
zero audio, zero keyboard interruptions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from decode.entities import events
from decode.harness.runner import Phase
from decode.sponsors.client import SponsorClient
from decode.sponsors.config import get_anonymized_metadata, is_sponsors_enabled
from decode.sponsors.rotator import SponsorRotator
from decode.sponsors.types import HarnessState

if TYPE_CHECKING:
    from decode.config.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_THINKING_TEXT = "Analyzing codebase…"
DEFAULT_WORKING_TEXT = "working…"


class SponsorStateMachineHook:
    """Hooks directly into the harness state machine to display rotating 1-line sponsor taglines."""

    def __init__(
        self,
        settings: Settings,
        *,
        no_ads_flag: bool = False,
        client: SponsorClient | None = None,
        rotator: SponsorRotator | None = None,
    ) -> None:
        self.settings = settings
        self.no_ads_flag = no_ads_flag
        self.state = HarnessState.IDLE
        self._enabled = is_sponsors_enabled(settings, no_ads_flag=no_ads_flag)

        self.client = client or SponsorClient(
            endpoint_url=getattr(settings, "sponsors_endpoint_url", ""),
            timeout_s=getattr(settings, "sponsors_timeout_s", 2.0),
            cache_ttl_s=getattr(settings, "sponsors_cache_ttl_s", 300.0),
        )
        self.rotator = rotator or SponsorRotator(
            rotation_interval_s=getattr(settings, "sponsors_rotation_interval_s", 8.0)
        )
        self._bg_task: asyncio.Task[None] | None = None

    @property
    def is_enabled(self) -> bool:
        """Whether sponsors are enabled based on opt-out flags and settings."""
        return self._enabled

    def on_phase_change(self, old_phase: Phase, new_phase: Phase) -> None:
        """Handle runner phase machine transitions (IDLE -> DISPATCHING -> RUNNING -> IDLE)."""
        if new_phase is Phase.IDLE:
            self.state = HarnessState.IDLE
        elif new_phase is Phase.DISPATCHING:
            self.state = HarnessState.DISPATCHING
            self._on_turn_start()
        elif new_phase is Phase.RUNNING and self.state is not HarnessState.EXECUTING:
            self.state = HarnessState.THINKING

    def on_event(self, event: events.Event) -> None:
        """Handle stream events emitted during a turn."""
        if isinstance(event, events.TurnStarted):
            self.state = HarnessState.THINKING
            self._on_turn_start()
        elif isinstance(event, events.ThinkingDelta):
            self.state = HarnessState.THINKING
        elif isinstance(event, events.ToolCallStarted):
            self.state = HarnessState.EXECUTING
        elif isinstance(event, events.TurnFinished):
            self.state = HarnessState.IDLE

    def _on_turn_start(self) -> None:
        """Triggered when a turn starts: rotate tagline and schedule background prefetch."""
        if not self._enabled:
            return

        self.rotator.advance()

        # Fail-silent background refresh if cache is expired
        if self.client.is_configured and not self.client.has_valid_cache:
            self._schedule_background_refresh()

    def _schedule_background_refresh(self) -> None:
        """Schedule a non-blocking background fetch so the main agent loop never lags."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if self._bg_task is not None and not self._bg_task.done():
            return

        async def _refresh() -> None:
            try:
                metadata = get_anonymized_metadata()
                campaigns = await self.client.fetch_campaigns(metadata)
                if campaigns:
                    self.rotator.update_campaigns(campaigns)
            except Exception as exc:
                logger.debug("Background sponsor refresh failed silently: %s", exc)

        self._bg_task = loop.create_task(_refresh())

    def spinner_text(self, phase: Phase, default: str = DEFAULT_WORKING_TEXT) -> str:
        """Return the transient 1-line text for the spinner during thinking/executing states.

        Rules:
        - If runner is IDLE: returns empty string.
        - If sponsors are disabled: returns `default` (e.g. "working…").
        - If active campaigns exist: returns rotating 1-line tagline.
        - If fetching failed / no campaigns: falls back silently to `default` or internal text.
        - Strictly single line, zero disruption.
        """
        if phase is Phase.IDLE:
            return ""

        if not self._enabled:
            return default

        if self.rotator.has_campaigns:
            return self.rotator.current_tagline(fallback=default)

        # Fallback to default when no campaigns are loaded
        return default
