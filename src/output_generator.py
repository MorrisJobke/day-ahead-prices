"""Output generator for creating static analysis files."""
import calendar
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from src.analyzer import PriceAnalyzer
from src.compensation import CompensationCalculator
from src.utils import ensure_dir, load_config, sunrise_sunset_utc


def _sunrise_sunset_utc(date_str: str, lat: float, lng: float) -> Tuple[Optional[float], Optional[float]]:
    return sunrise_sunset_utc(date_str, lat, lng)


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

    def generate_history_view(self) -> Optional[str]:
        """Generate historical price distribution statistics for the web dashboard.

        Returns:
            Path to the generated history_view.json, or None on error
        """
        import shutil

        dates = sorted(self.analyzer.fetcher.get_cached_dates())
        if not dates:
            return None

        loc = self.config.get('location', {})
        lat = loc.get('lat', 51.0)
        lng = loc.get('lng', 10.0)

        # month_data: {(year, month): {...accumulators...}}
        month_data: Dict = {}

        for date_str in dates:
            raw = self.analyzer.fetcher.load_cached_data(date_str)
            if not raw:
                continue
            prices = raw.get('price') or []
            if not prices:
                continue

            timestamps = raw.get('unix_seconds') or []
            is_qh = len(prices) >= 90
            slot_hours = 0.25 if is_qh else 1.0
            slot_secs = slot_hours * 3600.0

            sunrise_ts, sunset_ts = _sunrise_sunset_utc(date_str, lat, lng)

            year, month, _ = (int(x) for x in date_str.split('-'))
            key = (year, month)
            if key not in month_data:
                month_data[key] = {
                    'days': 0,
                    'negative_days': 0,
                    'total_hours': 0.0,
                    'daylight_hours': 0.0,
                    'daylight_neg_hours': 0.0,
                    'price_sum': 0.0,
                    'price_count': 0,
                    'daily_spreads': [],
                    'buckets': {
                        'deeply_negative': 0.0,
                        'negative': 0.0,
                        'near_zero_neg': 0.0,
                        'near_zero_pos': 0.0,
                        'normal': 0.0,
                    }
                }

            md = month_data[key]
            md['days'] += 1
            if any(p < 0 for p in prices):
                md['negative_days'] += 1
            day_min = min(prices)
            day_max = max(prices)
            md['daily_spreads'].append(day_max - day_min)

            for i, p in enumerate(prices):
                md['total_hours'] += slot_hours
                md['price_sum'] += p * slot_hours
                md['price_count'] += 1
                if p < -50:
                    md['buckets']['deeply_negative'] += slot_hours
                elif p < -10:
                    md['buckets']['negative'] += slot_hours
                elif p < 0:
                    md['buckets']['near_zero_neg'] += slot_hours
                elif p <= 10:
                    md['buckets']['near_zero_pos'] += slot_hours
                else:
                    md['buckets']['normal'] += slot_hours

                # Daylight check: slot overlaps [sunrise, sunset)
                if sunrise_ts is not None and i < len(timestamps):
                    slot_start = float(timestamps[i])
                    slot_end = slot_start + slot_secs
                    if slot_start < sunset_ts and slot_end > sunrise_ts:
                        md['daylight_hours'] += slot_hours
                        if p < 0:
                            md['daylight_neg_hours'] += slot_hours

        # Build monthly_stats list
        month_labels = {
            1: 'Jan', 2: 'Feb', 3: 'Mär', 4: 'Apr', 5: 'Mai', 6: 'Jun',
            7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Okt', 11: 'Nov', 12: 'Dez'
        }
        monthly_stats = []
        for (year, month), md in sorted(month_data.items()):
            total_hours = md['total_hours']
            neg_hours = (
                md['buckets']['deeply_negative'] +
                md['buckets']['negative'] +
                md['buckets']['near_zero_neg']
            )
            spreads = md['daily_spreads']
            avg_price = md['price_sum'] / total_hours if total_hours > 0 else 0.0
            dl_hours = md['daylight_hours']
            dl_neg_hours = md['daylight_neg_hours']
            monthly_stats.append({
                'year': year,
                'month': month,
                'label': f"{month_labels[month]} {year}",
                'days_analyzed': md['days'],
                'negative_days': md['negative_days'],
                'total_hours': round(total_hours, 2),
                'avg_price': round(avg_price, 2),
                'avg_daily_spread': round(sum(spreads) / len(spreads), 2) if spreads else 0.0,
                'max_daily_spread': round(max(spreads), 2) if spreads else 0.0,
                'buckets': {k: round(v, 2) for k, v in md['buckets'].items()},
                'negative_hours': round(neg_hours, 2),
                'negative_pct': round(neg_hours / total_hours * 100, 2) if total_hours > 0 else 0.0,
                'daylight_hours': round(dl_hours, 2),
                'daylight_negative_hours': round(dl_neg_hours, 2),
                'daylight_negative_pct': round(dl_neg_hours / dl_hours * 100, 2) if dl_hours > 0 else 0.0,
            })

        # Build yearly_stats list
        year_data: Dict = {}
        for ms in monthly_stats:
            y = ms['year']
            if y not in year_data:
                year_data[y] = {
                    'months': 0,
                    'total_hours': 0.0,
                    'daylight_hours': 0.0,
                    'daylight_neg_hours': 0.0,
                    'price_sum': 0.0,
                    'spread_sum': 0.0,
                    'buckets': {
                        'deeply_negative': 0.0,
                        'negative': 0.0,
                        'near_zero_neg': 0.0,
                        'near_zero_pos': 0.0,
                        'normal': 0.0,
                    }
                }
            yd = year_data[y]
            yd['months'] += 1
            yd['total_hours'] += ms['total_hours']
            yd['daylight_hours'] += ms['daylight_hours']
            yd['daylight_neg_hours'] += ms['daylight_negative_hours']
            yd['price_sum'] += ms['avg_price'] * ms['total_hours']
            yd['spread_sum'] += ms['avg_daily_spread']
            for bk, bv in ms['buckets'].items():
                yd['buckets'][bk] += bv

        yearly_stats = []
        for year, yd in sorted(year_data.items()):
            th = yd['total_hours']
            dl_h = yd['daylight_hours']
            dl_neg = yd['daylight_neg_hours']
            neg_hours = (
                yd['buckets']['deeply_negative'] +
                yd['buckets']['negative'] +
                yd['buckets']['near_zero_neg']
            )
            yearly_stats.append({
                'year': year,
                'months_analyzed': yd['months'],
                'total_hours': round(th, 2),
                'avg_price': round(yd['price_sum'] / th, 2) if th > 0 else 0.0,
                'avg_daily_spread': round(yd['spread_sum'] / yd['months'], 2) if yd['months'] > 0 else 0.0,
                'buckets': {k: round(v, 2) for k, v in yd['buckets'].items()},
                'negative_hours': round(neg_hours, 2),
                'negative_pct': round(neg_hours / th * 100, 2) if th > 0 else 0.0,
                'daylight_hours': round(dl_h, 2),
                'daylight_negative_hours': round(dl_neg, 2),
                'daylight_negative_pct': round(dl_neg / dl_h * 100, 2) if dl_h > 0 else 0.0,
            })

        output = {
            'generated_at': datetime.now(ZoneInfo('Europe/Berlin')).isoformat(),
            'monthly_stats': monthly_stats,
            'yearly_stats': yearly_stats,
        }

        output_file = self.output_dir / 'history_view.json'
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)

        # Copy HTML template
        template_path = Path(__file__).parent.parent / 'web' / 'history.html'
        if template_path.exists():
            shutil.copy2(template_path, self.output_dir / 'history.html')

        return str(output_file)

    def generate_nachbarschaft_status(self) -> Dict:
        """Generate status payload for nachbarschaftsstrom repo.

        Covers the last 7 days plus tomorrow if prices are already cached
        (they are fetched in the afternoon of the previous day).
        """
        tz = ZoneInfo('Europe/Berlin')
        today = datetime.now(tz).date()

        def _day_entry(date_str: str) -> Dict:
            result = self.analyzer.analyze_day(date_str)
            if not result:
                return {'date': date_str, 'active': False, 'windows': []}
            windows = [
                f"{datetime.fromisoformat(p['start']).strftime('%H:%M')}–"
                f"{datetime.fromisoformat(p['end']).strftime('%H:%M')}"
                for p in result['periods']
            ]
            return {'date': date_str, 'active': bool(windows), 'windows': windows}

        days = [_day_entry((today - timedelta(days=i)).strftime('%Y-%m-%d')) for i in range(6, -1, -1)]

        # Include tomorrow when prices have already been fetched (afternoon of today).
        tomorrow_str = (today + timedelta(days=1)).strftime('%Y-%m-%d')
        if self.analyzer.analyze_day(tomorrow_str) is not None:
            days.append(_day_entry(tomorrow_str))

        return {
            'updated_at': datetime.now(tz).isoformat(),
            'days': days,
        }

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

        print("Generating history view...")
        self.generate_history_view()

        result = {
            'files': {
                'summary': 'summary.json',
                'periods': 'periods.json',
                'monthly_count': len(monthly_files),
                'csv_files': [f'{current_year}.csv'],
                'daily_view': 'daily_view.json',
                'web_dashboard': 'index.html',
                'history_view': 'history_view.json',
                'history_html': 'history.html',
            },
            'output_directory': str(self.output_dir)
        }

        print(f"\n✓ Generated {len(monthly_files) + 7} files in {self.output_dir}")
        return result

