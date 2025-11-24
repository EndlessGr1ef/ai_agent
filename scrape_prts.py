#!/usr/bin/env python3
"""
Command-line interface for PRTS Wiki scraping.

This script provides a convenient CLI for scraping PRTS Wiki content
and ingesting it into ChromaDB for RAG applications.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from src.rag.pipelines.scrape_ingest_pipeline import ScrapePipeline


async def main():
    """Main CLI function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Scrape PRTS Wiki and ingest to ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape character overview page
  python scrape_prts.py "https://prts.wiki/w/干员一览"
  
  # Scrape with custom settings
  python scrape_prts.py "https://prts.wiki/w/干员一览" --max-pages 10 --output-dir characters
  
  # Scrape without JavaScript rendering (faster but may miss content)
  python scrape_prts.py "https://prts.wiki/w/干员一览" --no-js-render
        """
    )
    
    parser.add_argument(
        "url",
        help="URL to scrape (e.g., PRTS Wiki character overview page)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of pages to scrape"
    )
    parser.add_argument(
        "--output-dir",
        default="docs/prts",
        help="Directory to save Markdown files (default: docs/prts)"
    )
    parser.add_argument(
        "--no-js-render",
        action="store_true",
        help="Disable JavaScript rendering (faster but may miss dynamic content)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('scraping.log')
        ]
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        # Create pipeline with configuration
        pipeline = ScrapePipeline(
            output_dir=args.output_dir,
            use_js_renderer=not args.no_js_render
        )
        
        logger.info(f"Starting PRTS Wiki scraping pipeline")
        logger.info(f"Target URL: {args.url}")
        logger.info(f"Max pages: {args.max_pages or 'unlimited'}")
        logger.info(f"Output directory: {args.output_dir}")
        logger.info(f"JavaScript rendering: {'disabled' if args.no_js_render else 'enabled'}")
        
        # Run pipeline with real-time saving enabled by default
        results = await pipeline.scrape_and_save(
            start_url=args.url,
            max_pages=args.max_pages,
            real_time_save=True
        )
        
        # Print results
        print("\\n" + "="*60)
        print("SCRAPING PIPELINE RESULTS")
        print("="*60)
        print(f"📄 Pages scraped: {results['scraped_count']}")
        print(f"💾 Markdown files saved: {len(results.get('saved_files', []))}")
        print(f"⏭️  Duplicates skipped: {results.get('skipped_count', 0)}")
        print(f"📁 Output directory: {args.output_dir}")
        
        print(f"\\n🔍 To ingest to ChromaDB, run:")
        print(f"   python ingest_md.py {args.output_dir}")
        
        if results.get('errors'):
            print(f"⚠️  Errors encountered: {len(results['errors'])}")
            for error in results['errors'][:3]:  # Show first 3 errors
                print(f"   • {error}")
            if len(results['errors']) > 3:
                print(f"   • ... and {len(results['errors']) - 3} more errors")
        
        # Show file locations
        if results.get('saved_files'):
            print(f"\\n📁 Files saved to: {args.output_dir}/")
            for file_path in results['saved_files'][:5]:  # Show first 5 files
                file_name = Path(file_path).name
                print(f"   • {file_name}")
            if len(results['saved_files']) > 5:
                print(f"   • ... and {len(results['saved_files']) - 5} more files")
        
        print("\\n✅ Pipeline completed successfully!")
        
        # Performance stats
        start_time = results.get('start_time')
        end_time = results.get('end_time')
        if start_time and end_time:
            from datetime import datetime
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            duration = end_dt - start_dt
            print(f"⏱️  Total time: {duration}")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        print(f"\\n❌ Error: {e}")
        return 1
    finally:
        # Cleanup
        if 'pipeline' in locals():
            await pipeline.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))