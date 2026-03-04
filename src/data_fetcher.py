"""Data fetcher module for downloading and caching day-ahead prices."""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from dateutil.parser import parse as parse_date

from src.utils import load_config, ensure_dir


def get_fetch_end_date() -> datetime:
    """Get the appropriate end date for fetching prices.

    If current time is after 2 PM (14:00), fetch tomorrow's prices as well,
    since next day prices are published at 2 PM local time.

    Returns:
        datetime object representing the end date for fetching
    """
    now = datetime.now(ZoneInfo('Europe/Berlin'))
    if now.hour >= 14:  # After 2 PM CET/CEST
        return (now + timedelta(days=1)).date()
    return now.date()


class DataFetcher:
    """Fetches and caches day-ahead electricity prices."""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the data fetcher with configuration.

        Args:
            config: Configuration dict. If None, loads from config.yaml
        """
        self.config = config or load_config()
        self.api_url = f"{self.config['api']['base_url']}{self.config['api']['endpoint']}"
        self.cache_dir = Path(self.config['cache']['data_dir'])
        ensure_dir(self.cache_dir)

    def fetch_day(self, date: str) -> Optional[Dict]:
        """Fetch price data for a specific day.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Dict with price data or None if fetch fails
        """
        # Check cache first
        cache_file = self.cache_dir / f"{date}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        # Fetch from API with retry logic for rate limiting
        max_retries = 5
        initial_wait = 1  # seconds

        for attempt in range(max_retries):
            try:
                # Fetch specific day's prices from the API
                # API accepts daily format (YYYY-MM-DD) for both start and end
                response = requests.get(
                    self.api_url,
                    params={
                        "bzn": "DE-LU",  # Bidding zone instead of country
                        "start": date,    # Daily format (YYYY-MM-DD)
                        "end": date       # Same date for single day
                    },
                    timeout=self.config['api']['timeout']
                )

                # Handle rate limiting with exponential backoff
                if response.status_code == 429:
                    wait_time = initial_wait * (2 ** attempt)
                    if attempt < max_retries - 1:
                        print(f"Rate limit hit for {date}. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"Max retries reached for {date}. Giving up.")
                        return None

                response.raise_for_status()
                data = response.json()

                # Add metadata about the requested date
                data['requested_date'] = date

                # Cache the data
                with open(cache_file, 'w') as f:
                    json.dump(data, f, indent=2)

                return data

            except requests.RequestException as e:
                # For other HTTP errors, don't retry
                if hasattr(e.response, 'status_code') and e.response.status_code != 429:
                    print(f"Error fetching data for {date}: {e}")
                    return None
                # For network errors or 429 without response object
                if attempt == max_retries - 1:
                    print(f"Error fetching data for {date}: {e}")
                    return None
                # Retry for network errors
                wait_time = initial_wait * (2 ** attempt)
                print(f"Network error for {date}. Retrying in {wait_time}s...")
                time.sleep(wait_time)

        return None

    def fetch_date_range(self, start_date: str, end_date: str, progress: bool = True) -> List[str]:
        """Fetch price data for a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            progress: Print progress updates

        Returns:
            List of dates that were successfully fetched
        """
        start = parse_date(start_date).date()
        end = parse_date(end_date).date()
        current = start
        fetched = []

        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            if progress:
                print(f"Fetching {date_str}...")

            data = self.fetch_day(date_str)
            if data:
                fetched.append(date_str)

            current += timedelta(days=1)

        return fetched

    def get_cached_dates(self) -> List[str]:
        """Get list of all dates with cached data.

        Returns:
            List of dates in YYYY-MM-DD format
        """
        dates = []
        for file in self.cache_dir.glob("*.json"):
            dates.append(file.stem)
        return sorted(dates)

    def load_cached_data(self, date: str) -> Optional[Dict]:
        """Load cached data for a date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Cached data or None
        """
        cache_file = self.cache_dir / f"{date}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return None


if __name__ == "__main__":
    fetcher = DataFetcher()

    # Fetch initial data from config start date to today (or tomorrow if after 2 PM)
    end_date = get_fetch_end_date()
    start_date = parse_date(fetcher.config['dates']['start_date']).date()

    print(f"Fetching data from {start_date} to {end_date}")
    fetched = fetcher.fetch_date_range(str(start_date), str(end_date))
    print(f"Successfully fetched {len(fetched)} days")
