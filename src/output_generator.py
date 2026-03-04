"""Output generator for creating static analysis files."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

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
        total_negative_units = sum(p['duration_units'] for p in all_periods)
        total_negative_hours = sum(p['duration_hours'] for p in all_periods)

        # Get current year stats
        current_year = datetime.now().year
        year_stats = self.analyzer.analyze_year(current_year)

        summary = {
            'data_period': {
                'start': dates[0] if dates else None,
                'end': dates[-1] if dates else None,
                'total_days': len(dates)
            },
            'total_negative_units': total_negative_units,
            'total_negative_hours': total_negative_hours,
            'total_periods': len(all_periods),
            'current_year': {
                'year': current_year,
                'negative_units': year_stats.get('negative_units', 0),
                'negative_hours': year_stats.get('negative_hours', 0),
                'monthly_negative_hours': {month['month']: month['negative_hours'] for month in year_stats.get('monthly_breakdown', [])},
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
                'Date', 'Resolution', 'Total Units', 'Negative Units',
                'Negative Hours', 'Negative %', 'Min Price',
                'Max Price', 'Avg Price', 'Period Count'
            ])

            # Data rows
            for month_data in year_result.get('monthly_breakdown', []):
                for day_data in month_data.get('daily_breakdown', []):
                    writer.writerow([
                        day_data['date'],
                        day_data.get('resolution', 'quarter_hourly'),
                        day_data['total_units'],
                        day_data['negative_units'],
                        round(day_data['negative_hours'], 2),
                        round(day_data['negative_percentage'], 2),
                        round(day_data['min_price'], 2),
                        round(day_data['max_price'], 2),
                        round(day_data['avg_price'], 2),
                        len(day_data['periods'])
                    ])

        return str(output_file)

    def generate_daily_view(self) -> Dict:
        """Generate daily price view JSON for the web dashboard.

        Returns:
            Dict with today's and (if after 14:00) tomorrow's price data
        """
        now = datetime.now(ZoneInfo('Europe/Berlin'))
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

        location = self.config.get('location', {'lat': 51.1657, 'lng': 10.4515})

        def format_day_data(date: str) -> Optional[Dict]:
            raw = self.analyzer.fetcher.load_cached_data(date)
            if not raw:
                return None

            unix_seconds = raw.get('unix_seconds') or []
            raw_prices = raw.get('price') or []
            if not unix_seconds or not raw_prices:
                return None

            df = self.analyzer.parse_price_data(raw, date)
            if df.empty:
                return None

            # Read resolution before get_negative_periods modifies the df
            is_qh = df.attrs.get('is_quarter_hourly', True)
            negative_periods = self.analyzer.get_negative_periods(df)

            prices = [
                {'unix_seconds': int(ts), 'price': round(float(p), 2)}
                for ts, p in zip(unix_seconds, raw_prices)
            ]

            return {
                'date': date,
                'resolution': 'quarter_hourly' if is_qh else 'hourly',
                'prices': prices,
                'negative_periods': [
                    {
                        'start': p['start'],
                        'end': p['end'],
                        'duration_hours': round(p['duration_hours'], 2),
                        'avg_price': round(float(p['avg_price']), 2),
                        'min_price': round(float(p['min_price']), 2),
                    }
                    for p in negative_periods
                ],
                'stats': {
                    'min_price': round(float(df['price'].min()), 2),
                    'max_price': round(float(df['price'].max()), 2),
                    'avg_price': round(float(df['price'].mean()), 2),
                    'negative_hours': round(
                        sum(p['duration_hours'] for p in negative_periods), 2
                    ),
                },
            }

        # Tomorrow's prices are published around 14:00
        include_tomorrow = now.hour >= 14

        output = {
            'location': location,
            'yesterday': format_day_data(yesterday),
            'today': format_day_data(today),
            'tomorrow': format_day_data(tomorrow) if include_tomorrow else None,
        }

        output_file = self.output_dir / 'daily_view.json'
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)

        return output

    def generate_web_view(self) -> Optional[str]:
        """Copy web dashboard HTML template to output directory.

        Returns:
            Path to the generated index.html, or None if template missing
        """
        import shutil

        template_path = Path(__file__).parent.parent / 'web' / 'index.html'
        output_file = self.output_dir / 'index.html'

        if not template_path.exists():
            print(f"Warning: web template not found at {template_path}")
            return None

        shutil.copy2(template_path, output_file)
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

        print("Generating daily view for web dashboard...")
        self.generate_daily_view()

        print("Generating web dashboard...")
        self.generate_web_view()

        result = {
            'files': {
                'summary': 'summary.json',
                'periods': 'periods.json',
                'monthly_count': len(monthly_files),
                'csv_files': [f'{current_year}.csv'],
                'daily_view': 'daily_view.json',
                'web_dashboard': 'index.html',
            },
            'output_directory': str(self.output_dir)
        }

        print(f"\n✓ Generated {len(monthly_files) + 5} files in {self.output_dir}")
        return result

