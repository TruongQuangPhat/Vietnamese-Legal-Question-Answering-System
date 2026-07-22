"""Compatibility exports for direct-evidence benchmark utilities.

The canonical implementation lives in ``src.evaluation.benchmark.direct_evidence``.
This module keeps the branch-era import path stable for existing callers while
avoiding a parallel benchmark package outside ``src.evaluation.benchmark``.
"""

from __future__ import annotations

from src.evaluation.benchmark.direct_evidence import *  # noqa: F403
