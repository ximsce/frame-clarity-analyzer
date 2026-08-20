"""Errors raised by the frame analysis core."""


class FrameClarityError(Exception):
    """Base class for expected user-facing workflow errors."""


class ConfigurationError(FrameClarityError):
    """The requested workflow configuration is invalid."""


class DiscoveryError(FrameClarityError):
    """The input frame set cannot be discovered safely."""


class AnalyzerError(FrameClarityError):
    """An analyzer could not be initialized or returned a usable result."""


class AnalyzerInitializationError(AnalyzerError):
    """Optional analyzer dependencies or configuration are unavailable."""


class AnalysisFailureError(FrameClarityError):
    """One or more frames remained unresolved after analysis."""


class ProgressError(FrameClarityError):
    """Progress data cannot be safely loaded or written."""


class ProgressMismatchError(ProgressError):
    """Progress belongs to a different input or analyzer context."""


class OutputError(FrameClarityError):
    """A result or copied frame artifact could not be written."""
