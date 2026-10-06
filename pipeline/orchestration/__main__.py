"""Preserve the original public preprocessing command."""
from pipeline.preprocessing.orchestration.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
