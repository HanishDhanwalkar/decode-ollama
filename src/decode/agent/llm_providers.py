"""Build Pydantic AI models for the configured LLM provider (ADR-0005 §3-5)."""

from __future__ import annotations

from typing import Literal

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.profiles import ModelProfile, merge_profile
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from decode.config.settings import settings


def _build_model(*, model: str | None = None) -> Model:
    """Build the model for ``settings.llm_provider`` — the Provider Seam.

    ``model`` overrides only the active provider's model id; it never changes the provider or
    authentication path. Gemini uses the Generative-Language API-key path and never passes
    ``vertexai=``. OpenRouter and Modal use ``OpenAIChatModel``; Modal uses a custom client with
    the endpoint URL and optional dual-header proxy-token authentication. Gemini and OpenRouter
    keys come from ``Settings``; Modal credentials are headers rather than a single API key.
    """
    provider = settings.llm_provider
    if provider == "gemini":
        return GoogleModel(
            model or settings.gemini_model,
            provider=GoogleProvider(api_key=_provider_api_key("gemini")),
        )
    if provider == "openrouter":
        return OpenAIChatModel(
            model or settings.openrouter_model,
            provider=OpenRouterProvider(api_key=_provider_api_key("openrouter")),
        )
    if provider == "modal":
        base_url = f"{settings.modal_endpoint_url}/v1"
        token_id = settings.modal_proxy_token_id.get_secret_value()
        token_secret = settings.modal_proxy_token_secret.get_secret_value()
        if token_id and token_secret:
            client = AsyncOpenAI(
                base_url=base_url,
                api_key=token_secret,
                default_headers={"Modal-Key": token_id, "Modal-Secret": token_secret},
            )
        else:
            client = AsyncOpenAI(base_url=base_url, api_key="EMPTY")
        return OpenAIChatModel(
            model or settings.modal_endpoint_model,
            provider=OpenAIProvider(openai_client=client),
            profile=_modal_profile,
        )
    if provider == "ollama":
        return OllamaModel(
            model or settings.ollama_model,
            provider=OllamaProvider(
                base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
            ),
        )
    raise ValueError(f"unsupported llm_provider: {provider!r}")


def discover_ollama_models() -> list[str]:
    """Return locally pulled model names from Ollama's ``/api/tags`` endpoint."""
    response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=5.0)
    response.raise_for_status()
    payload = response.json()
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return [entry["name"] for entry in models if isinstance(entry, dict) and entry.get("name")]

def discover_provider_models() -> list[str]:
    """List models available from the active provider for the interactive ``/model`` command."""
    if settings.llm_provider == "ollama":
        return discover_ollama_models()
    if settings.llm_provider == "gemini":
        response = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": _provider_api_key("gemini")},
            timeout=5.0,
        )
        response.raise_for_status()
        entries = response.json().get("models", [])
        return sorted(
            entry["name"].removeprefix("models/")
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("name")
            and "generateContent" in entry.get("supportedGenerationMethods", [])
        )
    if settings.llm_provider == "openrouter":
        response = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {_provider_api_key('openrouter')}"},
            timeout=5.0,
        )
        response.raise_for_status()
        entries = response.json().get("data", [])
        return sorted(entry["id"] for entry in entries if isinstance(entry, dict) and entry.get("id"))
    if settings.llm_provider == "modal":
        token_id = settings.modal_proxy_token_id.get_secret_value()
        token_secret = settings.modal_proxy_token_secret.get_secret_value()
        headers = (
            {"Modal-Key": token_id, "Modal-Secret": token_secret}
            if token_id and token_secret
            else None
        )
        response = httpx.get(
            f"{settings.modal_endpoint_url.rstrip('/')}/v1/models", headers=headers, timeout=5.0
        )
        response.raise_for_status()
        entries = response.json().get("data", [])
        return sorted(entry["id"] for entry in entries if isinstance(entry, dict) and entry.get("id"))
    raise ValueError(f"unsupported llm_provider: {settings.llm_provider!r}")


def _modal_profile(inferred: ModelProfile) -> ModelProfile:
    """Disable OpenAI-cloud strict tool definitions for Modal-hosted open-weight models."""
    return merge_profile(inferred, OpenAIModelProfile(openai_supports_strict_tool_definition=False))


def _provider_api_key(provider: Literal["gemini", "openrouter"]) -> str:
    """Read the provider API key from the Settings singleton (ADR-0021)."""
    secret = settings.gemini_api_key if provider == "gemini" else settings.openrouter_api_key
    return secret.get_secret_value()
