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
    
    def parse_price_data(self, data: Dict) -> pd.DataFrame:
        """Parse API response into pandas DataFrame.
        
        Args:
            data: API response data
            
        Returns:
            DataFrame with timestamp and price columns
        """
        if not data or 'price' not in data:
            return pd.DataFrame()
        
        # API returns Unix timestamps (ms) and prices
        timestamps = [datetime.fromtimestamp(ts / 1000) for ts in data.get('unix_seconds', [])]
        prices = data['price']
        
        df = pd.DataFrame({
            'timestamp': timestamps,
            'price': prices
        })
        
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
        
        # Identify negative periods
        df['is_negative'] = df['price'] < 0
        df['period_id'] = (df['is_negative'] != df['is_negative'].shift()).cumsum()
        
        negative_periods = []
        for period_id, group in df[df['is_negative']].groupby('period_id'):
            negative_periods.append({
                'start': group['timestamp'].iloc[0].isoformat(),
                'end': group['timestamp'].iloc[-1].isoformat(),
                'duration_quarters': len(group),
                'duration_hours': len(group) * 0.25,
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
        
        df = self.parse_price_data(data)
        if df.empty:
            return None
        
        negative_periods = self.get_negative_periods(df)
        total_negative_quarters = sum(p['duration_quarters'] for p in negative_periods)
        
        return {
            'date': date,
            'total_quarters': len(df),
            'negative_quarters': total_negative_quarters,
            'negative_hours': total_negative_quarters * 0.25,
            'negative_percentage': (total_negative_quarters / len(df) * 100) if len(df) > 0 else 0,
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
        negative_quarters_total = 0
        
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            day_result = self.analyze_day(date_str)
            if day_result:
                daily_results.append(day_result)
                negative_quarters_total += day_result['negative_quarters']
            current += timedelta(days=1)
        
        return {
            'year': year,
            'month': month,
            'days_analyzed': len(daily_results),
            'total_quarters': sum(r['total_quarters'] for r in daily_results),
            'negative_quarters': negative_quarters_total,
            'negative_hours': negative_quarters_total * 0.25,
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
        total_negative_quarters = 0
        
        for month in range(1, 13):
            month_result = self.analyze_month(year, month)
            if month_result['days_analyzed'] > 0:
                monthly_results.append(month_result)
                total_negative_quarters += month_result['negative_quarters']
        
        return {
            'year': year,
            'months_analyzed': len(monthly_results),
            'total_quarters': sum(r['total_quarters'] for r in monthly_results),
            'negative_quarters': total_negative_quarters,
            'negative_hours': total_negative_quarters * 0.25,
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

