#!/usr/bin/env python3
"""Backward-compatible wrapper for the Phase 9B Naive RAG workflow."""

# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.retrieval.workflows.naive_rag import main

if __name__ == "__main__":
    raise SystemExit(main())
