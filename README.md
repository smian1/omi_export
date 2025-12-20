# Getting Started with OMI Conversation Export Script

## What This Script Does

This script retrieves conversation data and memories from the OMI API and exports them to organized JSON files. It supports:

- Retrieving conversations within a specified date range
- Retrieving memories (with optional category filtering)
- Filtering conversations by timezone (supports all major timezones)
- Organizing exports by month into separate folders
- Extracting transcripts separately from conversation metadata
- Parallel API requests for faster data retrieval
- Colorful output for better visibility

## What It's For

Use this script to:
- Export your conversation history for backup or analysis
- Export your memories for backup or analysis
- Extract transcripts for processing or analysis
- Organize conversations by date/month for easier management
- Retrieve conversations from specific time periods
- Filter memories by category (personal, work, interesting, system, etc.)

## Overview

The script connects to the OMI Developer API to fetch conversation data and memories. For conversations, it retrieves transcripts, metadata, and structured information (titles, summaries, action items, etc.). For memories, it retrieves all your saved memories with optional category filtering. It handles pagination automatically, filters conversations by your specified date range, and organizes the output into easy-to-manage files.

### Key Features

- **Conversations:**
  - Date range filtering (supports "now" for current date)
  - Timezone-aware date handling
  - Parallel processing for faster retrieval
  - Automatic pagination handling
  - Rate limit protection
  - Client-side date filtering for accuracy
  - Month-based file organization
  - Optional transcript separation

- **Memories:**
  - Export all memories or filter by category
  - Automatic pagination to retrieve all memories
  - Saved to a separate `memories` folder
  - Single JSON file with all memories

## Requirements & Installation

Before running this script, install the required dependencies:

### Required

- **Python 3.9+** (for zoneinfo support)
- **requests library**
  ```bash
  pip install requests
  ```

### Other Requirements

- **OMI Developer API Key** (starts with "omi_dev...")
  
  To get your API key:
  1. Open the OMI app
  2. Go to **Settings** → **Developer Settings**
  3. Navigate to the **Developer API** section
  4. Create a new API key
  5. Copy the key (it should start with "omi_dev...")
  6. Paste it in the script's configuration section

## Testing the API with curl

Before running the full script, you can test the API directly using curl to verify your API key works:

```bash
curl -X GET "https://api.omi.me/v1/dev/user/conversations?start_date=2025-01-01T00:00:00Z&end_date=2025-01-31T23:59:59Z&limit=10&include_transcript=true" \
  -H "Authorization: Bearer YOUR_API_KEY_HERE" \
  -H "Content-Type: application/json"
```

**Replace `YOUR_API_KEY_HERE`** with your actual API key (starts with "omi_dev...").

**Parameters:**
- `start_date` - Start date in ISO 8601 format (UTC): `YYYY-MM-DDTHH:MM:SSZ`
- `end_date` - End date in ISO 8601 format (UTC): `YYYY-MM-DDTHH:MM:SSZ`
- `limit` - Number of conversations to retrieve (default: 50, max: 100)
- `include_transcript` - Set to `true` to include full transcripts, `false` for metadata only
- `offset` - Pagination offset (use 0 for first page, 50 for second, etc.)
- `order` - Sort order: `asc` for oldest first, `desc` for newest first

**Example for a specific date (January 15, 2025):**
```bash
curl -X GET "https://api.omi.me/v1/dev/user/conversations?start_date=2025-01-15T00:00:00Z&end_date=2025-01-15T23:59:59Z&limit=50&include_transcript=true&order=asc" \
  -H "Authorization: Bearer omi_dev_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" | jq .
```

**Note:** The `| jq .` at the end formats the JSON output nicely (requires `jq` to be installed). Remove it if you don't have `jq` installed.

## Quick Start

### 🎯 Easiest Method: Interactive Mode (No File Editing Required!)

**Perfect for first-time users!** Just run the script and it will prompt you for everything:

1. **Install dependencies:**
   ```bash
   pip install requests
   ```

2. **Run in interactive mode:**
   ```bash
   python3 omi_data.py --interactive
   ```

3. **Follow the prompts:**
   - Enter your API key (starts with "omi_dev...")
   - Choose what to export: conversations, memories, or both
   - **For conversations:** Enter start date, end date, and timezone settings
   - **For memories:** Optionally filter by categories (or leave empty for all)
   - Your system timezone will be detected automatically! ✨

That's it! No file editing needed. The script handles everything for you.

---

### Alternative Methods (For Advanced Users)

If you prefer not to use interactive mode, you can configure the script manually:

1. **Install dependencies:**
   ```bash
   pip install requests
   ```

2. **Provide your API key** using one of these methods:
   
   **Option A: Command-line argument (recommended for security)**
   ```bash
   python3 omi_data.py --api-key omi_dev_YOUR_KEY_HERE --start-date 2025-01-01 --end-date 2025-01-31
   ```
   
   **Option B: Environment variable**
   ```bash
   export OMI_API_KEY=omi_dev_YOUR_KEY_HERE
   python3 omi_data.py --start-date 2025-01-01 --end-date 2025-01-31
   ```
   
   **Option C: Script configuration**
   - Edit `omi_data.py` and set `API_KEY`, `START_DATE`, `END_DATE`, and `TIMEZONE` in the configuration section
   - Then run: `python3 omi_data.py`

3. **Run the script:**
   ```bash
   python3 omi_data.py
   ```

The script will create an 'export' folder (or your specified folder) with organized JSON files containing your conversation data.

**Priority Order:**
- Command-line arguments > Environment variables > Script configuration
- Interactive mode prompts override all other settings

## Command-Line Options

The script supports several command-line options for easy configuration:

```bash
python3 omi_data.py [OPTIONS]
```

**Available Options:**

- `--interactive` - Interactive mode: prompts for API key, dates, and auto-detects timezone (easiest method!)
- `--api-key KEY` - Provide API key via command line (e.g., `--api-key omi_dev_YOUR_KEY_HERE`)
- `--start-date DATE` - Start date in YYYY-MM-DD format (e.g., `--start-date 2025-01-01`)
- `--end-date DATE` - End date in YYYY-MM-DD format or "now" (e.g., `--end-date 2025-01-31`)

**Examples:**

```bash
# Interactive mode (easiest - no file editing!)
python3 omi_data.py --interactive

# All options via command line
python3 omi_data.py --api-key omi_dev_KEY --start-date 2025-01-01 --end-date now

# Mix of command line and config file
python3 omi_data.py --api-key omi_dev_KEY  # Uses dates from config file
```

## Configuration Guide

### Most Important Settings

These are located at the top of the configuration section in `omi_data.py` (only needed if not using interactive mode or command-line options):

1. **API_KEY** - Your OMI Developer API Key (can also be provided via `--api-key` or `OMI_API_KEY` environment variable)
2. **START_DATE** - Start date in YYYY-MM-DD format (e.g., "2025-01-01")
3. **END_DATE** - End date in YYYY-MM-DD format, or use "now" for current date
4. **TIMEZONE** - Your timezone (see examples in the script, or use interactive mode for auto-detection)

**Priority Order:**
- Command-line arguments (`--api-key`, `--start-date`, `--end-date`) have highest priority
- Environment variable (`OMI_API_KEY`) is checked next
- Script configuration is used as fallback
- Interactive mode (`--interactive`) prompts for all values and auto-detects timezone

### Output Settings

- **EXPORT_FOLDER** - Folder name to save conversation exports
- **ORGANIZE_BY_MONTH** - `True` to organize by month folders, `False` for single folder
- **SEPARATE_TRANSCRIPTS** - `True` to extract transcripts separately, `False` to include with conversations

### Advanced Settings

These usually don't need to be changed:
- **INCLUDE_TRANSCRIPT** - Whether to get full conversation text
- **PAGE_LIMIT** - Conversations per API request
- **MAX_WORKERS** - Number of parallel threads
- **ORDER_BY** - "asc" for oldest first, "desc" for newest first

## API Documentation

For detailed API information, authentication, and endpoint documentation, see:
**https://docs.omi.me/doc/get_started/introduction**

## Common Timezones

The script supports all standard timezone identifiers. Here are some common ones:

- `America/Los_Angeles` - Pacific Time (PT) - US West Coast
- `America/New_York` - Eastern Time (ET) - US East Coast
- `America/Chicago` - Central Time (CT) - US Central
- `America/Denver` - Mountain Time (MT) - US Mountain
- `Europe/London` - GMT/BST - United Kingdom
- `Europe/Paris` - CET/CEST - Central Europe
- `Asia/Tokyo` - JST - Japan
- `Asia/Kolkata` - IST - India
- `Asia/Mumbai` - IST - India (Mumbai)
- `Asia/Delhi` - IST - India (Delhi)
- `UTC` - Coordinated Universal Time

See the script for a complete list of timezone examples.

## Output Structure

**Conversations** are organized by date:

When `ORGANIZE_BY_MONTH = True`:
```
export/
├── 2025-01/
│   ├── conversation_export_2025-01-07.json
│   ├── conversation_export_2025-01-08.json
│   └── ...
├── 2025-02/
│   └── ...
└── memories/
    └── memories_export.json
```

When `ORGANIZE_BY_MONTH = False`:
```
export/
├── conversation_export_2025-01-07.json
├── conversation_export_2025-01-08.json
└── ...
└── memories/
    └── memories_export.json
```

**Memories** are saved in a separate folder:
- All memories are saved to `export/memories/memories_export.json`
- If category filtering is used, the filename includes categories: `memories_export_personal_work.json`
- All memories are in a single file (no date-based separation)

## Troubleshooting

- **Rate Limit Errors**: Reduce `MAX_WORKERS` or increase `REQUEST_DELAY`
- **Import Errors**: Make sure you've installed `requests` with `pip install requests`
- **Date Range Issues**: Check that your timezone is set correctly
- **API Key Errors**: Verify your API key starts with "omi_dev..." and is correct

## Need Help?

- Check the API documentation: https://docs.omi.me/doc/get_started/introduction
- Review the configuration comments in the script
- Ensure all dependencies are installed correctly

