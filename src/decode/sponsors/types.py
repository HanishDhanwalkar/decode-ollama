"""Domain types for the B2B sponsorship feature.

Narrow types for sponsor campaigns, anonymized client metadata, and state transitions.
Strict privacy guarantees: ClientMetadata explicitly excludes any user code, files,
prompts, diffs, paths, tokens, or environment variables.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class HarnessState(enum.Enum):
    """The state of the agent harness observed by the sponsor state machine hook."""

    IDLE = "idle"
    DISPATCHING = "dispatching"
    THINKING = "thinking"
    EXECUTING = "executing"


# Forbidden keys that must NEVER be passed or present in client metadata or telemetry payloads
FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "prompt",
        "prompt_text",
        "messages",
        "history",
        "code",
        "diff",
        "git_diff",
        "file",
        "files",
        "file_content",
        "file_contents",
        "path",
        "paths",
        "cwd",
        "repo",
        "repository",
        "token",
        "api_key",
        "key",
        "secret",
        "env",
        "environ",
        "user",
        "username",
    }
)


@dataclass(frozen=True)
class ClientMetadata:
    """Strictly anonymized client metadata for developer-focused campaign targeting.

    Zero Code Leakage Guarantee:
    Only system-level platform and version info is transmitted. Under no circumstances
    may prompt contents, file contents, git diffs, environment variables, or workspace
    paths be included in this object.
    """

    client_version: str
    os_type: str
    python_version: str

    def __post_init__(self) -> None:
        for field_name in ("client_version", "os_type", "python_version"):
            val = getattr(self, field_name)
            if not isinstance(val, str):
                raise TypeError(f"ClientMetadata.{field_name} must be a str, got {type(val)}")
            if len(val) > 100:
                raise ValueError(f"ClientMetadata.{field_name} exceeds maximum allowed length")

    def to_dict(self) -> dict[str, str]:
        """Serialize anonymized client metadata."""
        return {
            "client_version": self.client_version,
            "os_type": self.os_type,
            "python_version": self.python_version,
        }


@dataclass(frozen=True)
class SponsorCampaign:
    """A developer-focused sponsor campaign."""

    campaign_id: str
    sponsor_name: str
    tagline: str
    url: str | None = None
    weight: float = 1.0

    def format_tagline(self) -> str:
        """Format as a clean, single-line developer-friendly message.

        Guarantees:
        - Exactly 1 line (no newlines, no carriage returns, stripped).
        - Clean attribution.
        """
        clean_tagline = " ".join(self.tagline.strip().splitlines())
        clean_name = self.sponsor_name.strip()
        if clean_name and not clean_tagline.lower().startswith(clean_name.lower()):
            text = f"Sponsored by {clean_name}: {clean_tagline}"
        else:
            text = f"Sponsored: {clean_tagline}"
        return " ".join(text.split())
