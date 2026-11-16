"""Configuration handler, privacy metadata builder, and frictionless opt-out resolution.

Guarantees:
- ClientMetadata only gathers anonymized system attributes (OS, Python version, CLI version).
- Opt-out checks support:
  * Startup CLI flag (--no-ads / --no-sponsors)
  * Global/project config file (.decode/settings.json -> "ads": false or "sponsors": false)
  * Settings / .env (SPONSORS_ENABLED=false / DECODE_ADS=false)
  * Seamless auto-opt-out for local-only models (Ollama) when sponsors_disable_for_local_models=True
  * Seamless opt-out for Bring-Your-Own-Key (BYOK) configurations when configured
"""

from __future__ import annotations

import json
import logging
import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from decode.sponsors.types import ClientMetadata

if TYPE_CHECKING:
    from decode.config.settings import Settings

logger = logging.getLogger(__name__)


def get_anonymized_metadata() -> ClientMetadata:
    """Build strictly anonymized client metadata.

    Privacy & Sandboxing Guarantee:
    NEVER accesses, reads, serializes, or transmits user prompt text, file contents,
    git diffs, environment variables, or workspace paths.
    """
    import decode

    version = getattr(decode, "__version__", "0.2.0")
    os_name = platform.system().lower()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    return ClientMetadata(
        client_version=version,
        os_type=os_name,
        python_version=py_ver,
    )


def read_config_file_opt_out(path: Path) -> bool | None:
    """Read opt-out setting from .decode/settings.json or similar config file.

    Returns:
        False if explicitly opted out via "ads": false or "sponsors": false.
        True if explicitly enabled via "ads": true or "sponsors": true.
        None if file is missing, malformed, or unmentioned.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("Failed to read settings config file at %s", path)
        return None

    if not isinstance(data, dict):
        return None

    for key in ("ads", "sponsors", "sponsors_enabled"):
        if key in data and isinstance(data[key], bool):
            return data[key]

    return None


def is_sponsors_enabled(
    settings: Settings,
    *,
    no_ads_flag: bool = False,
    config_path: Path | None = None,
) -> bool:
    """Determine whether sponsor monetization features are enabled.

    Priority order:
    1. Startup flag (--no-ads / --no-sponsors): if True, unconditionally disabled.
    2. Local settings file (.decode/settings.json): "ads": false explicitly disables.
    3. Global settings (settings.sponsors_enabled): if False, disabled.
    4. Local-only models: if settings.sponsors_disable_for_local_models and llm_provider == "ollama",
       disabled to provide a zero-sponsor experience for local AI.
    5. BYOK opt-out: if settings.sponsors_disable_for_byok and user configured their own keys,
       disabled.
    """
    # 1. Startup flag
    if no_ads_flag:
        return False

    # 2. Local settings file
    resolved_path = config_path or getattr(
        settings, "permissions_file", Path(".decode/settings.json")
    )
    file_setting = read_config_file_opt_out(resolved_path)
    if file_setting is False:
        return False

    # 3. Global settings field
    if not getattr(settings, "sponsors_enabled", True):
        return False

    # 4. Local-only models (Ollama)
    if (
        getattr(settings, "sponsors_disable_for_local_models", True)
        and getattr(settings, "llm_provider", "") == "ollama"
    ):
        return False

    # 5. BYOK (Bring Your Own Key) automatic opt-out check if enabled
    if getattr(settings, "sponsors_disable_for_byok", False):
        gemini_key = getattr(settings, "gemini_api_key", None)
        openrouter_key = getattr(settings, "openrouter_api_key", None)
        has_byok = (gemini_key is not None and bool(gemini_key.get_secret_value().strip())) or (
            openrouter_key is not None and bool(openrouter_key.get_secret_value().strip())
        )
        if has_byok:
            return False

    return True
