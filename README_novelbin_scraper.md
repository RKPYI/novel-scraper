# NovelBin.com Specialized Scraper

A specialized web scraper for **novelbin.com** that extracts novel information and chapters for storage in a MySQL database.

## Features

- **Novel Metadata Extraction**: Extracts comprehensive novel information including:
  - Title and author
  - Description and cover image
  - Status (ongoing, completed, hiatus)
  - Genres and tags
  - Rating and publication year
  - Chapter count

- **Chapter Content Scraping**: Downloads chapter content with:
  - Chapter titles and numbers
  - Full chapter text content
  - Word count calculation
  - Navigation-based chapter discovery

- **Database Integration**: Stores data in MySQL database with:
  - Novel and chapter tables
  - Duplicate detection and updates
  - Proper data normalization

- **Robust Error Handling**: Includes:
  - Retry logic with exponential backoff
  - Comprehensive logging
  - Graceful failure handling
  - Skip existing chapters option

## Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Database Setup**: 
   Ensure you have a MySQL database with the proper schema (novels and chapters tables).

3. **Environment Configuration**:
   Create a `.env` file with your database credentials:
   ```env
   DB_HOST=localhost
   DB_USER=your_username
   DB_PASSWORD=your_password
   DB_NAME=novel_db
   DB_CHARSET=utf8mb4
   ```

## Usage

### Basic Usage

```bash
# Scrape novel information only
python novelbin_scraper.py --novel-slug mmorpg-rebirth-as-an-alchemist --novel-only

# Scrape novel and all chapters starting from chapter 1
python novelbin_scraper.py --novel-slug mmorpg-rebirth-as-an-alchemist --start-chapter 1

# Scrape specific chapter range
python novelbin_scraper.py --novel-slug mmorpg-rebirth-as-an-alchemist --start-chapter 1 --end-chapter 50

# Skip existing chapters (default behavior)
python novelbin_scraper.py --novel-slug mmorpg-rebirth-as-an-alchemist --skip-existing
```

### Command Line Arguments

- `--novel-slug`: **Required**. The novel slug from the URL (e.g., `mmorpg-rebirth-as-an-alchemist`)
- `--start-chapter`: Starting chapter number (default: 1)
- `--end-chapter`: Ending chapter number (optional, scrapes until no more chapters)
- `--novel-only`: Only scrape novel information, skip chapters
- `--skip-existing`: Skip chapters that already exist in database (default: True)

## Novel URL Structure

NovelBin uses the following URL patterns:
- **Novel page**: `https://novelbin.com/b/{novel-slug}`
- **Chapter page**: `https://novelbin.com/b/{novel-slug}/chapter-{number}`

## Data Extraction Details

### Novel Information
The scraper extracts the following novel metadata:
- **Title**: Main novel title (cleaned from page title)
- **Author**: Author name from author links
- **Description**: Novel description/summary
- **Cover Image**: Novel cover image URL
- **Status**: Publication status (ongoing, completed, hiatus)
- **Genres**: Associated genres and tags
- **Rating**: User rating (out of 10)
- **Year**: Publication year
- **Total Chapters**: Chapter count

### Chapter Content
For each chapter, the scraper extracts:
- **Chapter Number**: Sequential chapter number
- **Title**: Chapter title (defaults to "Chapter X" if not found)
- **Content**: Full chapter text content
- **Word Count**: Calculated word count for the chapter

## Site-Specific Features

### NovelBin.com Characteristics
- Uses clean URLs with novel slugs
- Chapter navigation via "Next Chapter" links
- Rich metadata including ratings and publication years
- Multiple genre categorization
- Author profile links
- Clean chapter content structure

### Content Processing
The scraper includes specific processing for NovelBin:
- Removes advertisement text and footers
- Cleans author notes (A/N sections)
- Handles various chapter title formats
- Processes navigation elements properly
- Manages content between navigation buttons

## Error Handling

The scraper includes robust error handling:
- **Network Issues**: Retry logic with exponential backoff
- **Missing Content**: Graceful skipping of empty chapters
- **Database Errors**: Proper connection management and error logging
- **Rate Limiting**: Built-in delays between requests
- **Consecutive Failures**: Stops after multiple consecutive failures

## Logging

All operations are logged to:
- **Console**: Real-time progress updates
- **Log File**: `novelbin_scraper.log` with detailed information

Log levels include:
- INFO: Normal operation progress
- WARNING: Minor issues and retries
- ERROR: Serious problems and failures

## Example Novels

Here are some example novels you can scrape:
- `mmorpg-rebirth-as-an-alchemist`
- `martial-peak`
- `against-the-gods`
- `tales-of-demons-and-gods`

## Database Schema

The scraper expects the following database tables:

### novels table
```sql
CREATE TABLE novels (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    author VARCHAR(255),
    description TEXT,
    cover_image TEXT,
    total_chapters INT DEFAULT 0,
    status ENUM('ongoing', 'completed', 'hiatus') DEFAULT 'ongoing',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### chapters table
```sql
CREATE TABLE chapters (
    id INT PRIMARY KEY AUTO_INCREMENT,
    novel_id INT NOT NULL,
    chapter_number INT NOT NULL,
    title VARCHAR(255),
    content LONGTEXT,
    word_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id),
    UNIQUE KEY unique_chapter (novel_id, chapter_number)
);
```

## Performance Notes

- **Rate Limiting**: 2-second delay between chapter requests
- **Memory Usage**: Processes one chapter at a time to minimize memory usage
- **Database Efficiency**: Uses prepared statements and proper indexing
- **Network Efficiency**: Reuses HTTP connections via session

## Troubleshooting

### Common Issues

1. **Database Connection Failed**:
   - Check your `.env` file configuration
   - Verify database server is running
   - Ensure database and tables exist

2. **No Content Found**:
   - Verify the novel slug is correct
   - Check if the novel exists on the site
   - Some novels may have different URL patterns

3. **Chapter Scraping Stops Early**:
   - May have reached the end of available chapters
   - Check logs for specific error messages
   - Some chapters may be missing or have different URLs

4. **Slow Performance**:
   - Built-in rate limiting prevents being blocked
   - Network conditions affect speed
   - Database performance depends on your setup

### Debug Mode

For debugging, you can modify the logging level in the script:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## Contributing

When contributing to this scraper:
1. Test with multiple novels to ensure compatibility
2. Follow the existing code style and patterns
3. Update documentation for any new features
4. Add appropriate error handling and logging

## Legal Notice

This scraper is for educational purposes. Please respect the website's robots.txt and terms of service. Consider implementing appropriate delays and limiting your scraping to avoid overloading the server.
