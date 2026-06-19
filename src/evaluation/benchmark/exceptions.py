"""Custom exceptions for benchmark loading, validation, and freeze support."""

from __future__ import annotations


class BenchmarkError(ValueError):
    """Base exception for benchmark implementation failures."""


class BenchmarkLoadError(BenchmarkError):
    """Raised when benchmark input files cannot be loaded deterministically."""


class BenchmarkValidationError(BenchmarkError):
    """Raised when benchmark validation prevents a requested operation."""


class BenchmarkFreezeError(BenchmarkError):
    """Raised when a frozen manifest cannot be created safely."""
