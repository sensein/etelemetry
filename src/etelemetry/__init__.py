"""etelemetry — lightweight version check telemetry client."""

from .client import check_available_version, get_project
from .errors import BadVersionError

__version__ = "2.0.0"

__all__ = [
    "BadVersionError",
    "check_available_version",
    "get_project",
    "__version__",
]
