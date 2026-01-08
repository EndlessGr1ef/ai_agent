#!/usr/bin/env python3
"""
Wrapper for backward compatibility
This script provides backward compatibility for the old ingest_md.py location.
The actual implementation is in src/data/ingestion/ingest_md.py
"""

from src.data.ingestion.ingest_md import main

if __name__ == "__main__":
    main()
