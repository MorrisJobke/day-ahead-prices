"""Price analysis module to identify periods when § 51 EEG applies."""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from src.data_fetcher import DataFetcher
from src.utils import load_config


class PriceAnalyzer:
    """Analyzes price data to identify negative periods and calculate statistics."""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize the analyzer.

        Args:
            config: Configuration dict. If None, loads from config.yaml
        """
        self.config = config or load_config()
        self.fetcher = DataFetcher(config)
        self.rule_start_date = self.config['eeg']['rule_start_date']

    def parse_price_data(self, data: Dict, date: str = None) -> pd.DataFrame:
        """Parse API response into pandas DataFrame.

        Args:
            data: API response data
            date: Date in YYYY-MM-DD format (optional, for data type detection)

        Returns:
            DataFrame with timestamp and price columns
        """
        if not data or 'price' not in data:
            return pd.DataFrame()

        # API returns Unix timestamps in seconds (not milliseconds)
        timestamps = [datetime.fromtimestamp(ts) for ts in data.get('unix_seconds', [])]
        prices = data['price']

        # Determine if data is hourly or quarter-hourly
        # Before Oct 1, 2025: 24 data points (hourly)
        # From Oct 1, 2025 onwards: 96 data points (quarter-hourly) (or 92/100 when there is the summer time change)
        # Check number of data points first (more reliable than date)
        is_quarter_hourly = len(timestamps) >= 90

        # If ambiguous, use date as fallback
        if len(timestamps) == 24 and date:
            transition_date = datetime(2025, 10, 1)
            data_date = datetime.strptime(date, "%Y-%m-%d")
            is_quarter_hourly = data_date >= transition_date

        df = pd.DataFrame({
            'timestamp': timestamps,
            'price': prices
        })

        # Store metadata about data resolution
        df.attrs['is_quarter_hourly'] = is_quarter_hourly
        df.attrs['resolution_hours'] = 0.25 if is_quarter_hourly else 1.0

        return df

    def get_negative_periods(self, df: pd.DataFrame) -> List[Dict]:
        """Identify continuous periods of negative prices.

        Args:
            df: DataFrame with price data

        Returns:
            List of dicts with start, end, and duration for each negative period
        """
        if df.empty:
            return []

        # Get resolution from metadata (default to 0.25 hours for quarter-hourly)
        resolution_hours = df.attrs.get('resolution_hours', 0.25)

        # Identify negative periods
        df['is_negative'] = df['price'] < 0
        df['period_id'] = (df['is_negative'] != df['is_negative'].shift()).cumsum()

        negative_periods = []
        for period_id, group in df[df['is_negative']].groupby('period_id'):
            # Calculate duration based on actual resolution
            duration_units = len(group)
            duration_hours = duration_units * resolution_hours

            end_timestamp = group['timestamp'].iloc[-1]
            if resolution_hours == 0.25:
                minute = (end_timestamp.minute // 15) * 15 + 14
                end_time = end_timestamp.replace(minute=minute, second=59, microsecond=0)
            else:
                end_time = end_timestamp.replace(minute=59, second=59, microsecond=0)

            negative_periods.append({
                'start': group['timestamp'].iloc[0].isoformat(),
                'end': end_time.isoformat(),
                'duration_units': duration_units,
                'duration_hours': duration_hours,
                'min_price': group['price'].min(),
                'max_price': group['price'].max(),
                'avg_price': group['price'].mean()
            })

        return negative_periods

    def analyze_day(self, date: str) -> Dict:
        """Analyze price data for a single day.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Analysis results for the day
        """
        data = self.fetcher.load_cached_data(date)
        if not data:
            return None

        df = self.parse_price_data(data, date)
        if df.empty:
            return None

        # Get resolution from metadata
        resolution_hours = df.attrs.get('resolution_hours', 0.25)
        is_quarter_hourly = df.attrs.get('is_quarter_hourly', True)

        negative_periods = self.get_negative_periods(df)
        total_negative_units = sum(p['duration_units'] for p in negative_periods)
        total_negative_hours = sum(p['duration_hours'] for p in negative_periods)

        return {
            'date': date,
            'resolution': 'quarter_hourly' if is_quarter_hourly else 'hourly',
            'total_units': len(df),
            'negative_units': total_negative_units,
            'negative_hours': total_negative_hours,
            'negative_percentage': (total_negative_units / len(df) * 100) if len(df) > 0 else 0,
            'periods': negative_periods,
            'min_price': df['price'].min(),
            'max_price': df['price'].max(),
            'avg_price': df['price'].mean()
        }

    def analyze_month(self, year: int, month: int) -> Dict:
        """Analyze price data for a month.

        Args:
            year: Year
            month: Month (1-12)

        Returns:
            Analysis results for the month
        """
        # Get all dates in the month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)

        daily_results = []
        negative_units_total = 0
        negative_hours_total = 0.0

        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            day_result = self.analyze_day(date_str)
            if day_result:
                daily_results.append(day_result)
                negative_units_total += day_result['negative_units']
                negative_hours_total += day_result['negative_hours']
            current += timedelta(days=1)

        return {
            'year': year,
            'month': month,
            'days_analyzed': len(daily_results),
            'total_units': sum(r['total_units'] for r in daily_results),
            'negative_units': negative_units_total,
            'negative_hours': negative_hours_total,
            'daily_breakdown': daily_results
        }

    def analyze_year(self, year: int) -> Dict:
        """Analyze price data for a year.

        Args:
            year: Year

        Returns:
            Analysis results for the year
        """
        monthly_results = []
        total_negative_units = 0
        total_negative_hours = 0.0

        for month in range(1, 13):
            month_result = self.analyze_month(year, month)
            if month_result['days_analyzed'] > 0:
                monthly_results.append(month_result)
                total_negative_units += month_result['negative_units']
                total_negative_hours += month_result['negative_hours']

        return {
            'year': year,
            'months_analyzed': len(monthly_results),
            'total_units': sum(r['total_units'] for r in monthly_results),
            'negative_units': total_negative_units,
            'negative_hours': total_negative_hours,
            'monthly_breakdown': monthly_results
        }

    def get_all_negative_periods(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Get all negative price periods in date range.

        Args:
            start_date: Start date (YYYY-MM-DD), defaults to config start
            end_date: End date (YYYY-MM-DD), defaults to today

        Returns:
            List of all negative periods
        """
        if start_date is None:
            start_date = self.config['dates']['start_date']
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        all_periods = []
        dates = self.fetcher.get_cached_dates()

        for date in dates:
            if date < start_date or date > end_date:
                continue

            day_result = self.analyze_day(date)
            if day_result and day_result['periods']:
                for period in day_result['periods']:
                    period['date'] = date
                    all_periods.append(period)

        return all_periods

