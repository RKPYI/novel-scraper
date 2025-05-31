#!/usr/bin/env python3
"""
Divine Dao Library Specialized Scraper

A specialized web scraper for divinedaolibrary.com that extracts novel information
and chapters for storage in the database.

Features:
- Scrapes novel metadata (title, author, description, cover image, etc.)
- Scrapes chapters with navigation-based approach
- Handles database operations for both novels and chapters
- Robust error handling and retry logic

Usage:
    python divinedaolibrary_scraper.py --novel-slug martial-peak --start-chapter 1
    python divinedaolibrary_scraper.py --novel-slug martial-peak --novel-only
"""

import requests
from bs4 import BeautifulSoup
import pymysql
import argparse
import time
import re
import logging
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Any
from datetime import datetime
import os
from dotenv import load_dotenv


class DivineDaoLibraryScraper:
    def __init__(self):
        """Initialize the scraper with Divine Dao Library configuration."""
        self.base_url = "https://www.divinedaolibrary.com"
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
                logging.FileHandler('divinedao_scraper.log'),
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
        novel_url = f"{self.base_url}/story/{novel_slug}"
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
            'status': 'ongoing'
        }
        
        try:
            # Extract title
            title_element = soup.find('h1', class_='story__identity-title')
            if title_element:
                novel_info['title'] = title_element.get_text(strip=True)
            
            # Extract author - look for the h3 element containing "Author:"
            author_element = soup.find('h3', string=lambda text: text and 'Author:' in text)
            if author_element:
                author_text = author_element.get_text(strip=True)
                # Extract author name from "Author: 莫默 (MOMO)" format
                if ':' in author_text:
                    novel_info['author'] = author_text.split(':', 1)[1].strip()
                else:
                    novel_info['author'] = author_text.strip()
            
            # Extract description - look for content after "Description" h3
            desc_heading = soup.find('h3', string='Description')
            if desc_heading:
                # Find the next p tag that contains description text
                current = desc_heading.next_sibling
                while current:
                    if hasattr(current, 'name') and current.name == 'p':
                        novel_info['description'] = current.get_text(strip=True)
                        break
                    current = current.next_sibling
            
            # Extract cover image
            cover_element = soup.find('img', alt=lambda x: x and 'Cover of' in x)
            if cover_element and cover_element.get('src'):
                cover_url = cover_element.get('src')
                if cover_url.startswith('//'):
                    cover_url = 'https:' + cover_url
                elif cover_url.startswith('/'):
                    cover_url = self.base_url + cover_url
                novel_info['cover_image'] = cover_url
            
            # Extract total chapters from chapter list
            chapter_links = soup.find_all('a', href=lambda x: x and 'chapter-' in x)
            novel_info['total_chapters'] = len(chapter_links)
            
            # Try to determine status
            status_element = soup.find('span', class_='status') or soup.find('div', class_='story__status')
            if status_element:
                status_text = status_element.get_text(strip=True).lower()
                if 'completed' in status_text or 'finished' in status_text:
                    novel_info['status'] = 'completed'
                elif 'hiatus' in status_text or 'paused' in status_text:
                    novel_info['status'] = 'hiatus'
            
            self.logger.info(f"Novel info extracted: {novel_info['title']} by {novel_info['author']}")
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
        return f"{self.base_url}/story/{novel_slug}/{novel_slug}-chapter-{chapter_number}"
    
    def extract_chapter_data(self, soup: BeautifulSoup, chapter_number: int) -> Optional[Dict[str, Any]]:
        """Extract chapter data from parsed HTML."""
        try:
            chapter_data = {
                'chapter_number': chapter_number,
                'title': None,
                'content': None
            }
            
            # Extract title
            title_element = soup.find('h1', class_='chapter__title')
            if title_element:
                chapter_data['title'] = title_element.get_text(strip=True)
            
            # Extract content
            content_element = soup.find('div', class_='chapter-formatting')
            if content_element:
                # Remove unwanted elements
                for unwanted in content_element.find_all(['script', 'style', 'nav', 'footer', 'header']):
                    unwanted.decompose()
                
                # Convert br tags to line breaks
                for br in content_element.find_all('br'):
                    br.replace_with('\n')
                
                # Get text with preserved paragraphs
                content = content_element.get_text(separator='\n')
                
                # Clean text
                content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
                content = re.sub(r'\n\s*\n+', '\n\n', content)  # Normalize line breaks
                content = re.sub(r'^\s+|\s+$', '', content, flags=re.MULTILINE)  # Strip line whitespace
                
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
            # Look for next chapter button
            next_element = soup.find('a', class_='button _secondary _navigation _next')
            if next_element and next_element.get('href'):
                next_url = next_element.get('href')
                if next_url.startswith('/'):
                    next_url = self.base_url + next_url
                return next_url
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
                        self.logger.error(f"Too many consecutive failures, stopping")
                        break
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                    continue
                
                # Check if chapter exists on the page
                if not soup.find('div', class_='chapter-formatting'):
                    self.logger.warning(f"Chapter {chapter_number} not found on page")
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        self.logger.error(f"Too many consecutive failures, stopping")
                        break
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                    continue
                
                # Extract chapter data
                chapter_data = self.extract_chapter_data(soup, chapter_number)
                if not chapter_data:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        break
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                    continue
                
                # Save chapter
                if self.save_chapter(novel_id, chapter_data):
                    chapters_scraped += 1
                    word_count = len(chapter_data.get('content', '').split())
                    total_words += word_count
                    consecutive_failures = 0  # Reset failure counter
                    
                    # Log progress every 10 chapters
                    if chapters_scraped % 10 == 0:
                        self.logger.info(f"Progress: {chapters_scraped} chapters scraped, {total_words:,} words")
                else:
                    consecutive_failures += 1
                
                # Get next chapter URL from navigation or build it
                next_url = self.get_next_chapter_url(soup, current_url)
                if next_url:
                    current_url = next_url
                    # Extract chapter number from URL
                    match = re.search(r'chapter-(\d+)', next_url)
                    if match:
                        chapter_number = int(match.group(1))
                    else:
                        chapter_number += 1
                else:
                    # Try building next chapter URL
                    chapter_number += 1
                    current_url = self.build_chapter_url(novel_slug, chapter_number)
                
                # Delay between requests
                time.sleep(1.0)
                
            except Exception as e:
                self.logger.error(f"Error processing chapter {chapter_number}: {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
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
    parser = argparse.ArgumentParser(description="Divine Dao Library Specialized Scraper")
    parser.add_argument(
        '--novel-slug',
        required=True,
        help='Novel slug (e.g., martial-peak)'
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
        scraper = DivineDaoLibraryScraper()
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
