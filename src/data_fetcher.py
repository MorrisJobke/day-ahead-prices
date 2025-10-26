"""Data fetcher module for downloading and caching day-ahead prices."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
import yaml
from dateutil.parser import parse as parse_date

from src.utils import load_config, ensure_dir


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
        
        # Fetch from API
        try:
            # Note: API returns current day prices regardless of date parameter
            # We'll use the date from the file or current date
            response = requests.get(
                self.api_url,
                params={
                    "country": self.config['api']['country']
                },
                timeout=self.config['api']['timeout']
            )
            response.raise_for_status()
            data = response.json()
            
            # Add metadata about the requested date
            data['requested_date'] = date

            # Cache the data
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return data
        except requests.RequestException as e:
            print(f"Error fetching data for {date}: {e}")
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
    
    # Fetch initial data from config start date to today
    end_date = datetime.now().date()
    start_date = parse_date(fetcher.config['dates']['start_date']).date()
    
    print(f"Fetching data from {start_date} to {end_date}")
    fetched = fetcher.fetch_date_range(str(start_date), str(end_date))
    print(f"Successfully fetched {len(fetched)} days")

