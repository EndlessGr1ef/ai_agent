#!/usr/bin/env python3
"""
Wrapper for backward compatibility
This script provides backward compatibility for the old prts_db_cli.py location.
The actual implementation is in src/cli/prts_db_cli.py
"""

from src.cli.prts_db_cli import main

if __name__ == "__main__":
    main()
