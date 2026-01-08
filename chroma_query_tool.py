#!/usr/bin/env python3
"""
Wrapper for backward compatibility
This script provides backward compatibility for the old chroma_query_tool.py location.
The actual implementation is in src/cli/chroma_query_tool.py
"""

from src.cli.chroma_query_tool import main

if __name__ == "__main__":
    main()
