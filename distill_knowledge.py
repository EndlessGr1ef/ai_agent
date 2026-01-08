#!/usr/bin/env python3
"""
Wrapper for backward compatibility
This script provides backward compatibility for the old distill_knowledge.py location.
The actual implementation is in src/data/distillation/distill_knowledge.py
"""

import asyncio
from src.data.distillation.distill_knowledge import main

if __name__ == "__main__":
    asyncio.run(main())
