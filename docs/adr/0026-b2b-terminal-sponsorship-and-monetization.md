# 0026. B2B terminal sponsorship and monetization engine

**Status:** Accepted  
**Date:** 2026-11-16

## Context

Open-source developer agents face high sustainability hurdles: they are expensive to maintain, but reselling model inference at a markup or gating core capabilities behind $20+/month SaaS subscriptions creates high friction and destroys open-source community adoption. Simultaneously, developer-tool vendors (compute, databases, observability, cloud providers) lack direct, respectful channels to reach technical users who actively write code in their terminal.

Early experiments considered rotating sponsored taglines directly inside the reasoning spinner animation (`spinner_text`). However, when animating at 10 Hz (`refresh_interval = 0.1s`), embedding varying-length text inside the fast spinner caused significant visual jitter, terminal reflows, and disrupted the developer's perception of agent progress.

## Decision

1. **Terminal-Native Placements:**
   - **Persistent TUI Footer Banner:** In the interactive REPL (`_bottom_toolbar`), sponsor ads are rendered as a dedicated line directly *above* the status toolbar:
     `📢 Sponsored by [Sponsor Name] | [Tagline] | [URL]` (with `url` styled with green underline).
     During initial startup or cache reloads, a transient fallback is shown (`🎯 Sponsor Ads (loading…)`).
   - **Response / Stream Ads (`display_sponsor_ad`):** On startup and when an ad rotates between prompt turns, an ad is emitted into the console output via Rich:
     `📢 Sponsored by [Sponsor Name] | [Tagline] | visit`
   - **OSC 8 Hyperlinks:** Terminal hyperlink codes (OSC 8) are embedded in modern terminal emulators via Rich's `Style(link=url)`, allowing developers to `Cmd/Ctrl + Click` the "visit" anchor or footer link to open documentation or sponsor sites.
   - **Decoupled Reasoning Spinner:** The busy spinner in the status footer remains clean and focused solely on progress (`frame + " working…"`), completely decoupled from commercial copy.

2. **Zero Code Leakage Privacy Guarantee:**
   - `ClientMetadata` transmits *only* high-level platform attributes: `client_version`, `os_type`, and `python_version`.
   - `FORBIDDEN_METADATA_KEYS` strictly blacklists and rejects any prompt text, file contents, git diffs, workspace paths, repository names, tokens, API keys, or environment variables.

3. **Resilience & Fail-Silent Performance:**
   - Background prefetching and TTL caching (default 300s) ensure ad requests never block or add latency to agent LLM loops or tool execution.
   - Any network timeout, HTTP error, or malformed payload fails silently to standard system messages without interrupting turns.

4. **Opt-Out Hierarchy:**
   - Users can disable monetization at multiple tiers with strict precedence:
     1. Startup CLI flag: `decode --no-ads`
     2. Project / user config: `.decode/settings.json` (`"ads": false` or `"sponsors": false`)
     3. Global settings / environment: `SPONSORS_ENABLED=false`

## Consequences

- The agent harness maintains a sustainable, non-intrusive revenue stream while remaining free and open-source.
- The developer experience is preserved: zero audio, zero pop-ups, zero input blocking, and no spinner animation jitter.
- Developer code and privacy are cryptographically and structurally protected from ad networks.
- Users who require complete ad-free environments can opt out via CLI flag or settings.
