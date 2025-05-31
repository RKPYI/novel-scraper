#!/usr/bin/env python3
"""
Wuxiaworld.site Specialized Scraper

A specialized web scraper for wuxiaworld.site that extracts novel information
and chapters for storage in the database.

Features:
- Scrapes novel metadata (title, author, description, cover image, etc.)
- Scrapes chapters with markdown-style headers (### Chapter X)
- Handles navigation-based approach with "[ Next]" links
- Robust error handling and retry logic
- Database operations for both novels and chapters

Usage:
    python wuxiaworld_site_scraper.py --novel-slug not-all-heroes-from-earth-are-bad --start-chapter 1
    python wuxiaworld_site_scraper.py --novel-slug not-all-heroes-from-earth-are-bad --novel-only
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


class WuxiaworldSiteScraper:
    def __init__(self):
        """Initialize the scraper with Wuxiaworld.site configuration."""
        self.base_url = "https://wuxiaworld.site"
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
                logging.FileHandler('wuxiaworld_site_scraper.log'),
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
                
                # Check if we were redirected to a different URL
                if response.url != url:
                    self.logger.warning(f"Redirected from {url} to {response.url}")
                    # If redirected to novel homepage, return None
                    if '/novel/' in response.url and '/chapter-' not in response.url:
                        self.logger.warning(f"Redirected to novel homepage, chapter likely doesn't exist")
                        return None
                
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
        novel_url = f"{self.base_url}/novel/{novel_slug}"
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
            'genres': []
        }
        
        try:
            # Extract title from h1 or title tag
            title_element = soup.find('h1') or soup.find('title')
            if title_element:
                title_text = title_element.get_text(strip=True)
                # Clean up title if it contains site name
                if ' - ' in title_text:
                    novel_info['title'] = title_text.split(' - ')[0].strip()
                else:
                    novel_info['title'] = title_text
            
            # Extract author - look for various patterns specific to wuxiaworld.site
            author_element = None
            
            # Try to find "Author(s)" section
            author_heading = soup.find(string=lambda text: text and 'Author(s)' in text)
            if author_heading:
                # Find the next sibling that contains the author link/text
                current = author_heading.parent
                while current:
                    next_elem = current.find_next_sibling()
                    if next_elem:
                        author_link = next_elem.find('a')
                        if author_link:
                            novel_info['author'] = author_link.get_text(strip=True)
                            break
                        elif next_elem.get_text(strip=True):
                            novel_info['author'] = next_elem.get_text(strip=True)
                            break
                    current = next_elem
            
            # Fallback to other patterns if author not found
            if not novel_info['author']:
                author_selectors = [
                    'span.author',
                    'div.author',
                    '.novel-author',
                    '.author-name'
                ]
                for selector in author_selectors:
                    author_element = soup.select_one(selector)
                    if author_element:
                        novel_info['author'] = author_element.get_text(strip=True)
                        break
                
                # Try to find text containing "Author:"
                if not novel_info['author']:
                    author_text_elem = soup.find(string=lambda x: x and 'Author:' in x)
                    if author_text_elem:
                        author_text = author_text_elem.strip()
                        if ':' in author_text:
                            novel_info['author'] = author_text.split(':', 1)[1].strip()
                        else:
                            novel_info['author'] = author_text.strip()
            
            # Extract description - look for meta description or content divs
            desc_meta = soup.find('meta', attrs={'name': 'description'})
            if desc_meta and desc_meta.get('content'):
                novel_info['description'] = desc_meta.get('content').strip()
            else:
                # Look for description in content
                desc_selectors = [
                    'div.summary',
                    'div.description', 
                    'div.novel-description',
                    'div.content p',
                    '.entry-content p'
                ]
                for selector in desc_selectors:
                    desc_element = soup.select_one(selector)
                    if desc_element and desc_element.get_text(strip=True):
                        novel_info['description'] = desc_element.get_text(strip=True)
                        break
            
            # Extract cover image - enhanced for wuxiaworld.site
            cover_selectors = [
                'img.cover',
                'img.novel-cover',
                'div.cover img',
                'div.novel-image img',
                'img[alt*="cover"]',
                'img[src*="cover"]',
                '.summary-image img',
                '.novel-thumbnail img',
                '.wp-post-image'
            ]
            
            for selector in cover_selectors:
                cover_element = soup.select_one(selector)
                if cover_element and cover_element.get('src'):
                    cover_url = cover_element.get('src')
                    # Handle different URL formats
                    if cover_url.startswith('//'):
                        cover_url = 'https:' + cover_url
                    elif cover_url.startswith('/'):
                        cover_url = self.base_url + cover_url
                    elif not cover_url.startswith('http'):
                        cover_url = self.base_url + '/' + cover_url
                    novel_info['cover_image'] = cover_url
                    break
            
            # Additional cover image search - look for any img near the title
            if not novel_info['cover_image']:
                # Find images that might be cover images based on size or position
                all_images = soup.find_all('img')
                for img in all_images:
                    src = img.get('src', '')
                    alt = img.get('alt', '')
                    
                    # Skip small images, logos, icons
                    if any(skip in src.lower() for skip in ['icon', 'logo', 'avatar', 'ad', 'banner']):
                        continue
                    if any(skip in alt.lower() for skip in ['icon', 'logo', 'avatar', 'ad', 'banner']):
                        continue
                    
                    # Look for images that might be covers
                    if src and (
                        'upload' in src.lower() or 
                        'thumb' in src.lower() or
                        'cover' in src.lower() or
                        novel_slug in src.lower()
                    ):
                        cover_url = src
                        if cover_url.startswith('//'):
                            cover_url = 'https:' + cover_url
                        elif cover_url.startswith('/'):
                            cover_url = self.base_url + cover_url
                        elif not cover_url.startswith('http'):
                            cover_url = self.base_url + '/' + cover_url
                        novel_info['cover_image'] = cover_url
                        break
            
            # Extract chapter links to determine total chapters
            chapter_links = soup.find_all('a', href=lambda x: x and '/chapter-' in x)
            if not chapter_links:
                # Alternative patterns for chapter links
                chapter_links = soup.find_all('a', href=lambda x: x and 'chapter' in x.lower())
            
            novel_info['total_chapters'] = len(chapter_links)
            
            # Extract genres if available
            genre_selectors = [
                '.genres a',
                '.genre-tags a', 
                '.tags a',
                'span.genre'
            ]
            for selector in genre_selectors:
                genre_elements = soup.select(selector)
                if genre_elements:
                    novel_info['genres'] = [elem.get_text(strip=True) for elem in genre_elements]
                    break
            
            # Try to determine status
            status_selectors = [
                '.status',
                '.novel-status',
                'span.completed',
                'span.ongoing'
            ]
            for selector in status_selectors:
                status_element = soup.select_one(selector)
                if status_element:
                    status_text = status_element.get_text(strip=True).lower()
                    if 'completed' in status_text or 'finished' in status_text:
                        novel_info['status'] = 'completed'
                    elif 'hiatus' in status_text or 'paused' in status_text:
                        novel_info['status'] = 'hiatus'
                    break
            
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
        return f"{self.base_url}/novel/{novel_slug}/chapter-{chapter_number}/"
    
    def extract_chapter_data(self, soup: BeautifulSoup, chapter_number: int) -> Optional[Dict[str, Any]]:
        """Extract chapter data from parsed HTML with wuxiaworld.site specific formatting."""
        try:
            # First check if this is actually a chapter page
            page_text = soup.get_text().lower()
            if 'summary' in page_text and 'author(s)' in page_text and 'genre(s)' in page_text:
                self.logger.warning(f"Chapter {chapter_number} page appears to be novel homepage, skipping")
                return None
            
            chapter_data = {
                'chapter_number': chapter_number,
                'title': None,
                'content': None
            }
            
            # Extract title - wuxiaworld.site uses various patterns
            title_selectors = [
                'h1.entry-title',
                'h1.chapter-title', 
                'h1',
                '.post-title h1',
                '.chapter-title'
            ]
            
            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title_text = title_element.get_text(strip=True)
                    # Clean up title
                    title_text = re.sub(r'^Chapter\s*\d+\s*[-:]?\s*', '', title_text, flags=re.IGNORECASE)
                    chapter_data['title'] = title_text
                    break
            
            # If no title found from HTML elements, set a default title
            if not chapter_data['title']:
                chapter_data['title'] = f"Chapter {chapter_number}"
            
            # Extract content - wuxiaworld.site specific selectors
            content_selectors = [
                '.entry-content',
                '.post-content',
                '.chapter-content',
                '.content',
                '#content',
                '.post-body'
            ]
            
            content_element = None
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    break
            
            if content_element:
                # Remove unwanted elements
                for unwanted in content_element.find_all([
                    'script', 'style', 'nav', 'footer', 'header', 
                    '.navigation', '.nav', '.prev-next', 
                    '.chapter-nav', '.ads', '.advertisement'
                ]):
                    unwanted.decompose()
                
                # Remove navigation elements with "Next" or "Previous" text
                for nav_elem in content_element.find_all(['a', 'div', 'span'], 
                                                       string=lambda x: x and ('next' in x.lower() or 'previous' in x.lower() or 'prev' in x.lower())):
                    nav_elem.decompose()
                
                # Convert br tags to line breaks
                for br in content_element.find_all('br'):
                    br.replace_with('\n')
                
                # Get text content
                content_text = content_element.get_text(separator='\n')
                
                # Process markdown-style headers (### Chapter X, ### Prologue)
                lines = content_text.split('\n')
                processed_lines = []
                chapter_found = False
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        if processed_lines and processed_lines[-1]:  # Only add if previous line has content
                            processed_lines.append('')
                        continue
                    
                    # Check for markdown headers
                    if line.startswith('###'):
                        header_text = line.replace('###', '').strip()
                        if re.match(r'(chapter\s*\d+|prologue|epilogue)', header_text, re.IGNORECASE):
                            chapter_found = True
                            # Use this header as title if we don't have one yet
                            if not chapter_data['title'] or chapter_data['title'] == f"Chapter {chapter_number}":
                                chapter_data['title'] = header_text
                            processed_lines.append(f"\n=== {header_text} ===\n")
                            continue
                    
                    # Skip navigation text
                    if re.match(r'^\[\s*(next|previous|prev)\s*\]', line, re.IGNORECASE):
                        continue
                    
                    # Skip if line is just navigation or metadata
                    if any(skip_text in line.lower() for skip_text in [
                        'table of contents', 'next chapter', 'previous chapter',
                        'click here', 'read more', 'subscribe', 'donate'
                    ]):
                        continue
                    
                    processed_lines.append(line)
                
                # Join and clean content
                content = '\n'.join(processed_lines)
                content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)  # Normalize multiple line breaks
                content = content.strip()
                
                # Ensure we have actual chapter content
                if content and len(content.split()) > 20:  # Minimum word count threshold
                    # Additional validation - check if content looks like a novel summary
                    content_lower = content.lower()
                    summary_indicators = ['summary', 'author(s)', 'genre(s)', 'alternative', 'rating', 'status']
                    summary_count = sum(1 for indicator in summary_indicators if indicator in content_lower)
                    
                    if summary_count >= 3:
                        self.logger.warning(f"Chapter {chapter_number} content appears to be novel summary, not chapter content")
                        return None
                    
                    # Check if content has actual story elements (dialogue, narrative)
                    story_indicators = ['"', '"', '"', 'he said', 'she said', 'thought', 'looked', 'walked']
                    story_count = sum(1 for indicator in story_indicators if indicator in content_lower)
                    
                    if story_count == 0 and len(content.split()) < 200:
                        self.logger.warning(f"Chapter {chapter_number} content doesn't appear to be story content")
                        return None
                    
                    chapter_data['content'] = content
                else:
                    self.logger.warning(f"Chapter {chapter_number} content too short or empty")
                    return None
            
            # Final check: ensure we have a title
            if not chapter_data['title']:
                chapter_data['title'] = f"Chapter {chapter_number}"
            
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
            # Look for next chapter links with various patterns
            next_selectors = [
                'a[href*="chapter-"]:contains("Next")',
                'a.next-chapter',
                'a.next',
                '.chapter-nav a[href*="chapter-"]',
                '.navigation a[href*="chapter-"]'
            ]
            
            # Find links containing "next" text
            next_links = soup.find_all('a', string=lambda x: x and 'next' in x.lower())
            for link in next_links:
                href = link.get('href')
                if href and 'chapter-' in href:
                    if href.startswith('/'):
                        return self.base_url + href
                    elif href.startswith('http'):
                        return href
            
            # Look for navigation patterns specific to wuxiaworld.site
            nav_divs = soup.find_all(['div', 'nav'], class_=lambda x: x and any(
                nav_class in x.lower() for nav_class in ['nav', 'chapter', 'next', 'pagination']
            ))
            
            for nav_div in nav_divs:
                next_links = nav_div.find_all('a', href=lambda x: x and 'chapter-' in x)
                for link in next_links:
                    link_text = link.get_text(strip=True).lower()
                    if 'next' in link_text:
                        href = link.get('href')
                        if href.startswith('/'):
                            return self.base_url + href
                        elif href.startswith('http'):
                            return href
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding next chapter URL: {e}")
            return None
    
    def is_actual_chapter_page(self, soup: BeautifulSoup, current_url: str, novel_slug: str, chapter_number: int) -> bool:
        """Check if we're actually on a chapter page or redirected to novel homepage."""
        try:
            # Check if URL contains the expected chapter pattern
            expected_chapter_pattern = f"chapter-{chapter_number}"
            if expected_chapter_pattern not in current_url:
                return False
            
            # Check for novel homepage indicators
            novel_homepage_indicators = [
                'div.summary',  # Summary section on novel page
                'div.novel-info',  # Novel info section
                '.author-info',  # Author info
                '.genre-tags',  # Genre tags
                'h2:contains("Summary")',  # Summary heading
                'h2:contains("SUMMARY")',  # Summary heading uppercase
                '.rating',  # Rating section
                '.novel-status'  # Status section
            ]
            
            for indicator in novel_homepage_indicators:
                if soup.select_one(indicator):
                    self.logger.debug(f"Found novel homepage indicator: {indicator}")
                    return False
            
            # Check for specific text that indicates we're on novel homepage
            page_text = soup.get_text().lower()
            homepage_text_indicators = [
                'summary',
                'author(s)',
                'genre(s)',
                'alternative',
                'status',
                'rating'
            ]
            
            # If we find multiple homepage indicators, likely not a chapter page
            found_indicators = sum(1 for indicator in homepage_text_indicators if indicator in page_text)
            if found_indicators >= 3:
                self.logger.debug(f"Found {found_indicators} homepage text indicators")
                return False
            
            # Check if we have actual chapter content patterns
            chapter_content_indicators = [
                # Look for chapter headers in the content
                soup.find(string=lambda x: x and re.match(r'###\s*(chapter\s*\d+|prologue|epilogue)', x, re.IGNORECASE)),
                # Look for "Next" navigation specific to chapters
                soup.find('a', string=lambda x: x and 'next' in x.lower() and 'chapter' in soup.get_text().lower()),
                # Look for chapter-specific content selectors
                soup.select_one('.entry-content'),
                soup.select_one('.post-content'),
                soup.select_one('.chapter-content')
            ]
            
            # If we have chapter content indicators, it's likely a chapter page
            if any(chapter_content_indicators):
                # Double-check by looking for substantial text content
                content_selectors = ['.entry-content', '.post-content', '.chapter-content', '.content']
                for selector in content_selectors:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        content_text = content_elem.get_text(strip=True)
                        # If content is substantial and contains story-like text, it's likely a chapter
                        if len(content_text.split()) > 100:
                            return True
            
            # If we reach here and don't have clear chapter indicators, probably not a chapter page
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking if page is actual chapter: {e}")
            # In case of error, assume it's not a chapter page to be safe
            return False

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
                
                # Check if we're actually on a chapter page or redirected to novel homepage
                is_chapter_page = self.is_actual_chapter_page(soup, current_url, novel_slug, chapter_number)
                
                if not is_chapter_page:
                    self.logger.warning(f"Chapter {chapter_number} not found - redirected to novel homepage or invalid page")
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
                
                # Get next chapter URL
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
                time.sleep(2.0)  # Be respectful to the server
                
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
    parser = argparse.ArgumentParser(description="Wuxiaworld.site Specialized Scraper")
    parser.add_argument(
        '--novel-slug',
        required=True,
        help='Novel slug (e.g., not-all-heroes-from-earth-are-bad)'
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
        scraper = WuxiaworldSiteScraper()
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
