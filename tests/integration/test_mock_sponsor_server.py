"""Tests for the mock sponsor server."""

from __future__ import annotations

import pytest

from tests.support.mock_sponsor_server import MockSponsorServer


@pytest.fixture
async def mock_server():
    """Fixture to start and stop the mock sponsor server."""
    server = MockSponsorServer(port=8765)
    await server.start()
    yield server
    await server.stop()


@pytest.mark.asyncio
async def test_mock_server_starts(mock_server: MockSponsorServer):
    """Test that the mock server starts without errors."""
    assert mock_server.url == "http://127.0.0.1:8765/sponsors/api"


@pytest.mark.asyncio
async def test_get_campaigns_endpoint(mock_server: MockSponsorServer):
    """Test the /campaigns endpoint returns campaigns."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{mock_server.url}/campaigns")
        assert response.status_code == 200
        data = response.json()
        assert "campaigns" in data
        assert len(data["campaigns"]) == 3
        assert data["campaigns"][0]["sponsor_name"] == "fakefirm AI"
        assert data["campaigns"][0]["priority"] == 10


@pytest.mark.asyncio
async def test_health_endpoint(mock_server: MockSponsorServer):
    """Test the /health endpoint."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get("http://127.0.0.1:8765/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["campaigns"] == 3


@pytest.mark.asyncio
async def test_log_impression(mock_server: MockSponsorServer):
    """Test logging impressions."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{mock_server.url}/impressions",
            json={"campaign_id": "sponsor-001", "session_id": "test-123"},
        )
        assert response.status_code == 200
        assert mock_server.impressions
        assert mock_server.impressions[0]["data"]["campaign_id"] == "sponsor-001"


@pytest.mark.asyncio
async def test_log_click(mock_server: MockSponsorServer):
    """Test logging clicks."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{mock_server.url}/clicks",
            json={"campaign_id": "sponsor-001", "session_id": "test-123"},
        )
        assert response.status_code == 200
        assert mock_server.clicks
        assert mock_server.clicks[0]["data"]["campaign_id"] == "sponsor-001"
