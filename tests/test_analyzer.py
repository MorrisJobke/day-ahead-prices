"""Tests for PriceAnalyzer."""
import pytest
import pandas as pd
from datetime import datetime

from src.analyzer import PriceAnalyzer


def test_get_negative_periods():
    """Test identification of negative price periods."""
    analyzer = PriceAnalyzer()
    
    # Create sample data with negative prices
    timestamps = pd.date_range('2025-01-01 00:00', periods=8, freq='15min')
    prices = [10.5, -5.2, -3.1, -1.5, 8.0, -2.0, 12.5, 15.0]
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'price': prices
    })
    
    periods = analyzer.get_negative_periods(df)
    
    # Should identify 2 negative periods
    assert len(periods) == 2
    
    # First period: quarters 1-3 (negative)
    assert periods[0]['duration_quarters'] == 3
    assert periods[0]['duration_hours'] == 0.75
    
    # Second period: quarter 5 (negative)
    assert periods[1]['duration_quarters'] == 1
    assert periods[1]['duration_hours'] == 0.25


def test_get_negative_periods_empty():
    """Test empty DataFrame handling."""
    analyzer = PriceAnalyzer()
    df = pd.DataFrame()
    
    periods = analyzer.get_negative_periods(df)
    assert periods == []


def test_get_negative_periods_no_negative():
    """Test with no negative prices."""
    analyzer = PriceAnalyzer()
    
    timestamps = pd.date_range('2025-01-01 00:00', periods=4, freq='15min')
    prices = [10.5, 8.2, 5.1, 12.5]
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'price': prices
    })
    
    periods = analyzer.get_negative_periods(df)
    assert periods == []

