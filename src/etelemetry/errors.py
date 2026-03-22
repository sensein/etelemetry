"""etelemetry exceptions."""


class BadVersionError(RuntimeError):
    """Local version is known to contain a critical bug."""

    pass
