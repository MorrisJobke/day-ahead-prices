"""Output generator for creating static analysis files."""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.analyzer import PriceAnalyzer
from src.compensation import CompensationCalculator
from src.utils import ensure_dir, load_config


class OutputGenerator:
    """Generates static output files for analysis results."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize the output generator.
        
        Args:
            config: Configuration dict. If None, loads from config.yaml
        """
        self.config = config or load_config()
        self.output_dir = Path(self.config['output']['directory'])
        ensure_dir(self.output_dir)
        
        self.analyzer = PriceAnalyzer(config)
        self.compensation_calc = CompensationCalculator(config)
    
    def generate_summary(self) -> Dict:
        """Generate overall summary statistics.
        
        Returns:
            Summary dict with key statistics
        """
        dates = self.analyzer.fetcher.get_cached_dates()
        if not dates:
            return {'error': 'No data available'}
        
        # Analyze all available data
        all_periods = self.analyzer.get_all_negative_periods()
        total_negative_quarters = sum(p['duration_quarters'] for p in all_periods)
        
        # Get current year stats
        current_year = datetime.now().year
        year_stats = self.analyzer.analyze_year(current_year)
        
        summary = {
            'generated_at': datetime.now().isoformat(),
            'data_period': {
                'start': dates[0] if dates else None,
                'end': dates[-1] if dates else None,
                'total_days': len(dates)
            },
            'total_negative_quarters': total_negative_quarters,
            'total_negative_hours': total_negative_quarters * 0.25,
            'total_periods': len(all_periods),
            'current_year': {
                'year': current_year,
                'negative_quarters': year_stats.get('negative_quarters', 0),
                'negative_hours': year_stats.get('negative_hours', 0),
                'months': year_stats.get('months_analyzed', 0)
            },
            'eeg_rule_info': {
                'rule_start_date': self.config['eeg']['rule_start_date'],
                'compensation_period_years': self.config['eeg']['compensation_period_years']
            }
        }
        
        # Save to file
        output_file = self.output_dir / 'summary.json'
        with open(output_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        return summary
    
    def generate_monthly_files(self) -> List[str]:
        """Generate monthly analysis files.
        
        Returns:
            List of generated file paths
        """
        generated = []
        dates = self.analyzer.fetcher.get_cached_dates()
        
        # Group dates by year-month
        months = set()
        for date in dates:
            parts = date.split('-')
            months.add((int(parts[0]), int(parts[1])))
        
        for year, month in sorted(months):
            month_result = self.analyzer.analyze_month(year, month)
            if month_result['days_analyzed'] > 0:
                filename = f"{year}-{month:02d}.json"
                output_file = self.output_dir / filename
                
                with open(output_file, 'w') as f:
                    json.dump(month_result, f, indent=2)
                
                generated.append(str(output_file))
        
        return generated
    
    def generate_periods_file(self) -> str:
        """Generate file with all negative price periods.
        
        Returns:
            Path to generated file
        """
        all_periods = self.analyzer.get_all_negative_periods()
        
        output = {
            'generated_at': datetime.now().isoformat(),
            'total_periods': len(all_periods),
            'periods': all_periods
        }
        
        output_file = self.output_dir / 'periods.json'
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        return str(output_file)
    
    def generate_annual_csv(self, year: int) -> str:
        """Generate annual CSV file for spreadsheet analysis.
        
        Args:
            year: Year to generate
            
        Returns:
            Path to generated file
        """
        import csv
        
        year_result = self.analyzer.analyze_year(year)
        
        filename = f"{year}.csv"
        output_file = self.output_dir / filename
        
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Date', 'Total Quarters', 'Negative Quarters',
                'Negative Hours', 'Negative %', 'Min Price',
                'Max Price', 'Avg Price', 'Period Count'
            ])
            
            # Data rows
            for month_data in year_result.get('monthly_breakdown', []):
                for day_data in month_data.get('daily_breakdown', []):
                    writer.writerow([
                        day_data['date'],
                        day_data['total_quarters'],
                        day_data['negative_quarters'],
                        day_data['negative_hours'],
                        round(day_data['negative_percentage'], 2),
                        round(day_data['min_price'], 2),
                        round(day_data['max_price'], 2),
                        round(day_data['avg_price'], 2),
                        len(day_data['periods'])
                    ])
        
        return str(output_file)
    
    def generate_all(self) -> Dict:
        """Generate all output files.
        
        Returns:
            Dict with information about generated files
        """
        print("Generating summary...")
        summary = self.generate_summary()
        
        print("Generating monthly files...")
        monthly_files = self.generate_monthly_files()
        
        print("Generating periods file...")
        periods_file = self.generate_periods_file()
        
        # Generate CSV for current year
        print("Generating CSV files...")
        current_year = datetime.now().year
        csv_file = self.generate_annual_csv(current_year)
        
        result = {
            'generated_at': datetime.now().isoformat(),
            'files': {
                'summary': 'summary.json',
                'periods': 'periods.json',
                'monthly_count': len(monthly_files),
                'csv_files': [f'{current_year}.csv']
            },
            'output_directory': str(self.output_dir)
        }
        
        print(f"\n✓ Generated {len(monthly_files) + 3} files in {self.output_dir}")
        return result

