"""Mock sponsor backend server for local development and testing.

Provides HTTP endpoints matching the sponsor backend API contract.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

# Default mock campaigns
MOCK_CAMPAIGNS = [
    {
        "id": "sponsor-001",
        "sponsor_name": "fakefirm AI",
        "tagline": "Enterprise AI transforming software development",
        "url": "https://fakefirm.ai",
        "priority": 10,
        "enabled": True,
    },
    {
        "id": "sponsor-002",
        "sponsor_name": "Modal",
        "tagline": "Serverless GPU compute for AI/ML",
        "url": "https://modal.com",
        "priority": 8,
        "enabled": True,
    },
    {
        "id": "sponsor-003",
        "sponsor_name": "Langfuse",
        "tagline": "Open-source LLM observability platform",
        "url": "https://langfuse.com",
        "priority": 5,
        "enabled": True,
    },
]


class MockSponsorServer:
    """In-memory sponsor backend for testing and development."""

    def __init__(self, campaigns: list[dict] | None = None, port: int = 8765) -> None:
        self.campaigns = campaigns or [c.copy() for c in MOCK_CAMPAIGNS]
        self.port = port
        self.impressions: list[dict[str, Any]] = []
        self.clicks: list[dict[str, Any]] = []
        self.runner: web.AppRunner | None = None

    def get_app(self) -> web.Application:
        """Create and return the aiohttp app."""
        app = web.Application()
        app.router.add_get("/sponsors/api/campaigns", self._handle_get_campaigns)
        app.router.add_post("/sponsors/api/impressions", self._handle_impression)
        app.router.add_post("/sponsors/api/clicks", self._handle_click)
        app.router.add_get("/health", self._handle_health)
        return app

    async def _handle_get_campaigns(self, request: web.Request) -> web.Response:
        """GET /sponsors/api/campaigns - return active campaigns."""
        active_campaigns = [c for c in self.campaigns if c.get("enabled", True)]
        return web.json_response({"campaigns": active_campaigns})

    async def _handle_impression(self, request: web.Request) -> web.Response:
        """POST /sponsors/api/impressions - log an impression."""
        try:
            data = await request.json()
            self.impressions.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": data,
                }
            )
            logger.debug(f"[SPONSOR] Impression logged: {data}")
            return web.json_response({"status": "ok"})
        except Exception as e:
            logger.error(f"Error logging impression: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=400)

    async def _handle_click(self, request: web.Request) -> web.Response:
        """POST /sponsors/api/clicks - log a click."""
        try:
            data = await request.json()
            self.clicks.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": data,
                }
            )
            logger.debug(f"[SPONSOR] Click logged: {data}")
            return web.json_response({"status": "ok"})
        except Exception as e:
            logger.error(f"Error logging click: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=400)

    async def _handle_health(self, request: web.Request) -> web.Response:
        """GET /health - health check."""
        return web.json_response({"status": "healthy", "campaigns": len(self.campaigns)})

    async def start(self) -> None:
        """Start the mock server."""
        app = self.get_app()
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", self.port)
        await site.start()
        logger.info(f"✓ Mock sponsor server running at http://127.0.0.1:{self.port}")

    async def stop(self) -> None:
        """Stop the mock server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("✓ Mock sponsor server stopped")

    @property
    def url(self) -> str:
        """Return the base URL of the mock server."""
        return f"http://127.0.0.1:{self.port}/sponsors/api"


async def main() -> None:
    """Run the mock server standalone."""
    server = MockSponsorServer()
    await server.start()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await server.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
