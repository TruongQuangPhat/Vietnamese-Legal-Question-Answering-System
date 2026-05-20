"""Main entry point for python -m src.ingestion.cli execution."""

from __future__ import annotations

from src.ingestion.cli import main

if __name__ == "__main__":
    import sys

    sys.exit(main())
