"""Unit tests for decode.sponsors.client."""

from typing import Any

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
    """Client successfully parses campaigns from a standard REST endpoint."""
    captured_request: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured_request["body"] = json.loads(request.read())
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

    # Zero Code Leakage: Ensure request body has ONLY anonymized metadata
    body = captured_request["body"]
    assert set(body.keys()) == {"client_version", "os_type", "python_version"}
    assert body["client_version"] == "0.2.0"
    assert body["os_type"] == "linux"


async def test_client_json_rpc_fetch_success(anonymized_meta):
    """Client successfully queries a JSON-RPC 2.0 endpoint."""
    captured_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured_payload.update(json.loads(request.read()))
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "result": [
                    {
                        "id": "c-rpc-1",
                        "name": "Sentry",
                        "text": "Application performance monitoring",
                    }
                ],
                "id": "1",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = SponsorClient(
            endpoint_url="https://ads.decode.dev/api/rpc",
            http_client=http_client,
        )
        campaigns = await client.fetch_campaigns(anonymized_meta)

    assert len(campaigns) == 1
    assert campaigns[0].campaign_id == "c-rpc-1"
    assert campaigns[0].sponsor_name == "Sentry"
    assert campaigns[0].tagline == "Application performance monitoring"

    # Verify JSON-RPC structure and privacy
    assert captured_payload["jsonrpc"] == "2.0"
    assert captured_payload["method"] == "campaigns.fetch"
    params = captured_payload["params"]
    assert set(params.keys()) == {"client_version", "os_type", "python_version"}


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
