#!/usr/bin/env python3
"""
Main entry point for the LLM agent.

This file now serves as a wrapper to the refactored module structure.
For new development, use src.main or import from src.config, src.agents, etc.
"""

import sys
import os

# Add src to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from main import main

if __name__ == "__main__":
    main()
