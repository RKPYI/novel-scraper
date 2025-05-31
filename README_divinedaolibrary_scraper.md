# Divine Dao Library Scraper

A specialized web scraper for divinedaolibrary.com that extracts novel information and chapters for storage in the database.

## Features

- ✅ Scrapes novel metadata (title, author, description, cover image, total chapters, status)
- ✅ Scrapes chapters with navigation-based approach
- ✅ Handles database operations for both novels and chapters
- ✅ Robust error handling and retry logic
- ✅ Skip existing chapters functionality
- ✅ Word count calculation
- ✅ Proper URL pattern handling for Divine Dao Library

## Usage Examples

### Scrape Novel Information Only
```bash
python divinedaolibrary_scraper.py --novel-slug martial-peak --novel-only
```

### Scrape Chapters from Start
```bash
python divinedaolibrary_scraper.py --novel-slug martial-peak --start-chapter 1
```

### Scrape Specific Range of Chapters
```bash
python divinedaolibrary_scraper.py --novel-slug martial-peak --start-chapter 1 --end-chapter 100
```

### Continue from Specific Chapter
```bash
python divinedaolibrary_scraper.py --novel-slug martial-peak --start-chapter 50
```

## Command Line Arguments

- `--novel-slug` (required): Novel slug from the URL (e.g., "martial-peak")
- `--start-chapter` (optional): Starting chapter number (default: 1)
- `--end-chapter` (optional): Ending chapter number (if not specified, scrapes until no more chapters)
- `--novel-only` (optional): Only scrape novel information, not chapters
- `--skip-existing` (optional): Skip chapters that already exist in database (default: True)

## Database Schema

### Novels Table
The scraper populates the following fields:
- `title`: Novel title
- `slug`: URL-friendly slug
- `author`: Author name
- `description`: Novel description/synopsis
- `cover_image`: Cover image URL
- `total_chapters`: Total number of chapters available
- `status`: Publication status (ongoing/completed/hiatus)
- `created_at`: When record was created
- `updated_at`: When record was last updated

### Chapters Table
The scraper populates the following fields:
- `novel_id`: Foreign key to novels table
- `chapter_number`: Chapter number
- `title`: Chapter title
- `content`: Chapter content (cleaned text)
- `word_count`: Word count of the chapter
- `created_at`: When record was created
- `updated_at`: When record was last updated

## URL Pattern

The scraper handles Divine Dao Library's URL pattern:
```
https://www.divinedaolibrary.com/story/{novel_slug}/{novel_slug}-chapter-{chapter_number}
```

Examples:
- Novel page: `https://www.divinedaolibrary.com/story/martial-peak`
- Chapter page: `https://www.divinedaolibrary.com/story/martial-peak/martial-peak-chapter-1`

## Error Handling

- Automatic retry on failed requests (up to 3 attempts)
- Exponential backoff for retries
- Stops after 5 consecutive failures
- Comprehensive logging to `divinedao_scraper.log`
- Database error handling with rollback

## Performance Features

- 1-second delay between requests to be respectful to the server
- Skip existing chapters to avoid duplicates
- Batch processing with progress logging every 10 chapters
- Memory-efficient text processing

## Example Output

```
2025-05-29 10:37:20,134 - INFO - Starting scrape for novel: martial-peak
2025-05-29 10:37:20,134 - INFO - Database connection established
2025-05-29 10:37:25,191 - INFO - Novel info extracted: Martial Peak by 莫默 (MOMO)
2025-05-29 10:37:25,194 - INFO - Updated existing novel: Martial Peak
2025-05-29 10:37:25,194 - INFO - Starting chapter scraping from chapter 1
2025-05-29 10:37:27,811 - INFO - Chapter 1 saved - 2331 words
2025-05-29 10:37:30,809 - INFO - Chapter 2 saved - 1066 words
2025-05-29 10:37:33,918 - INFO - Chapter 3 saved - 1460 words
2025-05-29 10:37:34,938 - INFO - Chapter scraping completed!
2025-05-29 10:37:34,938 - INFO -    Chapters scraped: 3
2025-05-29 10:37:34,938 - INFO -    Total words: 4,857
```

## Requirements

- Python 3.7+
- requests
- beautifulsoup4
- pymysql
- lxml

Install dependencies:
```bash
pip install requests beautifulsoup4 pymysql lxml
```

## Database Configuration

The scraper connects to MySQL with these default settings:
- Host: localhost
- User: root
- Password: rangga
- Database: novel_db

Modify the database configuration in the script if needed.
