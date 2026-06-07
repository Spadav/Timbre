class TimbreError(Exception):
    """Base Timbre exception."""


class BackendUnavailable(TimbreError):
    """Raised when an optional backend dependency or model is unavailable."""


class UnknownBackend(TimbreError):
    """Raised when a request references an unknown or disabled backend."""
