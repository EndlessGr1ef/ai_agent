"""HTML to Markdown converter with content cleaning and formatting."""

import logging
import re
from typing import Dict, Any, Optional, List
from markdownify import markdownify as md
from bs4 import BeautifulSoup, Tag, NavigableString
import html

logger = logging.getLogger(__name__)


class MarkdownConverter:
    """Converts HTML content to clean, structured Markdown."""
    
    def __init__(self, 
                 strip_tags: List[str] = None,
                 convert_tables: bool = True,
                 preserve_links: bool = True,
                 heading_style: str = "atx"):
        """
        Initialize the Markdown converter.
        
        Args:
            strip_tags: HTML tags to completely remove
            convert_tables: Whether to convert HTML tables to Markdown
            preserve_links: Whether to preserve links in Markdown format
            heading_style: Heading style ('atx' for #, 'underlined' for === ---)
        """
        self.strip_tags = strip_tags or [
            'script', 'style', 'nav', 'header', 'footer',
            'aside', 'form', 'input', 'button'
        ]
        self.convert_tables = convert_tables
        self.preserve_links = preserve_links
        self.heading_style = heading_style
        
        # Configure markdownify options
        # Note: Can't use both 'strip' and 'convert' - using convert only
        self.md_options = {
            'heading_style': heading_style,
            'bullets': '-',
            'convert': self._get_convert_tags(),
        }
    
    def _get_convert_tags(self) -> List[str]:
        """Get list of HTML tags to convert to Markdown."""
        convert_tags = [
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'p', 'br', 'strong', 'b', 'em', 'i',
            'ul', 'ol', 'li', 'blockquote', 'code', 'pre'
        ]
        
        if self.preserve_links:
            convert_tags.extend(['a'])
        
        if self.convert_tables:
            convert_tags.extend(['table', 'thead', 'tbody', 'tr', 'th', 'td'])
        
        return convert_tags
    
    def html_to_markdown(self, html_content: str, 
                        base_url: str = None,
                        title: str = None) -> Dict[str, Any]:
        """
        Convert HTML content to Markdown with metadata.
        
        Args:
            html_content: Raw HTML content
            base_url: Base URL for resolving relative links
            title: Page title to include in output
            
        Returns:
            Dictionary containing Markdown content and metadata
        """
        try:
            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Clean HTML before conversion
            cleaned_soup = self._clean_html(soup, base_url)
            
            # Convert to Markdown
            markdown_content = md(
                str(cleaned_soup),
                **self.md_options
            )
            
            # Post-process Markdown
            processed_markdown = self._post_process_markdown(markdown_content)
            
            # Add title if provided
            if title:
                processed_markdown = f"# {title}\n\n{processed_markdown}"
            
            # Extract metadata
            metadata = self._extract_html_metadata(soup)
            
            result = {
                'markdown': processed_markdown,
                'metadata': metadata,
                'word_count': len(processed_markdown.split()),
                'character_count': len(processed_markdown),
                'has_tables': 'table' in html_content.lower(),
                'has_images': 'img' in html_content.lower(),
                'has_links': '[' in processed_markdown and '](' in processed_markdown,
            }
            
            logger.info(f"Converted HTML to Markdown ({result['word_count']} words)")
            return result
            
        except Exception as e:
            logger.error(f"Error converting HTML to Markdown: {e}")
            return {
                'markdown': '',
                'metadata': {},
                'error': str(e)
            }
    
    def _clean_html(self, soup: BeautifulSoup, base_url: str = None) -> BeautifulSoup:
        """Clean HTML content before Markdown conversion."""
        # Remove unwanted tags completely
        for tag_name in self.strip_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, NavigableString) and 
                                    str(text).strip().startswith('<!--')):
            comment.extract()
        
        # Clean up specific wiki elements
        self._clean_wiki_elements(soup)
        
        # Fix relative URLs if base_url provided
        if base_url:
            self._fix_relative_urls(soup, base_url)
        
        # Clean up empty elements
        self._remove_empty_elements(soup)
        
        return soup
    
    def _clean_wiki_elements(self, soup: BeautifulSoup) -> None:
        """Clean wiki-specific elements."""
        # Remove edit sections
        for edit_section in soup.find_all(class_='mw-editsection'):
            edit_section.decompose()
        
        # Remove reference links like [1], [2], etc.
        for ref in soup.find_all('sup', class_='reference'):
            ref.decompose()
        
        # Clean up navigation boxes
        for navbox in soup.find_all(class_=['navbox', 'navigation-box']):
            navbox.decompose()
        
        # Remove table of contents
        toc = soup.find(id='toc')
        if toc:
            toc.decompose()
        
        # Clean up infobox styling
        for infobox in soup.find_all(class_='infobox'):
            # Remove style attributes
            if infobox.get('style'):
                del infobox['style']
            
            # Clean nested elements
            for element in infobox.find_all():
                if element.get('style'):
                    del element['style']
    
    def _fix_relative_urls(self, soup: BeautifulSoup, base_url: str) -> None:
        """Convert relative URLs to absolute URLs."""
        from urllib.parse import urljoin
        
        # Fix links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if not href.startswith(('http://', 'https://', 'mailto:', '#')):
                a_tag['href'] = urljoin(base_url, href)
        
        # Fix images
        for img_tag in soup.find_all('img', src=True):
            src = img_tag['src']
            if not src.startswith(('http://', 'https://', 'data:')):
                img_tag['src'] = urljoin(base_url, src)
    
    def _remove_empty_elements(self, soup: BeautifulSoup) -> None:
        """Remove empty HTML elements."""
        # Tags that should be removed if empty
        empty_tags = ['p', 'div', 'span', 'strong', 'em', 'b', 'i']
        
        for tag_name in empty_tags:
            for tag in soup.find_all(tag_name):
                if not tag.get_text(strip=True) and not tag.find_all(['img', 'br']):
                    tag.decompose()
    
    def _post_process_markdown(self, markdown: str) -> str:
        """Post-process Markdown content for better formatting."""
        # Fix excessive line breaks
        markdown = re.sub(r'\n{4,}', '\n\n\n', markdown)
        
        # Clean up table formatting
        markdown = self._fix_table_formatting(markdown)
        
        # Fix list formatting
        markdown = self._fix_list_formatting(markdown)
        
        # Clean up links
        markdown = self._clean_markdown_links(markdown)
        
        # Remove excessive whitespace
        markdown = re.sub(r'[ \t]+', ' ', markdown)
        markdown = re.sub(r'\n +', '\n', markdown)
        
        # Ensure proper spacing around headings
        markdown = re.sub(r'\n(#{1,6})', r'\n\n\1', markdown)
        markdown = re.sub(r'(#{1,6}[^\n]*)\n(?!\n)', r'\1\n\n', markdown)
        
        return markdown.strip()
    
    def _fix_table_formatting(self, markdown: str) -> str:
        """Fix Markdown table formatting issues."""
        lines = markdown.split('\n')
        fixed_lines = []
        in_table = False
        
        for line in lines:
            # Detect table rows
            if '|' in line and line.strip().startswith('|') and line.strip().endswith('|'):
                if not in_table:
                    # Add separator before table
                    if fixed_lines and fixed_lines[-1].strip():
                        fixed_lines.append('')
                    in_table = True
                
                # Clean up table row
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                fixed_line = '| ' + ' | '.join(cells) + ' |'
                fixed_lines.append(fixed_line)
            else:
                if in_table:
                    # Add separator after table
                    fixed_lines.append('')
                    in_table = False
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _fix_list_formatting(self, markdown: str) -> str:
        """Fix Markdown list formatting issues."""
        lines = markdown.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            # Fix nested list indentation
            if re.match(r'^[\s]*[-*+]\s', line):
                # Ensure proper spacing before lists
                if (i > 0 and 
                    fixed_lines and 
                    not re.match(r'^[\s]*[-*+]\s', lines[i-1]) and
                    fixed_lines[-1].strip()):
                    fixed_lines.append('')
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _clean_markdown_links(self, markdown: str) -> str:
        """Clean up Markdown links."""
        # Remove empty links
        markdown = re.sub(r'\[([^\]]*)\]\(\s*\)', r'\1', markdown)
        
        # Fix malformed links
        markdown = re.sub(r'\[([^\]]*)\]\(([^)]*)\s+([^)]*)\)', r'[\1](\2)', markdown)
        
        return markdown
    
    def _extract_html_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract metadata from HTML structure."""
        metadata = {}
        
        # Count different elements
        metadata['heading_count'] = len(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']))
        metadata['paragraph_count'] = len(soup.find_all('p'))
        metadata['link_count'] = len(soup.find_all('a', href=True))
        metadata['image_count'] = len(soup.find_all('img'))
        metadata['table_count'] = len(soup.find_all('table'))
        metadata['list_count'] = len(soup.find_all(['ul', 'ol']))
        
        # Extract language if available
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            metadata['language'] = html_tag['lang']
        
        # Check for specific content types
        metadata['has_infobox'] = bool(soup.find(class_=['infobox', 'character-info']))
        metadata['has_navbox'] = bool(soup.find(class_=['navbox', 'navigation-box']))
        metadata['has_references'] = bool(soup.find(class_='references'))
        
        return metadata
    
    def save_markdown(self, content: Dict[str, Any], 
                     file_path: str,
                     include_metadata: bool = True) -> None:
        """
        Save Markdown content to file.
        
        Args:
            content: Content dictionary from html_to_markdown
            file_path: Path to save the Markdown file
            include_metadata: Whether to include metadata as YAML frontmatter
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if include_metadata and 'metadata' in content:
                    # Write YAML frontmatter
                    f.write("---\n")
                    for key, value in content['metadata'].items():
                        f.write(f"{key}: {value}\n")
                    f.write(f"word_count: {content.get('word_count', 0)}\n")
                    f.write(f"character_count: {content.get('character_count', 0)}\n")
                    f.write("---\n\n")
                
                # Write Markdown content
                f.write(content['markdown'])
            
            logger.info(f"Saved Markdown file: {file_path}")
            
        except Exception as e:
            logger.error(f"Error saving Markdown file {file_path}: {e}")
            raise