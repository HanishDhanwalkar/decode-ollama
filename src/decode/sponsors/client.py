"""Modular backend client for fetching B2B sponsor campaigns.

Operates in an isolated network/memory boundary.
Supports standard HTTPS JSON-RPC 2.0 and REST endpoints with strict timeouts (2.0s).
Implements a fail-silent design: all network, timeout, HTTP, and parsing errors are
caught and logged at DEBUG level only, never raising, crashing, or blocking the harness.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from decode.sponsors.types import ClientMetadata, SponsorCampaign

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 2.0
DEFAULT_CACHE_TTL_S = 300.0  # 5 minutes


class SponsorClient:
    """Backend client for querying developer sponsor rotation campaigns."""

    def __init__(
        self,
        endpoint_url: str = "",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url.strip()
        self.timeout_s = timeout_s
        self.cache_ttl_s = cache_ttl_s
        self._http_client = http_client
        self._cache: list[SponsorCampaign] | None = None
        self._cache_timestamp: float = 0.0
        self._fetch_lock: asyncio.Lock | None = None

    @property
    def fetch_lock(self) -> asyncio.Lock:
        """Lazily initialize fetch lock on the active event loop."""
        if self._fetch_lock is None:
            self._fetch_lock = asyncio.Lock()
        return self._fetch_lock

    @property
    def is_configured(self) -> bool:
        """True if an endpoint URL is configured."""
        return bool(self.endpoint_url)

    @property
    def has_valid_cache(self) -> bool:
        """True if the in-memory cache is still fresh."""
        return (
            self._cache is not None
            and (time.monotonic() - self._cache_timestamp) < self.cache_ttl_s
        )

    def get_cached_campaigns(self) -> list[SponsorCampaign]:
        """Return currently cached campaigns without fetching."""
        return list(self._cache) if self._cache is not None else []

    async def fetch_campaigns(
        self, metadata: ClientMetadata | None = None
    ) -> list[SponsorCampaign]:
        """Fetch active campaigns with strict timeout and fail-silent design.

        Returns:
            list[SponsorCampaign]: Active campaigns on success, cached campaigns if available,
            or an empty list on failure. Never raises an exception.
        """
        if not self.is_configured:
            return self.get_cached_campaigns()

        if self.has_valid_cache:
            return self.get_cached_campaigns()

        # Concurrency safety: if multiple requests arrive at once, only one network fetch runs
        async with self.fetch_lock:
            # Re-check cache inside lock
            if self.has_valid_cache:
                return self.get_cached_campaigns()

            try:
                campaigns = await self._do_fetch(metadata)
                if campaigns:
                    self._cache = campaigns
                    self._cache_timestamp = time.monotonic()
                return list(self._cache) if self._cache is not None else []
            except Exception as exc:
                # Fail-silent guarantee: log only at debug level, never raise or crash
                logger.debug("Failed to fetch sponsor campaigns (failing silently): %s", exc)
                return self.get_cached_campaigns()

    async def _do_fetch(self, metadata: ClientMetadata | None) -> list[SponsorCampaign]:
        """Perform the actual HTTP request to fetch campaigns."""
        timeout = httpx.Timeout(self.timeout_s)

        client = self._http_client
        created_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=timeout)
            created_client = True

        try:
            # Simple GET request to the campaigns endpoint
            resp = await client.get(
                self.endpoint_url,
                headers={"User-Agent": "decode-harness"},
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_rest_response(data)
        finally:
            if created_client:
                await client.aclose()

    def _parse_json_rpc_response(self, data: Any) -> list[SponsorCampaign]:
        """Parse JSON-RPC 2.0 response."""
        if not isinstance(data, dict):
            return []
        if data.get("error"):
            logger.debug("JSON-RPC error from sponsor endpoint: %s", data["error"])
            return []
        result = data.get("result")
        return self._parse_campaign_list(result)

    def _parse_rest_response(self, data: Any) -> list[SponsorCampaign]:
        """Parse REST response."""
        if isinstance(data, list):
            return self._parse_campaign_list(data)
        if isinstance(data, dict):
            items = data.get("campaigns", data.get("result", []))
            return self._parse_campaign_list(items)
        return []

    def _parse_campaign_list(self, items: Any) -> list[SponsorCampaign]:
        """Parse a list of campaign dicts safely."""
        if not isinstance(items, list):
            return []
        campaigns: list[SponsorCampaign] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            campaign_id = str(item.get("campaign_id") or item.get("id") or "")
            sponsor_name = str(item.get("sponsor_name") or item.get("name") or "")
            tagline = str(item.get("tagline") or item.get("text") or "")
            if not tagline:
                continue
            # Use 'priority' from backend (fallback to 'weight' if present, then 1.0)
            weight = float(item.get("priority") or item.get("weight", 1.0))
            campaigns.append(
                SponsorCampaign(
                    campaign_id=campaign_id or f"cmp-{len(campaigns)}",
                    sponsor_name=sponsor_name,
                    tagline=tagline,
                    url=item.get("url"),
                    weight=weight,
                )
            )
        return campaigns
