"""etelemetry client configuration.

Server URL resolution (basic — US1):
    1. ETELEMETRY_URL environment variable
    2. Hardcoded default

The full precedence chain (param → env → default_url → hardcoded)
is added in US2 (T027).
"""

from __future__ import annotations

import os

_DEFAULT_URL = "https://etelemetry.sensein.group/"


def resolve_url() -> str | None:
    """Resolve the etelemetry server URL.

    Returns None if telemetry is disabled via NO_ET env var.
    """
    if "NO_ET" in os.environ:
        return None
    return os.environ.get("ETELEMETRY_URL", _DEFAULT_URL)
