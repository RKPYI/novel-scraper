#!/usr/bin/env python3
"""
NovelBin.com Specialized Scraper

A specialized web scraper for novelbin.com that extracts novel information
and chapters for storage in the database.

Features:
- Scrapes novel metadata (title, author, description, cover image, etc.)
- Scrapes chapters with navigation-based approach
- Handles database operations for both novels and chapters
- Robust error handling and retry logic

Usage:
    python novelbin_scraper.py --novel-slug mmorpg-rebirth-as-an-alchemist --start-chapter 1
    python novelbin_scraper.py --novel-slug mmorpg-rebirth-as-an-alchemist --novel-only
"""

import requests
from bs4 import BeautifulSoup
import pymysql
import argparse
import time
import re
import logging
import os
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Any
from datetime import datetime
from dotenv import load_dotenv


class NovelBinScraper:
    def __init__(self):
        """Initialize the scraper with NovelBin configuration."""
        self.base_url = "https://novelbin.com"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })
        load_dotenv()
        self.setup_logging()
        self.db_connection = None
        
    def setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('novelbin_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def connect_database(self):
        """Connect to the MySQL database using environment variables."""
        try:
            self.db_connection = pymysql.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                user=os.getenv('DB_USER', 'root'),
                password=os.getenv('DB_PASSWORD', ''),
                database=os.getenv('DB_NAME', 'novel_db'),
                charset=os.getenv('DB_CHARSET', 'utf8mb4')
            )
            self.logger.info("Database connection established")
        except pymysql.Error as e:
            self.logger.error(f"Database connection error: {e}")
            raise
    
    def fetch_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page with retry logic."""
        for attempt in range(retries + 1):
            try:
                self.logger.info(f"Fetching: {url} (attempt {attempt + 1})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                return soup
                
            except requests.RequestException as e:
                self.logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < retries:
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                else:
                    self.logger.error(f"Failed to fetch {url} after {retries + 1} attempts")
                    return None
    
    def scrape_novel_info(self, novel_slug: str) -> Optional[Dict[str, Any]]:
        """Scrape novel information from the novel's main page."""
        novel_url = f"{self.base_url}/b/{novel_slug}"
        soup = self.fetch_page(novel_url)
        
        if not soup:
            return None
        
        novel_info = {
            'slug': novel_slug,
            'title': None,
            'author': None,
            'description': None,
            'cover_image': None,
            'total_chapters': 0,
            'status': 'ongoing',
            'genres': [],
            'rating': None,
            'year': None
        }
        
        try:
            # Extract title - NovelBin uses h1 in main content or page title
            title_selectors = [
                'h1',
                '.novel-title',
                'title'
            ]
            
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title_text = title_element.get_text(strip=True)
                    # Clean up title - remove "Novel Bin" suffix if present
                    title_text = re.sub(r'\s*-\s*Novel\s*Bin.*$', '', title_text, flags=re.IGNORECASE)
                    if title_text and len(title_text) > 3:  # Ensure it's not just empty or very short
                        novel_info['title'] = title_text
                        break
            
            # Extract author - look for author links or author information
            author_patterns = [
                'a[href*="/a/"]',  # Author links typically contain /a/
                '.author a',
                '.novel-author a',
                'dt:contains("Author") + dd a',
                'strong:contains("Author") + a'
            ]
            
            for pattern in author_patterns:
                author_element = soup.select_one(pattern)
                if author_element:
                    novel_info['author'] = author_element.get_text(strip=True)
                    break
            
            # Fallback author extraction - look for text patterns
            if not novel_info['author']:
                author_text = soup.find(string=re.compile(r'Author.*:', re.IGNORECASE))
                if author_text:
                    # Find next link or text after "Author:"
                    parent = author_text.parent
                    if parent:
                        author_link = parent.find_next('a')
                        if author_link:
                            novel_info['author'] = author_link.get_text(strip=True)
            
            # Extract genres - look for genre links
            genre_selectors = [
                'a[href*="/genre/"]',
                '.genre a',
                '.genres a',
                '.novel-genres a'
            ]
            
            for selector in genre_selectors:
                genre_elements = soup.select(selector)
                if genre_elements:
                    novel_info['genres'] = [elem.get_text(strip=True) for elem in genre_elements]
                    break
            
            # Extract status - look for status information
            status_patterns = [
                'a[href*="/sort/completed"]',
                'a[href*="/sort/ongoing"]',
                '.status',
                '.novel-status'
            ]
            
            for pattern in status_patterns:
                status_element = soup.select_one(pattern)
                if status_element:
                    status_text = status_element.get_text(strip=True).lower()
                    if 'completed' in status_text or 'finished' in status_text:
                        novel_info['status'] = 'completed'
                    elif 'hiatus' in status_text or 'paused' in status_text:
                        novel_info['status'] = 'hiatus'
                    elif 'ongoing' in status_text:
                        novel_info['status'] = 'ongoing'
                    break
            
            # Extract rating
            rating_pattern = r'Rating:\s*([0-9.]+)\s*/\s*10'
            rating_match = re.search(rating_pattern, soup.get_text())
            if rating_match:
                try:
                    novel_info['rating'] = float(rating_match.group(1))
                except ValueError:
                    pass
            
            # Extract year of publishing
            year_patterns = [
                'a[href*="/year/"]',
                '.year',
                '.publish-year'
            ]
            
            for pattern in year_patterns:
                year_element = soup.select_one(pattern)
                if year_element:
                    year_text = year_element.get_text(strip=True)
                    year_match = re.search(r'(\d{4})', year_text)
                    if year_match:
                        novel_info['year'] = int(year_match.group(1))
                        break
            
            # Extract description - look for description in various locations
            description_selectors = [
                'meta[name="description"]',
                '.description',
                '.novel-description',
                '.summary',
                'p:contains("Description")'
            ]
            
            # Try meta description first
            desc_meta = soup.select_one('meta[name="description"]')
            if desc_meta and desc_meta.get('content'):
                novel_info['description'] = desc_meta.get('content').strip()
            else:
                # Look for description in page content
                description_text = soup.get_text()
                # Find description section in the text
                desc_match = re.search(r'Description\s*(.+?)(?:\n\s*Chapter\s*List|\n\s*More\s*from\s*author|$)', 
                                     description_text, re.DOTALL | re.IGNORECASE)
                if desc_match:
                    desc_content = desc_match.group(1).strip()
                    # Clean up the description
                    desc_content = re.sub(r'\s+', ' ', desc_content)
                    desc_content = re.sub(r'Novel Bin.*$', '', desc_content, flags=re.IGNORECASE)
                    if len(desc_content) > 50:  # Ensure it's substantial
                        novel_info['description'] = desc_content
            
            # Extract cover image
            cover_selectors = [
                'img[alt*="MMORPG"]',  # Specific to the example
                'img[src*="cover"]',
                '.novel-cover img',
                '.cover img',
                'img[alt*="cover"]',
                '.novel-image img'
            ]
            
            for selector in cover_selectors:
                cover_element = soup.select_one(selector)
                if cover_element and cover_element.get('src'):
                    cover_url = cover_element.get('src')
                    if cover_url.startswith('//'):
                        cover_url = 'https:' + cover_url
                    elif cover_url.startswith('/'):
                        cover_url = self.base_url + cover_url
                    novel_info['cover_image'] = cover_url
                    break
            
            # Extract total chapters by looking for "READ NOW" link and latest chapter info
            latest_chapter_text = soup.get_text()
            chapter_match = re.search(r'Chapter\s+(\d+)', latest_chapter_text)
            if chapter_match:
                novel_info['total_chapters'] = int(chapter_match.group(1))
            
            # Alternative: count chapter links if available
            if novel_info['total_chapters'] == 0:
                chapter_links = soup.find_all('a', href=re.compile(r'/chapter-\d+'))
                novel_info['total_chapters'] = len(chapter_links)
            
            self.logger.info(f"Novel info extracted: {novel_info['title']} by {novel_info['author']}")
            self.logger.info(f"Status: {novel_info['status']}, Chapters: {novel_info['total_chapters']}")
            return novel_info
            
        except Exception as e:
            self.logger.error(f"Error extracting novel info: {e}")
            return None
    
    def get_or_create_novel(self, novel_info: Dict[str, Any]) -> Optional[int]:
        """Get or create novel in database and return novel_id."""
        cursor = self.db_connection.cursor()
        
        try:
            # Check if novel exists by slug
            cursor.execute("SELECT id FROM novels WHERE slug = %s", (novel_info['slug'],))
            result = cursor.fetchone()
            
            if result:
                novel_id = result[0]
                self.logger.info(f"Found existing novel with ID: {novel_id}")
                
                # Update the novel with new information
                cursor.execute("""
                    UPDATE novels SET 
                        title = %s, author = %s, description = %s, cover_image = %s, 
                        total_chapters = %s, status = %s, updated_at = NOW()
                    WHERE id = %s
                """, (
                    novel_info['title'], novel_info['author'], novel_info['description'],
                    novel_info['cover_image'], novel_info['total_chapters'], 
                    novel_info['status'], novel_id
                ))
                self.db_connection.commit()
                self.logger.info(f"Updated existing novel: {novel_info['title']}")
            else:
                # Create new novel
                cursor.execute("""
                    INSERT INTO novels (title, slug, author, description, cover_image, 
                                      total_chapters, status, created_at, updated_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (
                    novel_info['title'], novel_info['slug'], novel_info['author'],
                    novel_info['description'], novel_info['cover_image'],
                    novel_info['total_chapters'], novel_info['status']
                ))
                self.db_connection.commit()
                novel_id = cursor.lastrowid
                self.logger.info(f"Created new novel with ID: {novel_id}")
            
            return novel_id
            
        except pymysql.Error as e:
            self.logger.error(f"Database error managing novel: {e}")
            return None
        finally:
            cursor.close()
    
    def build_chapter_url(self, novel_slug: str, chapter_number: int) -> str:
        """Build chapter URL from pattern."""
        return f"{self.base_url}/b/{novel_slug}/chapter-{chapter_number}"
    
    def extract_chapter_data(self, soup: BeautifulSoup, chapter_number: int) -> Optional[Dict[str, Any]]:
        """Extract chapter data from parsed HTML."""
        try:
            chapter_data = {
                'chapter_number': chapter_number,
                'title': None,
                'content': None
            }
            
            # Extract title - NovelBin uses h2 for chapter titles
            title_selectors = [
                'h2',
                'h1',
                '.chapter-title',
                '.entry-title'
            ]
            
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title_text = title_element.get_text(strip=True)
                    # Check if this looks like a chapter title
                    if re.search(r'chapter\s*\d+', title_text, re.IGNORECASE) or len(title_text) < 100:
                        chapter_data['title'] = title_text
                        break
            
            # If no title found, set a default
            if not chapter_data['title']:
                chapter_data['title'] = f"Chapter {chapter_number}"
            
            # NovelBin specific content extraction
            # The content is typically in the main text flow between navigation links
            page_text = soup.get_text()
            
            # Find content between navigation elements
            # Look for the pattern: navigation -> content -> navigation
            nav_pattern = r'(Prev Chapter|Next Chapter)'
            
            # Split by navigation patterns and get the middle content
            parts = re.split(nav_pattern, page_text, flags=re.IGNORECASE)
            
            # The content is usually in the middle parts
            content_candidates = []
            for i, part in enumerate(parts):
                if not re.search(nav_pattern, part, re.IGNORECASE):
                    # Clean and check if this looks like chapter content
                    cleaned_part = part.strip()
                    if len(cleaned_part) > 100:  # Substantial content
                        content_candidates.append(cleaned_part)
            
            # Find the longest content candidate (likely the chapter content)
            if content_candidates:
                content = max(content_candidates, key=len)
                
                # Clean the content
                content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
                content = re.sub(r'\n\s*\n+', '\n\n', content)  # Normalize line breaks
                
                # Remove common unwanted patterns
                content = re.sub(r'MMORPG: Rebirth as an Alchemist.*?Chapter \d+', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'Enhance your reading experience.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'Novel Bin.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'A/N.*?Thank you.*?\^\^', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'REMOVE ADS.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'Report chapter.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'Comments.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'Contact.*?ToS.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'Read Novel Online Full.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'Novel / GAME.*?$', '', content, flags=re.DOTALL | re.IGNORECASE)
                
                # Clean up extra whitespace again
                content = re.sub(r'\s+', ' ', content)
                content = content.strip()
                
                # Ensure we have substantial content
                if len(content) > 50:
                    chapter_data['content'] = content
            
            # Fallback: try to extract content from specific HTML structure
            if not chapter_data['content']:
                # Look for content in paragraph elements between navigation
                nav_elements = soup.find_all('a', string=re.compile(r'(Prev|Next)', re.IGNORECASE))
                if len(nav_elements) >= 2:
                    # Find all text nodes between the first and last navigation elements
                    start_element = nav_elements[0]
                    end_element = nav_elements[-1]
                    
                    # Get all paragraphs and text between these elements
                    content_parts = []
                    
                    # Simple approach: get all text from the page and clean it
                    full_text = soup.get_text()
                    lines = full_text.split('\n')
                    
                    # Find lines between "Chapter X" and navigation elements
                    in_content = False
                    for line in lines:
                        line = line.strip()
                        if re.match(r'Chapter \d+', line):
                            in_content = True
                            continue
                        elif re.search(r'(Prev Chapter|Next Chapter|REMOVE ADS|Report chapter)', line, re.IGNORECASE):
                            in_content = False
                            continue
                        elif in_content and len(line) > 10:
                            content_parts.append(line)
                    
                    if content_parts:
                        content = ' '.join(content_parts)
                        # Final cleanup
                        content = re.sub(r'\s+', ' ', content)
                        content = re.sub(r'A/N.*?Thank you.*?\^\^', '', content, flags=re.DOTALL | re.IGNORECASE)
                        chapter_data['content'] = content.strip()
            
            if not chapter_data['content']:
                self.logger.warning(f"No content found for chapter {chapter_number}")
                return None
                
            return chapter_data
            
        except Exception as e:
            self.logger.error(f"Error extracting chapter {chapter_number}: {e}")
            return None
    
    def get_next_chapter_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Extract the next chapter URL from the current page."""
        try:
            # Look for next chapter links
            next_selectors = [
                'a[href*="/chapter-"]:contains("Next")',
                'a:contains("Next Chapter")'
            ]
            
            for selector in next_selectors:
                next_elements = soup.select(selector)
                for next_element in next_elements:
                    href = next_element.get('href')
                    if href and '/chapter-' in href and href != current_url:
                        if href.startswith('/'):
                            href = self.base_url + href
                        return href
            
            # Alternative method: look for next chapter pattern
            next_links = soup.find_all('a', string=re.compile(r'Next', re.IGNORECASE))
            for link in next_links:
                href = link.get('href')
                if href and '/chapter-' in href:
                    if href.startswith('/'):
                        href = self.base_url + href
                    return href
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding next chapter URL: {e}")
            return None
    
    def chapter_exists_in_db(self, novel_id: int, chapter_number: int) -> bool:
        """Check if chapter already exists in database."""
        cursor = self.db_connection.cursor()
        try:
            cursor.execute(
                "SELECT id FROM chapters WHERE novel_id = %s AND chapter_number = %s",
                (novel_id, chapter_number)
            )
            return cursor.fetchone() is not None
        except pymysql.Error as e:
            self.logger.error(f"Database error checking chapter existence: {e}")
            return False
        finally:
            cursor.close()
    
    def save_chapter(self, novel_id: int, chapter_data: Dict[str, Any]) -> bool:
        """Save chapter to database."""
        cursor = self.db_connection.cursor()
        try:
            # Calculate word count
            content = chapter_data.get('content', '')
            word_count = len(content.split()) if content else 0
            
            cursor.execute(
                """INSERT INTO chapters (novel_id, chapter_number, title, content, word_count, created_at, updated_at) 
                   VALUES (%s, %s, %s, %s, %s, NOW(), NOW())""",
                (
                    novel_id,
                    chapter_data['chapter_number'],
                    chapter_data.get('title', ''),
                    content,
                    word_count
                )
            )
            self.db_connection.commit()
            
            self.logger.info(f"Chapter {chapter_data['chapter_number']} saved - {word_count} words")
            return True
        except pymysql.Error as e:
            self.logger.error(f"Database error saving chapter {chapter_data['chapter_number']}: {e}")
            return False
        finally:
            cursor.close()
    
    def scrape_chapters(self, novel_slug: str, novel_id: int, start_chapter: int = 1, 
                       end_chapter: Optional[int] = None, skip_existing: bool = True):
        """Scrape chapters using next button navigation."""
        self.logger.info(f"Starting chapter scraping from chapter {start_chapter}")
        
        # Build first chapter URL
        current_url = self.build_chapter_url(novel_slug, start_chapter)
        chapter_number = start_chapter
        consecutive_failures = 0
        max_consecutive_failures = 5
        chapters_scraped = 0
        total_words = 0
        
        while current_url and (not end_chapter or chapter_number <= end_chapter):
            try:
                # Check if chapter already exists
                if skip_existing and self.chapter_exists_in_db(novel_id, chapter_number):
                    self.logger.info(f"Chapter {chapter_number} already exists, skipping")
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                    continue
                
                # Fetch chapter page
                soup = self.fetch_page(current_url)
                if not soup:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        self.logger.error(f"Too many consecutive failures, stopping at chapter {chapter_number}")
                        break
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                    continue
                
                # Extract chapter data
                chapter_data = self.extract_chapter_data(soup, chapter_number)
                if not chapter_data:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        self.logger.error(f"Too many consecutive failures, stopping at chapter {chapter_number}")
                        break
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                    continue
                
                # Save chapter to database
                if self.save_chapter(novel_id, chapter_data):
                    chapters_scraped += 1
                    total_words += len(chapter_data.get('content', '').split())
                    consecutive_failures = 0  # Reset counter on success
                else:
                    consecutive_failures += 1
                
                # Get next chapter URL
                next_url = self.get_next_chapter_url(soup, current_url)
                if next_url:
                    current_url = next_url
                    # Extract chapter number from URL
                    next_chapter_match = re.search(r'/chapter-(\d+)', next_url)
                    if next_chapter_match:
                        chapter_number = int(next_chapter_match.group(1))
                    else:
                        chapter_number += 1
                else:
                    # Try incrementing chapter number
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                
                # Add delay between requests
                time.sleep(2)
                
            except Exception as e:
                self.logger.error(f"Error processing chapter {chapter_number}: {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    self.logger.error(f"Too many consecutive failures, stopping at chapter {chapter_number}")
                    break
                chapter_number += 1
                current_url = self.build_chapter_url(novel_slug, chapter_number)
        
        self.logger.info(f"Chapter scraping completed!")
        self.logger.info(f"   Chapters scraped: {chapters_scraped}")
        self.logger.info(f"   Total words: {total_words:,}")
        self.logger.info(f"   Last chapter attempted: {chapter_number - 1}")
    
    def scrape_novel(self, novel_slug: str, start_chapter: int = 1, 
                    end_chapter: Optional[int] = None, novel_only: bool = False,
                    skip_existing: bool = True):
        """Main scraping method."""
        self.logger.info(f"Starting scrape for novel: {novel_slug}")
        
        # Connect to database
        self.connect_database()
        
        # Scrape novel information
        novel_info = self.scrape_novel_info(novel_slug)
        if not novel_info:
            self.logger.error(f"Failed to scrape novel info for: {novel_slug}")
            return
        
        # Save/update novel in database
        novel_id = self.get_or_create_novel(novel_info)
        if not novel_id:
            self.logger.error(f"Failed to save novel to database")
            return
        
        if novel_only:
            self.logger.info(f"Novel-only mode: Novel info saved for {novel_info['title']}")
            return
        
        # Scrape chapters
        self.scrape_chapters(novel_slug, novel_id, start_chapter, end_chapter, skip_existing)
        
        # Update total chapters count
        cursor = self.db_connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM chapters WHERE novel_id = %s", (novel_id,))
            total_chapters = cursor.fetchone()[0]
            cursor.execute("UPDATE novels SET total_chapters = %s WHERE id = %s", (total_chapters, novel_id))
            self.db_connection.commit()
            self.logger.info(f"Updated total chapters count: {total_chapters}")
        except pymysql.Error as e:
            self.logger.error(f"Error updating total chapters: {e}")
        finally:
            cursor.close()
        
        # Close database connection
        if self.db_connection:
            self.db_connection.close()


def main():
    parser = argparse.ArgumentParser(description="NovelBin.com Specialized Scraper")
    parser.add_argument(
        '--novel-slug',
        required=True,
        help='Novel slug (e.g., mmorpg-rebirth-as-an-alchemist)'
    )
    parser.add_argument(
        '--start-chapter',
        type=int,
        default=1,
        help='Starting chapter number (default: 1)'
    )
    parser.add_argument(
        '--end-chapter',
        type=int,
        help='Ending chapter number (optional)'
    )
    parser.add_argument(
        '--novel-only',
        action='store_true',
        help='Only scrape novel information, not chapters'
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        default=True,
        help='Skip chapters that already exist in database'
    )
    
    args = parser.parse_args()
    
    try:
        scraper = NovelBinScraper()
        scraper.scrape_novel(
            novel_slug=args.novel_slug,
            start_chapter=args.start_chapter,
            end_chapter=args.end_chapter,
            novel_only=args.novel_only,
            skip_existing=args.skip_existing
        )
        
    except Exception as e:
        logging.error(f"Scraper failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
