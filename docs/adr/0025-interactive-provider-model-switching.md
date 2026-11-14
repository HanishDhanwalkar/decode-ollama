# 0025. Switch LLM providers and models from the interactive REPL

**Status:** Accepted  
**Date:** 2026-11-15

## Context

The `/model` picker only listed models from `LLM_PROVIDER`, even when credentials for other
providers were configured. Users then had to edit `.env` and restart Decode to try another provider.
The model override already changes the live agent and compaction model for the rest of the session,
but model construction and context-window probing were tied to the configured provider.

## Decision

1. `/model` lists models for providers whose credentials or endpoint are configured, and the active
   provider. Each choice is a provider/model pair; discovery failures are reported per provider
   without hiding the providers whose catalogs remain available.
2. Selecting an option builds the model with that provider's own credentials and updates the active
   provider/model in memory. The switch applies to later turns in the current REPL session, including
   Explore subagents and compaction. It does not write `.env` or change the default for a new process.
3. `decode run --model` and Kitaru replay model inputs remain model-ID overrides for the provider
   selected by `LLM_PROVIDER`. Cross-provider model switching is an interactive REPL feature only.

## Consequences

- Users can switch among configured Gemini, OpenRouter, Modal, and Ollama providers without
  restarting Decode.
- Provider keys remain in `Settings` and are never included in the picker labels or confirmation.
- Restarting Decode restores the provider selected by `LLM_PROVIDER`.
