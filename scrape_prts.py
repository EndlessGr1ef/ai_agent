#!/usr/bin/env python3
"""
Wrapper for backward compatibility
This script provides backward compatibility for the old scrape_prts.py location.
The actual implementation is in src/data/scraping/scrape_prts.py
"""

import asyncio
from src.data.scraping.scrape_prts import main

if __name__ == "__main__":
    asyncio.run(main())
