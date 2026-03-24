"""etelemetry — lightweight version check telemetry client."""

from .client import check_available_version, get_project
from .errors import BadVersionError

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "BadVersionError",
    "check_available_version",
    "get_project",
    "__version__",
]
