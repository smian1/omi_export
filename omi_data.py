"""
================================================================================
OMI CONVERSATION EXPORT SCRIPT
================================================================================

This script retrieves conversation data from the OMI API and exports it to 
organized JSON files. It supports date range filtering, timezone handling,
month-based organization, transcript extraction, and parallel processing.

📖 GETTING STARTED:
   See GETTING_STARTED.md for detailed installation instructions, configuration
   guide, and usage examples.

📚 API DOCUMENTATION:
   https://docs.omi.me/doc/get_started/introduction

⚙️ QUICK CONFIGURATION:
   1. Set your API_KEY below (get it from OMI app → Settings → Developer Settings)
   2. Set START_DATE and END_DATE
   3. Set your TIMEZONE
   4. Run: python3 omi_data.py

================================================================================
"""

import requests
import time
import json
import os
import sys
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Try to detect system timezone automatically
def get_system_timezone():
    """Detect the system's timezone automatically."""
    try:
        # Try macOS/Linux system commands first
        if sys.platform == "darwin":
            # macOS - use systemsetup or readlink
            try:
                import subprocess
                result = subprocess.run(['systemsetup', '-gettimezone'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    tz_line = result.stdout.strip()
                    # Extract timezone name (format: "Time Zone: America/Los_Angeles")
                    if ":" in tz_line:
                        tz_name = tz_line.split(":", 1)[1].strip()
                        if tz_name:
                            return tz_name
            except:
                pass
            
            # Try reading from /etc/localtime symlink
            try:
                import subprocess
                result = subprocess.run(['readlink', '/etc/localtime'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    tz_path = result.stdout.strip()
                    # Extract timezone from path like /usr/share/zoneinfo/America/Los_Angeles
                    if 'zoneinfo' in tz_path:
                        tz_name = tz_path.split('zoneinfo/')[-1]
                        return tz_name
            except:
                pass
        
        elif sys.platform.startswith("linux"):
            # Linux - try timedatectl
            try:
                import subprocess
                result = subprocess.run(['timedatectl', 'show', '-p', 'Timezone', '--value'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    tz_name = result.stdout.strip()
                    if tz_name:
                        return tz_name
            except:
                pass
            
            # Try /etc/timezone
            try:
                with open('/etc/timezone', 'r') as f:
                    tz_name = f.read().strip()
                    if tz_name:
                        return tz_name
            except:
                pass
        
        # Fallback: try to map UTC offset to common timezone
        try:
            now = datetime.now()
            local_now = datetime.now().astimezone()
            offset = local_now.strftime('%z')
            if offset:
                offset_hours = int(offset[:3])
                # Map common offsets to timezones (simplified)
                offset_map = {
                    -8: "America/Los_Angeles",   # PST
                    -7: "America/Denver",         # MST
                    -6: "America/Chicago",        # CST
                    -5: "America/New_York",       # EST
                    0: "UTC",
                    5: "Asia/Kolkata",           # IST
                    9: "Asia/Tokyo",             # JST
                }
                if offset_hours in offset_map:
                    return offset_map[offset_hours]
        except:
            pass
        
        # Final fallback
        return "America/Los_Angeles"
    except Exception:
        # Fallback to a common default
        return "America/Los_Angeles"

def prompt_for_input(prompt_text, default_value=None, validation_func=None):
    """Prompt user for input with optional default and validation."""
    if default_value is not None:
        if default_value == "":
            full_prompt = f"{prompt_text} [empty for all]: "
        else:
            full_prompt = f"{prompt_text} [{default_value}]: "
    else:
        full_prompt = f"{prompt_text}: "
    
    while True:
        user_input = input(full_prompt).strip()
        
        # Use default if empty and default provided
        if not user_input and default_value is not None:
            user_input = default_value
            if user_input == "":
                print(f"  Using: (empty - all)")
            else:
                print(f"  Using: {user_input}")
            break
        
        # Require input if no default
        if not user_input and default_value is None:
            print(f"  {Colors.YELLOW}This field is required. Please enter a value.{Colors.END}")
            continue
        
        # Validate if validation function provided
        if validation_func:
            is_valid, error_msg = validation_func(user_input)
            if not is_valid:
                print(f"  {Colors.YELLOW}{error_msg}{Colors.END}")
                continue
        
        break
    
    return user_input

# ============================================================================
# ═══════════════════════════════════════════════════════════════════════════
#   MOST IMPORTANT SETTINGS - Configure these first!
# ═══════════════════════════════════════════════════════════════════════════
# ============================================================================

# ────────────────────────────────────────────────────────────────────────────
# API KEY (REQUIRED)
# ────────────────────────────────────────────────────────────────────────────
# To get your API key:
#   1. Open the OMI app
#   2. Go to Settings → Developer Settings
#   3. Navigate to the Developer API section
#   4. Create a new API key
#   5. Copy the key (it should start with "omi_dev...")
#   6. Paste it below
# ────────────────────────────────────────────────────────────────────────────
API_KEY = "omi_dev_YOUR_API_KEY_HERE"  # Replace with your OMI Developer API Key (starts with "omi_dev...")

# ────────────────────────────────────────────────────────────────────────────
# DATE RANGE (REQUIRED)
# ────────────────────────────────────────────────────────────────────────────
START_DATE = "2025-01-01"          # Start date: YYYY-MM-DD format (e.g., "2025-01-01")
END_DATE = "2025-01-31"            # End date: YYYY-MM-DD format, or use "now" for current date

# ────────────────────────────────────────────────────────────────────────────
# TIMEZONE (REQUIRED)
# ────────────────────────────────────────────────────────────────────────────
# Your timezone for date queries. Common examples:
#   "America/Los_Angeles"     - Pacific Time (PT) - US West Coast
#   "America/New_York"         - Eastern Time (ET) - US East Coast
#   "America/Chicago"          - Central Time (CT) - US Central
#   "America/Denver"           - Mountain Time (MT) - US Mountain
#   "America/Toronto"          - Eastern Time - Canada
#   "America/Vancouver"        - Pacific Time - Canada
#   "Europe/London"            - GMT/BST - United Kingdom
#   "Europe/Paris"             - CET/CEST - Central Europe
#   "Europe/Berlin"            - CET/CEST - Germany
#   "Asia/Tokyo"               - JST - Japan
#   "Asia/Shanghai"            - CST - China
#   "Asia/Dubai"               - GST - UAE
#   "Asia/Kolkata"             - IST - India (Kolkata/Calcutta)
#   "Asia/Mumbai"              - IST - India (Mumbai/Bombay)
#   "Asia/Delhi"               - IST - India (Delhi/New Delhi)
#   "Asia/Chennai"             - IST - India (Chennai/Madras)
#   "Asia/Bangalore"           - IST - India (Bangalore)
#   "Asia/Hyderabad"           - IST - India (Hyderabad)
#   "Australia/Sydney"         - AEDT/AEST - Australia East
#   "Australia/Melbourne"      - AEDT/AEST - Australia Southeast
#   "UTC"                      - Coordinated Universal Time
TIMEZONE = "America/Los_Angeles"  # Your timezone

# ============================================================================
# ═══════════════════════════════════════════════════════════════════════════
#   OUTPUT SETTINGS - How files are saved
# ═══════════════════════════════════════════════════════════════════════════
# ============================================================================

EXPORT_FOLDER = "export"          # Folder name to save conversation exports
ORGANIZE_BY_MONTH = True          # True = organize by month folders (export/2025-01/), False = single folder
SEPARATE_TRANSCRIPTS = False      # True = separate transcript files, False = include transcripts with conversations

# ============================================================================
# ═══════════════════════════════════════════════════════════════════════════
#   ADVANCED SETTINGS - Usually don't need to change these
# ═══════════════════════════════════════════════════════════════════════════
# ============================================================================

# API Request Settings
INCLUDE_TRANSCRIPT = True         # True = get full conversation text, False = metadata only
PAGE_LIMIT = 50                   # Conversations per API request (max usually 100)
REQUEST_DELAY = 0.5               # Seconds between requests (helps avoid rate limits)
RATE_LIMIT_RETRY_DELAY = 10       # Seconds to wait when hitting rate limit (HTTP 429)
MAX_WORKERS = 5                   # Parallel threads for API requests (5-10 is safe)
ORDER_BY = "asc"                  # "asc" = oldest first, "desc" = newest first

# API Endpoints (usually don't need to change)
BASE_URL = "https://api.omi.me/v1/dev/user/conversations"
MEMORIES_URL = "https://api.omi.me/v1/dev/user/memories"

# ============================================================================
# END OF CONFIGURATION - Do not modify below unless you know what you're doing
# ============================================================================

# Authentication headers (automatically generated from API_KEY)
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Color and emoji helpers for exciting output! 🎨
class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    """Print a colorful header"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text.center(70)}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.END}\n")

def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_info(text):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.END}")

def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_progress(text):
    """Print progress message"""
    print(f"{Colors.BLUE}🔄 {text}{Colors.END}")

def parse_timestamp_from_conversation(conversation):
    """
    Extract and parse timestamp from a conversation object.
    Returns UTC datetime or None.
    """
    for field in ['created_at', 'timestamp', 'date', 'time', 'started_at', 'updated_at', 'created', 'start_time']:
        if field in conversation:
            try:
                timestamp_value = conversation[field]
                if isinstance(timestamp_value, str):
                    timestamp_str = timestamp_value.replace('Z', '+00:00')
                    try:
                        dt = datetime.fromisoformat(timestamp_str)
                    except ValueError:
                        dt = datetime.fromisoformat(timestamp_value.replace('Z', ''))
                        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                    
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                    else:
                        dt = dt.astimezone(ZoneInfo("UTC"))
                    return dt
                elif isinstance(timestamp_value, (int, float)):
                    return datetime.fromtimestamp(timestamp_value, tz=ZoneInfo("UTC"))
            except (ValueError, TypeError, OSError):
                continue
    return None

def filter_conversations_by_date(conversations, start_date_utc=None, end_date_utc=None):
    """
    Filter conversations to only include those within the specified date range.
    Returns filtered list and boolean indicating if we should continue fetching.
    """
    if not start_date_utc and not end_date_utc:
        return conversations, True
    
    filtered = []
    all_within_range = True
    
    for conv in conversations:
        conv_date_utc = parse_timestamp_from_conversation(conv)
        
        if conv_date_utc is None:
            # If we can't parse the date, include it (better to include than exclude)
            filtered.append(conv)
            continue
        
        # Check if conversation is within date range
        within_range = True
        if start_date_utc and conv_date_utc < start_date_utc:
            within_range = False
            all_within_range = False
        if end_date_utc and conv_date_utc > end_date_utc:
            within_range = False
            all_within_range = False
        
        if within_range:
            filtered.append(conv)
    
    # If ORDER_BY is "asc" (oldest first) and we found dates before start_date, we're done
    # If ORDER_BY is "desc" (newest first) and we found dates after end_date, we're done
    should_continue = all_within_range
    
    return filtered, should_continue

def fetch_page(offset, start_date=None, end_date=None):
    """
    Fetch a single page of conversations from the API.
    Returns (offset, data, error) tuple.
    """
    params = {
        "limit": PAGE_LIMIT,
        "offset": offset,
        "include_transcript": "true" if INCLUDE_TRANSCRIPT else "false"
    }
    
    # Add ordering parameter - Omi API uses created_at_order or order
    if ORDER_BY:
        # Omi API specifically looks for created_at_order=asc or order=asc depending on API version
        # Using order as primary parameter (created_at_order may not be working in some API versions)
        # If sorting still doesn't work, try params["created_at_order"] = ORDER_BY instead
        params["order"] = ORDER_BY
    
    # Omi expects ISO 8601 strings (YYYY-MM-DDTHH:MM:SSZ) for these filters
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    
    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=30)
        
        if response.status_code == 429:
            return (offset, None, "rate_limit")
        
        response.raise_for_status()
        data = response.json()
        return (offset, data, None)
        
    except requests.exceptions.RequestException as e:
        return (offset, None, str(e))

def get_conversations(start_date=None, end_date=None, callback=None):
    """
    Function to crawl the Omi API and retrieve conversations using parallel requests.
    Supports pagination and parallel fetching for faster retrieval.
    Filters conversations client-side to ensure they're within the date range.
    
    Args:
        start_date: Start date in UTC ISO format
        end_date: End date in UTC ISO format
        callback: Optional function to call with each batch of conversations (conversations, total_count)
    """
    # Parse date strings to datetime objects for filtering
    start_date_utc = None
    end_date_utc = None
    if start_date:
        try:
            start_date_utc = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_date_utc.tzinfo is None:
                start_date_utc = start_date_utc.replace(tzinfo=ZoneInfo("UTC"))
        except:
            pass
    if end_date:
        try:
            end_date_utc = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_date_utc.tzinfo is None:
                end_date_utc = end_date_utc.replace(tzinfo=ZoneInfo("UTC"))
        except:
            pass
    
    print_header("🚀 STARTING API RETRIEVAL (PARALLEL MODE)")
    print_info(f"Query date range: {Colors.BOLD}{start_date} to {end_date}{Colors.END}")
    if start_date_utc:
        print_info(f"Filtering: Only conversations from {Colors.BOLD}{start_date_utc.strftime('%Y-%m-%d')}{Colors.END} onwards")
    if end_date_utc:
        print_info(f"Filtering: Only conversations up to {Colors.BOLD}{end_date_utc.strftime('%Y-%m-%d')}{Colors.END}")
    print_info(f"Page limit: {Colors.BOLD}{PAGE_LIMIT}{Colors.END} conversations per request")
    print_info(f"Parallel workers: {Colors.BOLD}{MAX_WORKERS}{Colors.END} threads")
    order_emoji = "⬆️" if ORDER_BY == 'asc' else "⬇️"
    print_info(f"Order: {order_emoji} {Colors.BOLD}{'Oldest first' if ORDER_BY == 'asc' else 'Newest first'}{Colors.END}\n")
    
    all_data = []  # List to store every conversation we find
    offset = 0     # The starting point for the current page
    batch_number = 1
    lock = Lock()  # Thread lock for safe data access
    
    # First, fetch the first page to determine if there's data and get initial info
    print_progress(f"Fetching first page to determine data availability...")
    first_result = fetch_page(0, start_date, end_date)
    
    if first_result[2] == "rate_limit":
        print_warning(f"Rate limit hit on initial request. Waiting {RATE_LIMIT_RETRY_DELAY} seconds...")
        time.sleep(RATE_LIMIT_RETRY_DELAY)
        first_result = fetch_page(0, start_date, end_date)
    
    if first_result[2]:
        print_error(f"Error on initial request: {first_result[2]}")
        return []
    
    if not first_result[1]:
        print_warning("No conversations found in date range.")
        return []
    
    # Filter first page by date range
    first_page_data_raw = first_result[1]
    first_page_data, should_continue = filter_conversations_by_date(
        first_page_data_raw, start_date_utc, end_date_utc
    )
    
    if not first_page_data:
        print_warning(f"First page had {len(first_page_data_raw)} conversations, but none were within the date range.")
        print_info("This suggests the API may not be filtering by date correctly. Continuing to fetch more pages...")
    else:
        filtered_info = f" ({Colors.YELLOW}{len(first_page_data)}/{len(first_page_data_raw)}{Colors.END} after filtering)" if len(first_page_data) != len(first_page_data_raw) else ""
        print_success(f"Retrieved {Colors.BOLD}{len(first_page_data)}{Colors.END} conversations{filtered_info} | Total: {Colors.BOLD}{len(first_page_data)}{Colors.END}")
    
    all_data.extend(first_page_data)
    
    # Show date info for first batch
    if first_page_data:
        first_date = None
        last_date = None
        for conv in [first_page_data[0], first_page_data[-1]]:
            conv_date = parse_timestamp_from_conversation(conv)
            if conv_date:
                date_str = conv_date.strftime('%Y-%m-%d')
                first_date = first_date or date_str
                last_date = date_str
        
        if first_date:
            date_info = f"{Colors.CYAN}📅 Dates: {first_date}" + (f" to {last_date}" if first_date != last_date else "") + f"{Colors.END}"
        else:
            date_info = f"{Colors.YELLOW}📅 Dates: (unable to parse){Colors.END}"
        print(f"  {date_info}")
    
    # Call callback for first batch
    if callback and first_page_data:
        callback(first_page_data, len(all_data))
    
    # If first page has fewer items than limit, we're done
    if len(first_page_data) < PAGE_LIMIT:
        print_success(f"\n🎉 All data retrieved in first page! Total: {Colors.BOLD}{len(all_data)}{Colors.END}")
        return all_data
    
    # Now use parallel requests for remaining pages
    offset = PAGE_LIMIT
    batch_number = 2
    has_more_data = True  # Flag to track if we should continue fetching
    
    print_info(f"\n🚀 Starting parallel batch retrieval with {MAX_WORKERS} workers...\n")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit initial batch of parallel requests
        futures = {}
        active_requests = 0
        
        while has_more_data:
            # Submit new requests up to MAX_WORKERS
            while active_requests < MAX_WORKERS and has_more_data:
                future = executor.submit(fetch_page, offset, start_date, end_date)
                futures[future] = offset
                active_requests += 1
                offset += PAGE_LIMIT
            
            # Process completed requests
            for future in as_completed(futures):
                active_requests -= 1
                page_offset = futures.pop(future)
                
                try:
                    result_offset, data, error = future.result()
                    
                    if error == "rate_limit":
                        print_warning(f"Rate limit hit at offset {page_offset}. Waiting {RATE_LIMIT_RETRY_DELAY} seconds...")
                        time.sleep(RATE_LIMIT_RETRY_DELAY)
                        # Retry this page
                        future = executor.submit(fetch_page, page_offset, start_date, end_date)
                        futures[future] = page_offset
                        active_requests += 1
                        continue
                    elif error:
                        print_error(f"Error at offset {page_offset}: {error}")
                        continue
                    
                    if not data:
                        # Empty response means we've reached the end
                        print_success(f"Reached end of data at offset {page_offset}")
                        has_more_data = False
                        break
                    
                    # Filter conversations by date range
                    original_count = len(data)
                    filtered_data, batch_should_continue = filter_conversations_by_date(
                        data, start_date_utc, end_date_utc
                    )
                    
                    # Check if we should stop fetching based on date range
                    # If ORDER_BY is "asc" and we're getting dates before start_date, stop
                    # If ORDER_BY is "desc" and we're getting dates after end_date, stop
                    if not batch_should_continue:
                        msg = f"\n⚠️  Batch at offset {page_offset} contains conversations outside date range."
                        print_warning(msg)
                        if ORDER_BY == "asc":
                            print_info(f"    (Getting dates before {start_date_utc.strftime('%Y-%m-%d') if start_date_utc else 'start date'}, stopping fetch)")
                        else:
                            print_info(f"    (Getting dates after {end_date_utc.strftime('%Y-%m-%d') if end_date_utc else 'end date'}, stopping fetch)")
                        has_more_data = False
                        # Still process the filtered data from this batch if any
                        if not filtered_data:
                            break
                    else:
                        # If all conversations were filtered out, we might want to continue
                        if not filtered_data and original_count == PAGE_LIMIT:
                            # Full page but all filtered out - might be a gap in dates, continue
                            msg = f"[Batch {batch_number}] ⚠️  Offset {page_offset}: All {original_count} conversations filtered out"
                            print_warning(msg)
                            batch_number += 1
                            continue
                    
                    # Show progress with colors and emojis
                    if filtered_data:
                        first_date = None
                        last_date = None
                        for conv in [filtered_data[0], filtered_data[-1]]:
                            conv_date = parse_timestamp_from_conversation(conv)
                            if conv_date:
                                date_str = conv_date.strftime('%Y-%m-%d')
                                first_date = first_date or date_str
                                last_date = date_str
                        
                        filtered_info = f" {Colors.YELLOW}({len(filtered_data)}/{original_count} filtered){Colors.END}" if len(filtered_data) != original_count else ""
                        date_info = f"{Colors.CYAN}📅 {first_date}" + (f" to {last_date}" if first_date != last_date else "") + f"{Colors.END}" if first_date else f"{Colors.YELLOW}📅 (unable to parse){Colors.END}"
                        
                        message = f"{Colors.GREEN}✓{Colors.END} Batch {Colors.BOLD}{batch_number}{Colors.END} | Offset {page_offset} | {Colors.BOLD}{len(filtered_data)}{Colors.END} conversations{filtered_info} | {date_info}"
                        print(message)
                    else:
                        message = f"{Colors.YELLOW}⚠️{Colors.END} Batch {batch_number} | Offset {page_offset} | 0 conversations (all filtered out)"
                        print(message)
                    
                    batch_number += 1
                    
                    # Only process if we have filtered data
                    if filtered_data:
                        # Process this batch
                        with lock:
                            all_data.extend(filtered_data)
                            if callback:
                                callback(filtered_data, len(all_data))
                    
                    # If we got fewer items than limit, we're done
                    if original_count < PAGE_LIMIT:
                        has_more_data = False
                        break
                    
                    # Small delay to be polite
                    time.sleep(REQUEST_DELAY)
                    
                except Exception as e:
                    print(f"\n❌ Exception processing offset {page_offset}: {e}")
            
            # If no more futures and no more data, we're done
            if not futures and not has_more_data:
                break
    
    # Sort all data by offset to ensure correct order (in case parallel requests completed out of order)
    # Actually, we should sort by timestamp if ORDER_BY is set, but for now just return in order received
    print_success(f"\n🎉 Retrieval complete! Total conversations: {Colors.BOLD}{len(all_data)}{Colors.END}")
    return all_data

def get_memories(limit=100, offset=0, categories=None):
    """
    Retrieve memories from the OMI API.
    
    Args:
        limit: Maximum number of memories to return (default: 100)
        offset: Number of memories to skip (default: 0)
        categories: Comma-separated list of categories to filter by (optional)
    
    Returns:
        List of memory objects
    """
    all_memories = []
    current_offset = offset
    
    print_info(f"Fetching memories (limit: {Colors.BOLD}{limit}{Colors.END} per page)")
    if categories:
        print_info(f"Filtering by categories: {Colors.BOLD}{categories}{Colors.END}")
    
    while True:
        params = {
            "limit": limit,
            "offset": current_offset
        }
        
        if categories:
            params["categories"] = categories
        
        try:
            response = requests.get(MEMORIES_URL, headers=HEADERS, params=params, timeout=30)
            
            if response.status_code == 429:
                print_warning(f"Rate limit hit. Waiting {RATE_LIMIT_RETRY_DELAY} seconds...")
                time.sleep(RATE_LIMIT_RETRY_DELAY)
                continue
            
            response.raise_for_status()
            data = response.json()
            
            if not data or len(data) == 0:
                # No more memories
                print_info(f"Reached end of memories (no more data at offset {current_offset})")
                break
            
            all_memories.extend(data)
            print_info(f"Retrieved {Colors.BOLD}{len(data)}{Colors.END} memories from offset {current_offset} (requested limit: {limit}, total so far: {Colors.BOLD}{len(all_memories)}{Colors.END})")
            
            # Continue fetching - only stop when we get 0 results (handled above)
            # The API might return fewer items than requested even if there are more pages
            current_offset += len(data)  # Use actual count returned, not requested limit
            
            # Small delay to be polite
            time.sleep(REQUEST_DELAY)
            
        except requests.exceptions.RequestException as e:
            print_error(f"Error fetching memories: {e}")
            break
    
    print_success(f"\n🎉 Memories retrieval complete! Total memories: {Colors.BOLD}{len(all_memories)}{Colors.END}")
    return all_memories

# --- Execution Block ---
if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Export conversations from OMI API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (easiest - prompts for everything)
  python3 omi_data.py --interactive
  
  # Use API key from configuration file
  python3 omi_data.py
  
  # Pass API key via command line
  python3 omi_data.py --api-key omi_dev_YOUR_KEY_HERE
  
  # Pass API key via environment variable
  export OMI_API_KEY=omi_dev_YOUR_KEY_HERE
  python3 omi_data.py
        """
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="OMI Developer API Key (starts with 'omi_dev...'). Can also be set via OMI_API_KEY environment variable or in the script configuration."
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode: prompts for API key, dates, and auto-detects timezone. Perfect for first-time users!"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format (e.g., '2025-01-01')"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format, or use 'now' for current date"
    )
    args = parser.parse_args()
    
    # Interactive mode - prompt for all required values
    if args.interactive:
        print_header("🎯 INTERACTIVE MODE - Let's get you set up!")
        print_info("This mode will prompt you for the required information.")
        print_info("Your system timezone will be detected automatically.\n")
        
        # Prompt for API key
        def validate_api_key(key):
            if not key.startswith("omi_dev_"):
                return False, "API key should start with 'omi_dev_'. Please check your key."
            return True, None
        
        final_api_key = prompt_for_input(
            f"{Colors.CYAN}Enter your OMI API Key{Colors.END}",
            validation_func=validate_api_key
        )
        
        # Ask what to export
        print(f"\n{Colors.CYAN}📦 What would you like to export?{Colors.END}")
        export_conversations = prompt_for_input(
            f"{Colors.CYAN}Export conversations? (y/n){Colors.END}",
            default_value="y"
        ).lower() in ['y', 'yes']
        
        export_memories = prompt_for_input(
            f"{Colors.CYAN}Export memories? (y/n){Colors.END}",
            default_value="n"
        ).lower() in ['y', 'yes']
        
        if not export_conversations and not export_memories:
            print_error("You must select at least one option (conversations or memories).")
            sys.exit(1)
        
        # Conversation-specific prompts (only if exporting conversations)
        final_start_date = None
        final_end_date = None
        final_timezone = None
        
        if export_conversations:
            # Prompt for start date
            def validate_date(date_str):
                try:
                    if date_str.lower() == "now":
                        return True, None
                    datetime.strptime(date_str, "%Y-%m-%d")
                    return True, None
                except ValueError:
                    return False, "Invalid date format. Use YYYY-MM-DD (e.g., '2025-01-01')"
            
            final_start_date = prompt_for_input(
                f"{Colors.CYAN}Enter start date (YYYY-MM-DD){Colors.END}",
                default_value="2025-01-01",
                validation_func=validate_date
            )
            
            # Prompt for end date
            final_end_date = prompt_for_input(
                f"{Colors.CYAN}Enter end date (YYYY-MM-DD or 'now'){Colors.END}",
                default_value="now",
                validation_func=validate_date
            )
            
            # Auto-detect timezone and ask if user wants to change it
            detected_tz = get_system_timezone()
            print(f"\n{Colors.GREEN}✓{Colors.END} Detected your system timezone: {Colors.BOLD}{detected_tz}{Colors.END}")
            
            # Common timezones for selection
            common_timezones = [
            ("America/Los_Angeles", "Pacific Time (PT) - US West Coast"),
            ("America/Denver", "Mountain Time (MT) - US Mountain"),
            ("America/Chicago", "Central Time (CT) - US Central"),
            ("America/New_York", "Eastern Time (ET) - US East Coast"),
            ("America/Toronto", "Eastern Time - Canada"),
            ("America/Vancouver", "Pacific Time - Canada"),
            ("Europe/London", "GMT/BST - United Kingdom"),
            ("Europe/Paris", "CET/CEST - Central Europe"),
            ("Europe/Berlin", "CET/CEST - Germany"),
            ("Asia/Tokyo", "JST - Japan"),
            ("Asia/Shanghai", "CST - China"),
            ("Asia/Dubai", "GST - UAE"),
            ("Asia/Kolkata", "IST - India (Kolkata)"),
            ("Asia/Mumbai", "IST - India (Mumbai)"),
            ("Asia/Delhi", "IST - India (Delhi)"),
            ("Australia/Sydney", "AEDT/AEST - Australia East"),
            ("UTC", "Coordinated Universal Time"),
            ]
            
            change_tz = prompt_for_input(
                f"{Colors.CYAN}Use detected timezone '{detected_tz}'? (y/n){Colors.END}",
                default_value="y"
            ).lower()
            
            if change_tz in ['n', 'no']:
                print(f"\n{Colors.CYAN}Select a timezone:{Colors.END}")
                print(f"  {Colors.YELLOW}Common timezones:{Colors.END}")
                for i, (tz, desc) in enumerate(common_timezones, 1):
                    print(f"  {i:2d}. {tz:25s} - {desc}")
                print(f"  {Colors.CYAN}Or enter a custom timezone name (e.g., 'America/Chicago'){Colors.END}")
                
                def validate_timezone(tz_input):
                    # Check if it's a number (selection from list)
                    try:
                        idx = int(tz_input) - 1
                        if 0 <= idx < len(common_timezones):
                            return True, None
                    except ValueError:
                        pass
                    
                    # Check if it's a valid timezone name
                    try:
                        ZoneInfo(tz_input)
                        return True, None
                    except:
                        return False, f"Invalid timezone. Please select a number (1-{len(common_timezones)}) or enter a valid timezone name."
                
                tz_choice = prompt_for_input(
                    f"{Colors.CYAN}Enter timezone (number or name){Colors.END}",
                    validation_func=validate_timezone
                )
                
                # Parse timezone choice
                try:
                    idx = int(tz_choice) - 1
                    if 0 <= idx < len(common_timezones):
                        final_timezone = common_timezones[idx][0]
                        print(f"{Colors.GREEN}✓{Colors.END} Selected: {Colors.BOLD}{final_timezone}{Colors.END}")
                except ValueError:
                    final_timezone = tz_choice
                    print(f"{Colors.GREEN}✓{Colors.END} Using custom timezone: {Colors.BOLD}{final_timezone}{Colors.END}")
            else:
                final_timezone = detected_tz
                print(f"{Colors.GREEN}✓{Colors.END} Using detected timezone: {Colors.BOLD}{final_timezone}{Colors.END}\n")
            
            # Ask about folder organization (for conversations)
            print(f"\n{Colors.CYAN}📁 Folder Organization (for conversations):{Colors.END}")
            print(f"  {Colors.YELLOW}How would you like to organize conversation files?{Colors.END}")
            print(f"  • {Colors.BOLD}By month{Colors.END}: Creates folders like 'export/2025-01/', 'export/2025-02/'")
            print(f"  • {Colors.BOLD}Single folder{Colors.END}: All files go directly in 'export/'")
            
            organize_choice = prompt_for_input(
                f"{Colors.CYAN}Organize conversations by month? (y/n){Colors.END}",
                default_value="y"
            ).lower()
            
            final_organize_by_month = organize_choice in ['y', 'yes']
            if final_organize_by_month:
                print(f"{Colors.GREEN}✓{Colors.END} Conversation files will be organized by month folders\n")
            else:
                print(f"{Colors.GREEN}✓{Colors.END} All conversation files will be in a single folder\n")
            
            # Ask about transcript separation
            print(f"{Colors.CYAN}📄 Transcript Separation:{Colors.END}")
            print(f"  {Colors.YELLOW}Would you like transcripts in separate files?{Colors.END}")
            print(f"  • {Colors.BOLD}Separate files{Colors.END}: Creates two files per day:")
            print(f"    - conversation_export_YYYY-MM-DD.json (metadata only)")
            print(f"    - conversation_export_YYYY-MM-DD_transcripts.json (transcripts only)")
            print(f"  • {Colors.BOLD}Combined{Colors.END}: One file with everything together")
            print(f"    - conversation_export_YYYY-MM-DD.json (conversations + transcripts)")
            
            separate_choice = prompt_for_input(
                f"{Colors.CYAN}Separate transcripts into different files? (y/n){Colors.END}",
                default_value="n"
            ).lower()
            
            final_separate_transcripts = separate_choice in ['y', 'yes']
            if final_separate_transcripts:
                print(f"{Colors.GREEN}✓{Colors.END} Transcripts will be saved in separate files\n")
            else:
                print(f"{Colors.GREEN}✓{Colors.END} Transcripts will be included with conversation data\n")
        else:
            # Set defaults for non-interactive or when not exporting conversations
            final_organize_by_month = ORGANIZE_BY_MONTH
            final_separate_transcripts = SEPARATE_TRANSCRIPTS
        
        # Memory-specific prompts (only if exporting memories)
        final_memory_categories = None
        final_memory_limit = 100
        
        if export_memories:
            print(f"\n{Colors.CYAN}💭 Memory Export Settings:{Colors.END}")
            
            categories_choice = prompt_for_input(
                f"{Colors.CYAN}Filter by categories? (comma-separated, e.g., 'personal,work' or leave empty for all){Colors.END}",
                default_value=""
            )
            
            # Convert empty string to None
            if categories_choice and categories_choice.strip():
                final_memory_categories = categories_choice.strip()
                print(f"{Colors.GREEN}✓{Colors.END} Will filter memories by categories: {Colors.BOLD}{final_memory_categories}{Colors.END}\n")
            else:
                final_memory_categories = None
                print(f"{Colors.GREEN}✓{Colors.END} Will export all memories\n")
        
        # Summary
        print_header("📋 CONFIGURATION SUMMARY")
        print_info(f"API Key: {Colors.BOLD}{final_api_key[:20]}...{Colors.END}")
        if export_conversations:
            print_info(f"Export Conversations: {Colors.BOLD}Yes{Colors.END}")
            print_info(f"Date Range: {Colors.BOLD}{final_start_date} to {final_end_date}{Colors.END}")
            print_info(f"Timezone: {Colors.BOLD}{final_timezone}{Colors.END}")
            print_info(f"Folder Organization: {Colors.BOLD}{'By month' if final_organize_by_month else 'Single folder'}{Colors.END}")
            print_info(f"Transcript Separation: {Colors.BOLD}{'Separate files' if final_separate_transcripts else 'Combined'}{Colors.END}")
        else:
            print_info(f"Export Conversations: {Colors.BOLD}No{Colors.END}")
        
        if export_memories:
            print_info(f"Export Memories: {Colors.BOLD}Yes{Colors.END}")
            if final_memory_categories:
                print_info(f"Memory Categories: {Colors.BOLD}{final_memory_categories}{Colors.END}")
            else:
                print_info(f"Memory Categories: {Colors.BOLD}All{Colors.END}")
        else:
            print_info(f"Export Memories: {Colors.BOLD}No{Colors.END}")
        
        confirm = prompt_for_input(
            f"\n{Colors.CYAN}Proceed with export? (y/n){Colors.END}",
            default_value="y"
        ).lower()
        
        if confirm not in ['y', 'yes']:
            print_info("Export cancelled.")
            sys.exit(0)
        
        print()  # Empty line before starting
        
    else:
        # Non-interactive mode - use provided values or defaults
        # Determine which API key to use (command line > environment variable > config)
        final_api_key = None
        if args.api_key:
            final_api_key = args.api_key
            print_info("Using API key from command-line argument")
        elif os.getenv("OMI_API_KEY"):
            final_api_key = os.getenv("OMI_API_KEY")
            print_info("Using API key from OMI_API_KEY environment variable")
        elif API_KEY and API_KEY != "omi_dev_YOUR_API_KEY_HERE":
            final_api_key = API_KEY
            print_info("Using API key from script configuration")
        else:
            # No API key found - offer interactive mode
            print_error("No API key provided!")
            print_info("\n💡 Tip: Run with --interactive for easy setup:")
            print_info("   python3 omi_data.py --interactive\n")
            print_info("Or provide an API key using one of these methods:")
            print_info("  1. Command line: --api-key omi_dev_YOUR_KEY_HERE")
            print_info("  2. Environment variable: export OMI_API_KEY=omi_dev_YOUR_KEY_HERE")
            print_info("  3. Script configuration: Set API_KEY in the configuration section")
            sys.exit(1)
        
        # Non-interactive mode defaults
        export_conversations = True  # Default to exporting conversations
        export_memories = False  # Default to not exporting memories
        final_start_date = args.start_date if args.start_date else START_DATE
        final_end_date = args.end_date if args.end_date else END_DATE
        final_timezone = TIMEZONE
        final_organize_by_month = ORGANIZE_BY_MONTH
        final_separate_transcripts = SEPARATE_TRANSCRIPTS
        final_memory_categories = None
        final_memory_limit = 100
    
    # Validate API key format
    if not final_api_key.startswith("omi_dev_"):
        print_warning(f"API key doesn't start with 'omi_dev_'. Please verify your key is correct.")
    
    # Update the API_KEY variable for use in the script
    API_KEY = final_api_key
    
    # Update headers with the final API key
    HEADERS = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Create export folder if it doesn't exist
    os.makedirs(EXPORT_FOLDER, exist_ok=True)
    
    # Initialize result variables
    results = []
    memories = []
    
    # Export conversations if requested
    if export_conversations:
        # Convert configured timezone and date to UTC for the API (which expects UTC timestamps)
        user_tz = ZoneInfo(final_timezone)
        
        # Parse start date
        try:
            start_year, start_month, start_day = map(int, final_start_date.split("-"))
            start_local = datetime(start_year, start_month, start_day, 0, 0, 0, tzinfo=user_tz)
        except ValueError:
            raise ValueError(f"Invalid start date format: {final_start_date}. Use YYYY-MM-DD format (e.g., '2025-01-01')")
        
        # Parse end date (handle "now" as special case)
        if final_end_date.lower() == "now":
            # Use current date/time in the user's timezone
            end_local = datetime.now(user_tz)
        else:
            try:
                end_year, end_month, end_day = map(int, final_end_date.split("-"))
                # Set to end of day (23:59:59)
                end_local = datetime(end_year, end_month, end_day, 23, 59, 59, tzinfo=user_tz)
            except ValueError:
                raise ValueError(f"Invalid end date format: {final_end_date}. Use YYYY-MM-DD format (e.g., '2025-01-31') or 'now'")
        
        # Convert to UTC for the API
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_local.astimezone(ZoneInfo("UTC"))
        
        # Format as ISO 8601 strings with Z suffix (UTC)
        QUERY_START = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        QUERY_END = end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Display configuration summary
        if not args.interactive:
            print_header("⚙️  CONVERSATION EXPORT CONFIGURATION")
        print_info(f"Date range: {Colors.BOLD}{final_start_date} to {final_end_date}{Colors.END} ({final_timezone})")
        print_info(f"Local dates: {Colors.BOLD}{start_local.strftime('%Y-%m-%d')} to {end_local.strftime('%Y-%m-%d')}{Colors.END}")
        print_info(f"UTC time range: {Colors.BOLD}{QUERY_START} to {QUERY_END}{Colors.END}")
        print_info(f"Include transcript: {Colors.BOLD}{INCLUDE_TRANSCRIPT}{Colors.END}")
        print_info(f"Export folder: {Colors.BOLD}{EXPORT_FOLDER}/{Colors.END}")
        if final_organize_by_month:
            print_info(f"Organization: 📁 By month folders (e.g., {EXPORT_FOLDER}/2025-01/)")
        else:
            print_info(f"Organization: 📁 Single folder (all files in {EXPORT_FOLDER}/)")
        if final_separate_transcripts:
            print_info(f"Transcript extraction: 📄 Separate files (conversations and transcripts in separate files)")
        else:
            print_info(f"Transcript extraction: 📄 Combined (transcripts included with conversation data)")
        print()

        if final_organize_by_month:
            print_success(f"Export folder '{EXPORT_FOLDER}' ready (files will be organized by month)\n")
        else:
            print_success(f"Export folder '{EXPORT_FOLDER}' ready (all files in single folder)\n")
    
    # Group conversations by day (will be populated incrementally)
    conversations_by_day = defaultdict(list)
    files_written = set()  # Track which files we've already written
    file_lock = Lock()  # Thread lock for safe file writing
    
    def parse_timestamp(timestamp_value):
        """
        Parse a timestamp value into a UTC datetime object.
        Handles various formats: ISO 8601 strings, Unix timestamps, etc.
        """
        if timestamp_value is None:
            return None
            
        try:
            if isinstance(timestamp_value, str):
                # Handle ISO 8601 format strings
                # Replace 'Z' with '+00:00' for proper parsing
                timestamp_str = timestamp_value.replace('Z', '+00:00')
                # Try parsing with timezone info
                try:
                    dt = datetime.fromisoformat(timestamp_str)
                except ValueError:
                    # Try parsing without timezone and assume UTC
                    dt = datetime.fromisoformat(timestamp_value.replace('Z', ''))
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                
                # Ensure timezone info exists
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                else:
                    # Convert to UTC if it has timezone info
                    dt = dt.astimezone(ZoneInfo("UTC"))
                
                return dt
            elif isinstance(timestamp_value, (int, float)):
                # Unix timestamp (seconds since epoch)
                return datetime.fromtimestamp(timestamp_value, tz=ZoneInfo("UTC"))
            elif isinstance(timestamp_value, datetime):
                # Already a datetime object
                if timestamp_value.tzinfo is None:
                    return timestamp_value.replace(tzinfo=ZoneInfo("UTC"))
                return timestamp_value.astimezone(ZoneInfo("UTC"))
        except (ValueError, TypeError, OSError):
            return None
        
        return None
    
    def process_batch(batch_conversations, total_count):
        """
        Process a batch of conversations: group by day and save files incrementally.
        Thread-safe version for parallel processing.
        """
        new_days_found = []
        
        # Process conversations and group by day (thread-safe)
        with file_lock:
            for conversation in batch_conversations:
                # Extract the timestamp from the conversation (assuming it's in UTC from the API)
                timestamp_utc = None
                
                # Try common timestamp field names in order of likelihood
                for field in ['created_at', 'timestamp', 'date', 'time', 'started_at', 'updated_at', 'created', 'start_time']:
                    if field in conversation:
                        timestamp_utc = parse_timestamp(conversation[field])
                        if timestamp_utc:
                            break
                
                if timestamp_utc:
                    # Convert to user's timezone to determine which day it belongs to
                    timestamp_local = timestamp_utc.astimezone(user_tz)
                    day_key = timestamp_local.strftime("%Y-%m-%d")
                    conversations_by_day[day_key].append(conversation)
                    
                    # Track new days we've found
                    if day_key not in files_written:
                        new_days_found.append(day_key)
                else:
                    # If we can't determine the day, put it in a special "unknown" category
                    conversations_by_day["unknown"].append(conversation)
                    if "unknown" not in files_written:
                        new_days_found.append("unknown")
            
            # Save files for any new days we found, or update existing ones
            days_to_save = set(new_days_found)
            # Also save files for days that have new conversations (in case we're updating)
            for day_key in conversations_by_day.keys():
                if day_key not in files_written or day_key in new_days_found:
                    days_to_save.add(day_key)
        
        # Save files for the days we've updated (thread-safe)
        with file_lock:
            for day_key in sorted(days_to_save):
                day_conversations = conversations_by_day[day_key]
                
                if day_key == "unknown":
                    base_filename = f"conversation_export_unknown"
                else:
                    # Extract just the date part (YYYY-MM-DD) for filename
                    base_filename = f"conversation_export_{day_key}"
                
                # Determine folder path based on final_organize_by_month setting
                if final_organize_by_month:
                    if day_key == "unknown":
                        # Unknown conversations go in a special folder
                        month_folder = "unknown"
                    else:
                        # Extract year-month from day_key (format: YYYY-MM-DD)
                        year_month = day_key[:7]  # Gets "YYYY-MM"
                        month_folder = year_month
                    
                    # Create month folder if it doesn't exist
                    month_folder_path = os.path.join(EXPORT_FOLDER, month_folder)
                    os.makedirs(month_folder_path, exist_ok=True)
                    base_path = month_folder_path
                    display_prefix = f"{month_folder}/"
                else:
                    # Save all files directly in the export folder
                    base_path = EXPORT_FOLDER
                    display_prefix = ""
                
                if final_separate_transcripts:
                    # Separate transcripts from conversation metadata
                    conversations_metadata = []
                    transcripts_data = []
                    
                    for conv in day_conversations:
                        # Extract transcript_segments if they exist
                        transcript_segments = conv.get("transcript_segments", [])
                        
                        # Create conversation metadata without transcripts
                        conv_metadata = {k: v for k, v in conv.items() if k != "transcript_segments"}
                        conversations_metadata.append(conv_metadata)
                        
                        # Create transcript entry with conversation ID and segments
                        if transcript_segments:
                            transcripts_data.append({
                                "conversation_id": conv.get("id"),
                                "created_at": conv.get("created_at"),
                                "transcript_segments": transcript_segments
                            })
                    
                    # Save conversation metadata file
                    metadata_filename = f"{base_filename}.json"
                    metadata_filepath = os.path.join(base_path, metadata_filename)
                    with open(metadata_filepath, "w") as f:
                        json.dump(conversations_metadata, f, indent=4)
                    
                    # Save transcripts file (only if there are transcripts)
                    if transcripts_data:
                        transcript_filename = f"{base_filename}_transcripts.json"
                        transcript_filepath = os.path.join(base_path, transcript_filename)
                        with open(transcript_filepath, "w") as f:
                            json.dump(transcripts_data, f, indent=4)
                        
                        if day_key not in files_written:
                            print(f"  {Colors.GREEN}📁 Created files:{Colors.END} {Colors.CYAN}{display_prefix}{metadata_filename}{Colors.END} ({Colors.BOLD}{len(conversations_metadata)}{Colors.END} conversations)")
                            print(f"                  {Colors.CYAN}{display_prefix}{transcript_filename}{Colors.END} ({Colors.BOLD}{len(transcripts_data)}{Colors.END} transcripts)")
                        elif day_key in new_days_found:
                            print(f"  {Colors.BLUE}💾 Updated files:{Colors.END} {Colors.CYAN}{display_prefix}{metadata_filename}{Colors.END} ({Colors.BOLD}{len(conversations_metadata)}{Colors.END} conversations)")
                            print(f"                  {Colors.CYAN}{display_prefix}{transcript_filename}{Colors.END} ({Colors.BOLD}{len(transcripts_data)}{Colors.END} transcripts)")
                    else:
                        # No transcripts, just save metadata
                        if day_key not in files_written:
                            print(f"  {Colors.GREEN}📁 Created file:{Colors.END} {Colors.CYAN}{display_prefix}{metadata_filename}{Colors.END} ({Colors.BOLD}{len(conversations_metadata)}{Colors.END} conversations, no transcripts)")
                        elif day_key in new_days_found:
                            print(f"  {Colors.BLUE}💾 Updated file:{Colors.END} {Colors.CYAN}{display_prefix}{metadata_filename}{Colors.END} ({Colors.BOLD}{len(conversations_metadata)}{Colors.END} conversations)")
                else:
                    # Save everything together (original behavior)
                    filename = f"{base_filename}.json"
                    filepath = os.path.join(base_path, filename)
                    display_path = f"{display_prefix}{filename}"
                    
                    with open(filepath, "w") as f:
                        json.dump(day_conversations, f, indent=4)
                    
                    if day_key not in files_written:
                        print(f"  {Colors.GREEN}📁 Created file:{Colors.END} {Colors.CYAN}{display_path}{Colors.END} ({Colors.BOLD}{len(day_conversations)}{Colors.END} conversations)")
                    elif day_key in new_days_found:
                        print(f"  {Colors.BLUE}💾 Updated file:{Colors.END} {Colors.CYAN}{display_path}{Colors.END} (now {Colors.BOLD}{len(day_conversations)}{Colors.END} conversations)")
                
                if day_key not in files_written:
                    files_written.add(day_key)
    
        # Run the retrieval function with incremental processing callback
        print_info("🚀 Starting conversation retrieval...\n")
        results = get_conversations(start_date=QUERY_START, end_date=QUERY_END, callback=process_batch)
        
        # Final summary for conversations
        print_header("🎉 CONVERSATION EXPORT COMPLETE!")
        print_success(f"Total conversations retrieved: {Colors.BOLD}{len(results)}{Colors.END}")
        print_success(f"Total days with conversations: {Colors.BOLD}{len([k for k in conversations_by_day.keys() if k != 'unknown'])}{Colors.END}")
        
        if final_organize_by_month:
            # Group files by month for summary
            files_by_month = defaultdict(list)
            for day_key in conversations_by_day.keys():
                if day_key == "unknown":
                    month_folder = "unknown"
                    base_filename = "conversation_export_unknown"
                else:
                    year_month = day_key[:7]  # Gets "YYYY-MM"
                    month_folder = year_month
                    base_filename = f"conversation_export_{day_key}"
                
                day_conversations = conversations_by_day[day_key]
                
                if final_separate_transcripts:
                    # Count conversations with transcripts
                    conversations_with_transcripts = sum(1 for conv in day_conversations if conv.get("transcript_segments"))
                    metadata_filename = f"{base_filename}.json"
                    transcript_filename = f"{base_filename}_transcripts.json"
                    files_by_month[month_folder].append((day_key, metadata_filename, len(day_conversations), transcript_filename, conversations_with_transcripts))
                else:
                    filename = f"{base_filename}.json"
                    files_by_month[month_folder].append((day_key, filename, len(day_conversations), None, 0))
            
            print(f"\n{Colors.CYAN}📁 Files organized by month in '{EXPORT_FOLDER}/':{Colors.END}")
            
            # Print summary organized by month
            for month_folder in sorted(files_by_month.keys()):
                files_in_month = files_by_month[month_folder]
                total_conversations = sum(count for _, _, count, _, _ in files_in_month)
                
                # Format month name nicely (e.g., "2025-01" -> "January 2025")
                if month_folder != "unknown":
                    try:
                        year, month = month_folder.split("-")
                        month_num = int(month)
                        month_names = ["", "January", "February", "March", "April", "May", "June",
                                      "July", "August", "September", "October", "November", "December"]
                        month_name = f"{month_names[month_num]} {year}"
                    except:
                        month_name = month_folder
                else:
                    month_name = "Unknown"
                
                file_count = len(files_in_month) * (2 if final_separate_transcripts else 1)
                print(f"\n  {Colors.CYAN}📂 {Colors.BOLD}{month_name}{Colors.END} ({Colors.CYAN}{month_folder}/{Colors.END})")
                print(f"     {Colors.GREEN}{file_count}{Colors.END} files, {Colors.BOLD}{total_conversations}{Colors.END} total conversations")
                for day_key, filename, count, transcript_filename, transcript_count in sorted(files_in_month):
                    if final_separate_transcripts:
                        print(f"     {Colors.CYAN}•{Colors.END} {filename}: {Colors.BOLD}{count}{Colors.END} conversations")
                        if transcript_count > 0:
                            print(f"     {Colors.CYAN}•{Colors.END} {transcript_filename}: {Colors.BOLD}{transcript_count}{Colors.END} transcripts")
                    else:
                        print(f"     {Colors.CYAN}•{Colors.END} {filename}: {Colors.BOLD}{count}{Colors.END} conversations")
        else:
            # Simple flat list when not organizing by month
            print(f"\n{Colors.CYAN}Files saved in '{EXPORT_FOLDER}/':{Colors.END}")
            for day_key in sorted(conversations_by_day.keys()):
                day_conversations = conversations_by_day[day_key]
                if day_key == "unknown":
                    base_filename = "conversation_export_unknown"
                else:
                    base_filename = f"conversation_export_{day_key}"
                
                if final_separate_transcripts:
                    conversations_with_transcripts = sum(1 for conv in day_conversations if conv.get("transcript_segments"))
                    print(f"  {Colors.CYAN}•{Colors.END} {base_filename}.json: {Colors.BOLD}{len(day_conversations)}{Colors.END} conversations")
                    if conversations_with_transcripts > 0:
                        print(f"  {Colors.CYAN}•{Colors.END} {base_filename}_transcripts.json: {Colors.BOLD}{conversations_with_transcripts}{Colors.END} transcripts")
                else:
                    filename = f"{base_filename}.json"
                    print(f"  {Colors.CYAN}•{Colors.END} {filename}: {Colors.BOLD}{len(day_conversations)}{Colors.END} conversations")
        
        print_success(f"\n🎊 All conversation files saved successfully!")
    
    # Export memories if requested
    if export_memories:
        print_header("💭 MEMORY EXPORT")
        print_info(f"Fetching memories...")
        if final_memory_categories:
            print_info(f"Filtering by categories: {Colors.BOLD}{final_memory_categories}{Colors.END}")
        print()
        
        # Fetch all memories
        memories = get_memories(limit=final_memory_limit, offset=0, categories=final_memory_categories)
        
        if memories:
            # Create memories folder
            memories_folder = os.path.join(EXPORT_FOLDER, "memories")
            os.makedirs(memories_folder, exist_ok=True)
            
            # Save all memories to a single file
            memories_filename = "memories_export.json"
            if final_memory_categories:
                # Include categories in filename
                safe_categories = final_memory_categories.replace(",", "_").replace(" ", "")
                memories_filename = f"memories_export_{safe_categories}.json"
            
            memories_filepath = os.path.join(memories_folder, memories_filename)
            
            with open(memories_filepath, "w") as f:
                json.dump(memories, f, indent=4)
            
            print_success(f"\n💾 Saved {Colors.BOLD}{len(memories)}{Colors.END} memories to: {Colors.CYAN}{memories_folder}/{memories_filename}{Colors.END}")
            
            # Show category breakdown if available
            if memories:
                categories_count = defaultdict(int)
                for memory in memories:
                    category = memory.get("category", "unknown")
                    categories_count[category] += 1
                
                if len(categories_count) > 1:
                    print_info(f"\nMemory breakdown by category:")
                    for category, count in sorted(categories_count.items()):
                        print_info(f"  • {Colors.BOLD}{category}{Colors.END}: {count}")
        else:
            print_warning("No memories found.")
    
    # Final overall summary
    print_header("🎉 EXPORT COMPLETE!")
    if export_conversations:
        print_success(f"Conversations: {Colors.BOLD}{len(results)}{Colors.END} exported")
    if export_memories:
        print_success(f"Memories: {Colors.BOLD}{len(memories)}{Colors.END} exported")
    print_success(f"\n🎊 All exports saved successfully!")