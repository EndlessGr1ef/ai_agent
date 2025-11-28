"""End-to-end pipeline for scraping PRTS Wiki and ingesting to ChromaDB."""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Import existing components
from ..scrapers.prts_wiki_scraper import PRTSWikiScraper
from ..extractors.markdown_converter import MarkdownConverter

# No longer need ChromaDB imports - will use external ingest_md.py

logger = logging.getLogger(__name__)


class ScrapePipeline:
    """Pipeline for scraping PRTS Wiki and generating Markdown files."""
    
    def __init__(self,
                 output_dir: str = "scraped_content",
                 use_js_renderer: bool = True):
        """
        Initialize the scraping pipeline.
        
        Args:
            output_dir: Directory to save scraped Markdown files
            use_js_renderer: Whether to use JavaScript rendering
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize components
        self.scraper = PRTSWikiScraper(use_js_renderer=use_js_renderer)
        self.markdown_converter = MarkdownConverter()
        
    async def scrape_and_save(self,
                              start_url: str,
                              max_pages: int = None,
                              real_time_save: bool = True) -> Dict[str, Any]:
        """
        Main pipeline: scrape PRTS Wiki and save as Markdown files.
        
        Args:
            start_url: Starting URL (e.g., character overview page)
            max_pages: Maximum number of pages to scrape
            real_time_save: If True, save each page immediately after scraping
            
        Returns:
            Dictionary with pipeline results and statistics
        """
        results = {
            'scraped_count': 0,
            'saved_files': [],
            'skipped_count': 0,  # Track skipped duplicates
            'errors': [],
            'start_time': datetime.now().isoformat(),
        }
        
        try:
            logger.info(f"Starting PRTS Wiki scraping pipeline for: {start_url}")
            logger.info(f"Real-time saving: {'enabled' if real_time_save else 'disabled'}")
            
            if real_time_save:
                # Real-time mode: scrape and save each page immediately
                results = await self._scrape_and_save_realtime(start_url, max_pages, results)
            else:
                # Batch mode: scrape all pages first, then save all
                scraped_data = await self._scrape_content(start_url, max_pages)
                results['scraped_count'] = len(scraped_data)
                
                if not scraped_data:
                    logger.warning("No content scraped")
                    return results
                
                markdown_files = await self._convert_and_save(scraped_data)
                results['saved_files'] = markdown_files
            
            results['end_time'] = datetime.now().isoformat()
            logger.info(f"Pipeline completed: {results['scraped_count']} pages scraped, "
                       f"{len(results['saved_files'])} files saved, "
                       f"{results.get('skipped_count', 0)} duplicates skipped")
            
            return results
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            results['errors'].append(str(e))
            results['end_time'] = datetime.now().isoformat()
            return results
    
    async def _scrape_and_save_realtime(self, start_url: str, max_pages: int = None, results: Dict = None) -> Dict[str, Any]:
        """Scrape pages and save each one immediately as it's processed."""
        if results is None:
            results = {'scraped_count': 0, 'saved_files': [], 'errors': []}
        
        try:
            if "干员一览" in start_url or "character" in start_url.lower():
                # Get character links from all pages with pagination
                logger.info("Extracting character links with pagination...")
                character_links = await self.scraper._extract_all_character_links_with_pagination(start_url)
                
                if not character_links:
                    logger.warning("No character links found")
                    return results
                
                # Limit pages if specified
                if max_pages and len(character_links) > max_pages:
                    character_links = character_links[:max_pages]
                    logger.info(f"Limited to {max_pages} character pages")
                
                logger.info(f"Found {len(character_links)} character pages to scrape")
                
                # Process each character page individually
                for i, char_url in enumerate(character_links, 1):
                    try:
                        logger.info(f"Processing page {i}/{len(character_links)}: {char_url}")
                        
                        # Check if this page has already been scraped
                        if await self._is_already_scraped(char_url):
                            logger.info(f"⏭️  Skipping already scraped page: {char_url}")
                            continue
                        
                        # Scrape single character page
                        char_data = await self.scraper._extract_content_async(char_url)
                        
                        if char_data:
                            # Convert and save immediately
                            saved_file = await self._convert_and_save_single(char_data, i)
                            if saved_file:
                                results['saved_files'].append(saved_file)
                                results['scraped_count'] += 1
                                logger.info(f"✓ Saved: {saved_file}")
                        else:
                            logger.warning(f"No content extracted from {char_url}")
                            
                    except Exception as e:
                        error_msg = f"Error processing {char_url}: {e}"
                        logger.error(error_msg)
                        results['errors'].append(error_msg)
                        continue
            else:
                # Single page mode
                content = await self.scraper._extract_content_async(start_url)
                if content:
                    saved_file = await self._convert_and_save_single(content, 1)
                    if saved_file:
                        results['saved_files'].append(saved_file)
                        results['scraped_count'] += 1
                        logger.info(f"✓ Saved: {saved_file}")
                        
        except Exception as e:
            error_msg = f"Error in real-time scraping: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            
        return results
    
    async def _is_already_scraped(self, url: str) -> bool:
        """
        Check if a page has already been scraped based on URL and existing files.
        
        Args:
            url: URL to check
            
        Returns:
            True if page already exists, False otherwise
        """
        try:
            # Extract character name from URL for matching
            char_name = self._extract_character_name_from_url(url)
            if not char_name:
                return False
            
            # Generate expected filename
            safe_filename = self._sanitize_filename(char_name)
            expected_file = self.output_dir / f"{safe_filename}.md"
            
            # Check if file exists
            if expected_file.exists():
                logger.debug(f"Found existing file: {expected_file}")
                
                # Optionally verify the file contains the expected URL
                try:
                    with open(expected_file, 'r', encoding='utf-8') as f:
                        content = f.read(500)  # Read first 500 chars to check metadata
                        if url in content or char_name in content:
                            return True
                except Exception as e:
                    logger.debug(f"Error reading file {expected_file}: {e}")
                    # If we can't read the file, assume it exists and skip
                    return True
            
            # Also check for similar filenames (in case of encoding differences)
            similar_files = self._find_similar_files(char_name)
            if similar_files:
                logger.debug(f"Found similar file for {char_name}: {similar_files[0]}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking if page already scraped: {e}")
            return False  # If error, proceed with scraping
    
    def _extract_character_name_from_url(self, url: str) -> Optional[str]:
        """
        Extract character name from PRTS Wiki URL.
        
        Args:
            url: PRTS Wiki character page URL
            
        Returns:
            Character name if extractable, None otherwise
        """
        try:
            from urllib.parse import unquote
            
            # Extract from URL path: https://prts.wiki/w/角色名
            if '/w/' in url:
                char_part = url.split('/w/')[-1]
                # URL decode Chinese characters
                char_name = unquote(char_part)
                # Clean up any URL fragments or parameters
                char_name = char_name.split('#')[0].split('?')[0]
                return char_name.strip()
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting character name from URL {url}: {e}")
            return None
    
    def _find_similar_files(self, char_name: str) -> List[str]:
        """
        Find files with similar names to handle encoding variations.
        
        Args:
            char_name: Character name to match
            
        Returns:
            List of similar file paths
        """
        try:
            if not self.output_dir.exists():
                return []
            
            similar_files = []
            safe_name = self._sanitize_filename(char_name).lower()
            
            # Check all .md files in output directory
            for file_path in self.output_dir.glob('*.md'):
                file_stem = file_path.stem.lower()
                
                # Exact match
                if file_stem == safe_name:
                    similar_files.append(str(file_path))
                    continue
                
                # Character name similarity check
                # Remove common variations and check if core name matches
                cleaned_file = file_stem.replace('_', '').replace('-', '')
                cleaned_char = safe_name.replace('_', '').replace('-', '')
                
                if cleaned_file == cleaned_char:
                    similar_files.append(str(file_path))
                    continue
                
                # Check if character name is contained in filename or vice versa
                if (len(char_name) > 2 and 
                    (char_name in file_path.stem or file_path.stem in char_name)):
                    similar_files.append(str(file_path))
            
            return similar_files
            
        except Exception as e:
            logger.debug(f"Error finding similar files for {char_name}: {e}")
            return []
    
    async def _convert_and_save_single(self, data: Dict[str, Any], page_num: int) -> Optional[str]:
        """Convert and save a single page's data to Markdown."""
        try:
            # Use cleaned text content directly instead of HTML-to-Markdown conversion
            # This avoids issues with HTML cleaning being too aggressive
            content_text = data.get('content', '')
            
            if not content_text and data.get('raw_html'):
                # Fallback: try to convert HTML to markdown
                try:
                    markdown_result = self.markdown_converter.html_to_markdown(
                        data['raw_html'],
                        base_url=data.get('url'),
                        title=data.get('title')
                    )
                    content_text = markdown_result.get('markdown', '')
                except Exception as e:
                    logger.warning(f"HTML to Markdown conversion failed: {e}")
                    # Last resort: use raw HTML
                    content_text = data.get('raw_html', '')
            
            # Prepare markdown result with cleaned text content
            markdown_result = {
                'markdown': content_text,
                'metadata': data.get('metadata', {}),
                'word_count': len(content_text.split()) if content_text else 0,
                'character_count': len(content_text) if content_text else 0,
            }
            
            # Generate filename - prioritize name from URL path
            url = data.get('url', '')
            file_name = self._extract_character_name_from_url(url)  # This extracts the part after /w/
            
            # If URL extraction fails, fall back to title
            if not file_name:
                title = data.get('title', f'page_{page_num}')
                file_name = title
                
            safe_title = self._sanitize_filename(file_name)
            filename = f"{safe_title}.md"
            file_path = self.output_dir / filename
            
            # Add pipeline metadata
            markdown_result['metadata'].update({
                'scraped_url': data.get('url'),
                'scraped_at': data.get('extracted_at'),
                'pipeline_version': '1.0.0',
                'content_type': data.get('content_type'),
            })
            
            # Save Markdown file
            self.markdown_converter.save_markdown(
                markdown_result, 
                str(file_path),
                include_metadata=True
            )
            
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Error saving page {page_num}: {e}")
            return None
    
    async def _scrape_content(self, start_url: str, max_pages: int = None) -> List[Dict[str, Any]]:
        """Scrape content using PRTS Wiki scraper."""
        try:
            if "干员一览" in start_url or "character" in start_url.lower():
                # Scrape character overview page with pagination support
                scraped_data = await self.scraper.scrape_character_overview(start_url, max_pages)
            else:
                # Scrape single page
                content = await self.scraper._extract_content_async(start_url)
                scraped_data = [content]
            
            # Limit pages if specified
            if max_pages and len(scraped_data) > max_pages:
                scraped_data = scraped_data[:max_pages]
                logger.info(f"Limited to {max_pages} pages")
            
            return scraped_data
            
        except Exception as e:
            logger.error(f"Error scraping content: {e}")
            return []
    
    async def _convert_and_save(self, scraped_data: List[Dict[str, Any]]) -> List[str]:
        """Convert scraped content to Markdown and save files."""
        saved_files = []
        
        for i, data in enumerate(scraped_data):
            try:
                # Convert HTML to Markdown
                if data.get('raw_html'):
                    markdown_result = self.markdown_converter.html_to_markdown(
                        data['raw_html'],
                        base_url=data.get('url'),
                        title=data.get('title')
                    )
                else:
                    # Use cleaned content if no raw HTML
                    markdown_result = {
                        'markdown': data.get('content', ''),
                        'metadata': data.get('metadata', {})
                    }
                
                # Generate filename - prioritize name from URL path
                url = data.get('url', '')
                file_name = self._extract_character_name_from_url(url)  # This extracts the part after /w/
                
                # If URL extraction fails, fall back to title
                if not file_name:
                    title = data.get('title', f'page_{i+1}')
                    file_name = title
                
                safe_title = self._sanitize_filename(file_name)
                filename = f"{safe_title}.md"
                file_path = self.output_dir / filename
                
                # Add pipeline metadata
                markdown_result['metadata'].update({
                    'scraped_url': data.get('url'),
                    'scraped_at': data.get('extracted_at'),
                    'pipeline_version': '1.0.0',
                    'content_type': data.get('content_type'),
                })
                
                # Save Markdown file
                self.markdown_converter.save_markdown(
                    markdown_result, 
                    str(file_path),
                    include_metadata=True
                )
                
                saved_files.append(str(file_path))
                logger.info(f"Saved: {filename}")
                
            except Exception as e:
                logger.error(f"Error saving page {i+1}: {e}")
                continue
        
        return saved_files
    
    def _extract_topic_from_title(self, title: str) -> str:
        """Extract topic from page title."""
        if not title:
            return 'Unknown'
        
        # Clean title
        clean_title = title.replace(' - PRTS', '').replace(' - 明日方舟', '').strip()
        
        # Limit length
        if len(clean_title) > 50:
            clean_title = clean_title[:50] + '...'
        
        return clean_title
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for saving."""
        import re
        
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'\s+', '_', filename)
        filename = filename.strip('._')
        
        # Limit length
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename or 'untitled'
    
    async def close(self):
        """Cleanup resources."""
        if hasattr(self.scraper, '_close_js_renderer'):
            await self.scraper._close_js_renderer()


# Convenience function for command-line usage
async def main(start_url: str, 
               max_pages: int = None,
               output_dir: str = "scraped_content"):
    """Main function for command-line usage."""
    
    pipeline = ScrapePipeline(
        output_dir=output_dir,
        use_js_renderer=True
    )
    
    try:
        results = await pipeline.scrape_and_save(
            start_url=start_url,
            max_pages=max_pages
        )
        
        print(f"Scraping Results:")
        print(f"- Scraped: {results['scraped_count']} pages")
        print(f"- Saved: {len(results['saved_files'])} Markdown files")
        print(f"- Output directory: {output_dir}")
        
        if results['errors']:
            print(f"- Errors: {len(results['errors'])}")
            for error in results['errors']:
                print(f"  * {error}")
        
        print(f"\nTo ingest to ChromaDB, run:")
        print(f"python ingest_md.py {output_dir}")
        
        return results
        
    finally:
        await pipeline.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape PRTS Wiki and ingest to ChromaDB")
    parser.add_argument("url", help="Starting URL to scrape")
    parser.add_argument("--max-pages", type=int, help="Maximum number of pages to scrape")
    parser.add_argument("--output-dir", default="scraped_content", help="Output directory for Markdown files")
    
    args = parser.parse_args()
    
    # Setup logging with UTF-8 encoding support
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('scraping_pipeline.log', encoding='utf-8')
        ]
    )
    
    # Run pipeline
    asyncio.run(main(
        start_url=args.url,
        max_pages=args.max_pages,
        output_dir=args.output_dir
    ))