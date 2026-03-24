"""etelemetry client configuration.

Server URL resolution precedence (highest to lowest):
    1. ``server_url`` function parameter
    2. ``ETELEMETRY_URL`` environment variable
    3. ``default_url`` module-level attribute (for library authors)
    4. Hardcoded default
"""

from __future__ import annotations

import os

_HARDCODED_URL = "https://et.dandiproject.org/"

#: Library authors can set this to point their package's clients at a
#: custom etelemetry instance without requiring end-users to set an
#: environment variable.  Example::
#:
#:     import etelemetry
#:     etelemetry.config.default_url = "https://my-instance.org/"
default_url: str | None = None


def resolve_url(server_url: str | None = None) -> str | None:
    """Resolve the etelemetry server URL.

    Parameters
    ----------
    server_url : str or None
        Explicit URL passed by the caller (highest precedence).

    Returns
    -------
    str or None
        The resolved URL, or None if telemetry is disabled via ``NO_ET``.
    """
    if "NO_ET" in os.environ:
        return None
    if server_url:
        return server_url
    env_url = os.environ.get("ETELEMETRY_URL")
    if env_url:
        return env_url
    if default_url:
        return default_url
    return _HARDCODED_URL
