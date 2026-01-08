#!/usr/bin/env python3
"""
Wrapper for backward compatibility
This script provides backward compatibility for the old clear_chromadb.py location.
The actual implementation is in src/cli/db_manager.py
"""

from src.cli.db_manager import main

if __name__ == "__main__":
    main()
