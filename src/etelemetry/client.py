"""etelemetry client — version check and telemetry reporting."""

from __future__ import annotations

import logging
import os

from packaging.version import Version

from .config import resolve_url
from .errors import BadVersionError

try:
    import ci_info
except ImportError:
    ci_info = None  # type: ignore[assignment]

_available_version_checked: dict | None = None


def _etrequest(endpoint: str, method: str = "get", **kwargs) -> dict:
    """Make a request to the etelemetry server.

    Lazy-imports ``requests`` to avoid penalizing startup time.
    """
    from requests import ConnectionError, ReadTimeout, request

    if kwargs.get("timeout") is None:
        kwargs["timeout"] = 5

    params: dict = kwargs.pop("params", {})
    # Send CI information as query parameters
    if ci_info is not None and ci_info.is_ci():
        ci_params = ci_info.info()
        if isinstance(ci_params, dict):
            params.update(ci_params)
        params["ci"] = "true"

    try:
        res = request(method, endpoint, params=params, **kwargs)
    except ConnectionError:
        raise RuntimeError("Connection to server could not be made")
    except ReadTimeout:
        raise RuntimeError(
            f"No response from server in {kwargs.get('timeout')} seconds"
        )
    res.raise_for_status()
    return res.json()


def get_project(repo: str, *, server_url: str | None = None, **rargs) -> dict | None:
    """Fetch latest version info from the etelemetry server.

    Parameters
    ----------
    repo : str
        GitHub repository as ``<owner>/<project>``.
    server_url : str or None
        Explicit server URL (highest precedence). See
        :func:`etelemetry.config.resolve_url` for the full chain.
    **rargs
        Additional keyword arguments passed to ``requests.request``.

    Returns
    -------
    dict or None
        Dictionary with ``version`` and ``bad_versions`` keys,
        or None if telemetry is disabled.

    Raises
    ------
    ValueError
        If ``repo`` is not in ``owner/project`` format.
    RuntimeError
        If the server is unreachable.
    """
    if "NO_ET" in os.environ:
        return None
    if "/" not in repo:
        raise ValueError("Invalid repository — expected 'owner/project' format")

    base_url = resolve_url(server_url=server_url)
    if base_url is None:
        return None

    # Ensure trailing slash
    if not base_url.endswith("/"):
        base_url += "/"

    endpoint = f"{base_url}projects/{repo}"
    return _etrequest(endpoint, **rargs)


def check_available_version(
    project: str,
    version: str,
    lgr: logging.Logger | None = None,
    raise_exception: bool = False,
    *,
    server_url: str | None = None,
) -> dict | None:
    """Check and report if a newer version of a project is available.

    Safe to call multiple times — only checks once per session.

    Parameters
    ----------
    project : str
        GitHub repository as ``owner/project``.
    version : str
        The local version string.
    lgr : logging.Logger or None
        Logger instance. Creates one if not provided.
    raise_exception : bool
        If True, raise ``BadVersionError`` when a bad version is detected.

    Returns
    -------
    dict or None
        Version info dict, or None if check failed.
    """
    global _available_version_checked
    if _available_version_checked is not None:
        return _available_version_checked

    if lgr is None:
        lgr = logging.getLogger("et-client")

    latest = {"version": "Unknown", "bad_versions": []}
    ret = None
    try:
        ret = get_project(project, server_url=server_url)
    except Exception as e:
        lgr.debug("Could not check %s for version updates: %s", project, e)
        return None
    finally:
        if ret:
            latest.update(**ret)
            try:
                local_version = Version(version)
                remote_version = Version(latest["version"])
            except Exception:
                lgr.debug("Could not parse version for %s", project)
                _available_version_checked = latest
                return latest

            if local_version < remote_version:
                lgr.warning(
                    "A newer version (%s) of %s is available. "
                    "You are using %s",
                    latest["version"],
                    project,
                    version,
                )
            elif remote_version < local_version:
                lgr.debug(
                    "Running a newer version (%s) of %s than available (%s)",
                    version,
                    project,
                    latest["version"],
                )
            else:
                lgr.debug(
                    "No newer (than %s) version of %s found available",
                    version,
                    project,
                )

            if latest["bad_versions"] and any(
                local_version == Version(ver)
                for ver in latest["bad_versions"]
            ):
                message = (
                    f"You are using a version of {project} with a critical "
                    "bug. Please use a different version."
                )
                if raise_exception:
                    raise BadVersionError(message)
                else:
                    lgr.critical(message)

            _available_version_checked = latest

    return latest
