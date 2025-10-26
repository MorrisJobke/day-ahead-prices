"""Compensation calculator for § 51a EEG period extensions."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

from src.analyzer import PriceAnalyzer
from src.utils import load_config


class CompensationCalculator:
    """Calculates compensation period extensions according to § 51a EEG."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the calculator.
        
        Args:
            config: Configuration dict. If None, loads from config.yaml
        """
        self.config = config or load_config()
        self.analyzer = PriceAnalyzer(config)
        self.compensation_period_years = self.config['eeg']['compensation_period_years']
        self.rule_start_date = self.config['eeg']['rule_start_date']
    
    def calculate_period_extension(
        self,
        start_date: str,
        negative_quarters: int,
        installation_type: str = "general"
    ) -> Dict:
        """Calculate the extended compensation period.
        
        According to § 51a EEG, the compensation period is extended by the
        amount of time lost due to negative prices.
        
        For PV installations, § 51a Abs. 2 provides a special distribution mechanism
        based on monthly production patterns.
        
        Args:
            start_date: Start of the 20-year compensation period (YYYY-MM-DD)
            negative_quarters: Total number of negative quarter-hours
            installation_type: "pv", "general", or "biogas"
            
        Returns:
            Dict with original period, extended period, and details
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end_original = start + timedelta(days=self.compensation_period_years * 365)
        
        # Basic extension: add the lost time
        extension_hours = negative_quarters * 0.25
        extension_days = extension_hours / 24
        
        if installation_type == "pv":
            # PV-specific calculation with monthly distribution
            end_extended = self._calculate_pv_extension(start, end_original, negative_quarters)
        else:
            # Simple extension: add lost hours to the end
            end_extended = end_original + timedelta(days=extension_days)
        
        return {
            'start_date': start_date,
            'original_end_date': end_original.strftime("%Y-%m-%d"),
            'extended_end_date': end_extended.strftime("%Y-%m-%d"),
            'negative_quarters': negative_quarters,
            'negative_hours': extension_hours,
            'extension_days': (end_extended - end_original).days,
            'installation_type': installation_type,
            'compensation_period_years': self.compensation_period_years
        }
    
    def _calculate_pv_extension(
        self,
        start_date: datetime,
        original_end: datetime,
        negative_quarters: int
    ) -> datetime:
        """Calculate PV extension with monthly distribution.
        
        According to § 51a Abs. 2 EEG, PV installations have a special mechanism
        that distributes the compensation over months after the 20-year period,
        with more compensation in months with less solar radiation.
        
        This is a simplified implementation that distributes quarters across months
        with weights based on typical solar production patterns (higher in summer).
        
        Args:
            start_date: Start of compensation period
            original_end: End of original 20-year period
            negative_quarters: Total negative quarters to distribute
            
        Returns:
            Extended end date
        """
        # Monthly solar production weights (higher in summer = less extension needed)
        # In summer months, we need to add more months to compensate for low winter production
        month_weights = {
            1: 1.5,   # January (winter, low sun)
            2: 1.5,   # February
            3: 1.3,   # March
            4: 1.0,   # April
            5: 0.8,   # May
            6: 0.7,   # June (summer, high sun)
            7: 0.7,   # July
            8: 0.8,   # August
            9: 1.0,   # September
            10: 1.3,  # October
            11: 1.5,  # November
            12: 1.5   # December
        }
        
        # Distribute quarters across months starting from the end month
        quarters_per_month = defaultdict(float)
        remaining_quarters = negative_quarters
        
        current_month = original_end.month
        current_year = original_end.year
        
        while remaining_quarters > 0:
            # Weight determines how many quarters go to this month
            weight = month_weights[current_month]
            quarters_for_month = min(remaining_quarters, 744 * weight)  # ~744 quarters/month
            
            quarters_per_month[f"{current_year}-{current_month:02d}"] += quarters_for_month
            remaining_quarters -= quarters_for_month
            
            # Move to previous month
            if current_month == 1:
                current_month = 12
                current_year -= 1
            else:
                current_month -= 1
        
        # Calculate how many full months are needed
        months_added = len([m for m, q in quarters_per_month.items() if q > 0])
        
        # Add months to original end date
        extended_end = original_end
        for i in range(months_added):
            # Add one month
            if extended_end.month == 12:
                extended_end = extended_end.replace(year=extended_end.year + 1, month=1)
            else:
                extended_end = extended_end.replace(month=extended_end.month + 1)
        
        return extended_end
    
    def calculate_for_installation(
        self,
        installation_date: str,
        start_date: str = None,
        end_date: str = None
    ) -> Dict:
        """Calculate compensation extension for a specific installation.
        
        Args:
            installation_date: When the installation started operation
            start_date: Start date for analysis (defaults to installation_date)
            end_date: End date for analysis (defaults to today)
            
        Returns:
            Full analysis with period extension calculation
        """
        if start_date is None:
            start_date = installation_date
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get negative quarters for the relevant period
        negative_periods = self.analyzer.get_all_negative_periods(start_date, end_date)
        total_negative_quarters = sum(p['duration_quarters'] for p in negative_periods)
        
        # Calculate extension
        # For installations after Feb 25, 2025, new rules apply
        if installation_date >= self.rule_start_date:
            installation_type = "general"  # Could be more specific based on plant type
        else:
            # Older installations use different rules
            installation_type = "general"
        
        extension_info = self.calculate_period_extension(
            installation_date,
            total_negative_quarters,
            installation_type
        )
        
        return {
            'installation_date': installation_date,
            'analysis_period': {
                'start': start_date,
                'end': end_date
            },
            'negative_periods_count': len(negative_periods),
            'total_negative_quarters': total_negative_quarters,
            'total_negative_hours': total_negative_quarters * 0.25,
            'extension': extension_info
        }

