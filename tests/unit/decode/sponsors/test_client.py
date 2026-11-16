"""Unit tests for decode.sponsors.client."""

import httpx
import pytest

from decode.sponsors.client import SponsorClient
from decode.sponsors.types import ClientMetadata


@pytest.fixture
def anonymized_meta() -> ClientMetadata:
    return ClientMetadata(
        client_version="0.2.0",
        os_type="linux",
        python_version="3.12",
    )


async def test_client_unconfigured_returns_cached_or_empty():
    """An unconfigured client (no URL) returns empty list and makes no network calls."""
    client = SponsorClient(endpoint_url="")
    assert not client.is_configured
    campaigns = await client.fetch_campaigns()
    assert campaigns == []


async def test_client_rest_fetch_success(anonymized_meta):
    """Client successfully parses campaigns from a standard REST endpoint (via GET)."""

    def handler(request: httpx.Request) -> httpx.Response:
        # New implementation uses GET with no body
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "campaigns": [
                    {
                        "campaign_id": "c1",
                        "sponsor_name": "PostHog",
                        "tagline": "Product analytics for developers",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/v1/campaigns",
            http_client=http_client,
        )
        campaigns = await client.fetch_campaigns(anonymized_meta)

    assert len(campaigns) == 1
    assert campaigns[0].campaign_id == "c1"
    assert campaigns[0].sponsor_name == "PostHog"
    assert campaigns[0].tagline == "Product analytics for developers"


async def test_client_json_rpc_fetch_success(anonymized_meta):
    """Client successfully queries a REST endpoint (simplified to GET)."""

    def handler(request: httpx.Request) -> httpx.Response:
        # New implementation uses GET
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "campaigns": [
                    {
                        "campaign_id": "c-rpc-1",
                        "sponsor_name": "Sentry",
                        "tagline": "Application performance monitoring",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/api/campaigns",
            http_client=http_client,
        )
        campaigns = await client.fetch_campaigns(anonymized_meta)

    assert len(campaigns) == 1
    assert campaigns[0].campaign_id == "c-rpc-1"
    assert campaigns[0].sponsor_name == "Sentry"
    assert campaigns[0].tagline == "Application performance monitoring"


async def test_client_fail_silent_on_http_429(anonymized_meta):
    """Client fails silently when hitting rate limits (HTTP 429)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/v1/campaigns",
            http_client=http_client,
        )
        campaigns = await client.fetch_campaigns(anonymized_meta)

    # Never raises, returns empty list
    assert campaigns == []


async def test_client_fail_silent_on_http_500(anonymized_meta):
    """Client fails silently when ad server is down (HTTP 500)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/v1/campaigns",
            http_client=http_client,
        )
        campaigns = await client.fetch_campaigns(anonymized_meta)

    assert campaigns == []


async def test_client_fail_silent_on_network_timeout(anonymized_meta):
    """Client fails silently on network timeout."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/v1/campaigns",
            timeout_s=0.5,
            http_client=http_client,
        )
        campaigns = await client.fetch_campaigns(anonymized_meta)

    assert campaigns == []


async def test_client_fail_silent_on_corrupt_json(anonymized_meta):
    """Client fails silently on malformed JSON response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="NOT JSON")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/v1/campaigns",
            http_client=http_client,
        )
        campaigns = await client.fetch_campaigns(anonymized_meta)

    assert campaigns == []


async def test_client_caching_and_ttl(anonymized_meta):
    """Client uses cached campaigns within cache TTL and avoids redundant calls."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json=[{"campaign_id": "c1", "sponsor_name": "TestSponsor", "tagline": "Test Tagline"}],
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/v1/campaigns",
            cache_ttl_s=300.0,
            http_client=http_client,
        )
        res1 = await client.fetch_campaigns(anonymized_meta)
        assert len(res1) == 1
        assert calls == 1
        assert client.has_valid_cache

        # Second call returns cached list without hitting transport
        res2 = await client.fetch_campaigns(anonymized_meta)
        assert len(res2) == 1
        assert calls == 1
