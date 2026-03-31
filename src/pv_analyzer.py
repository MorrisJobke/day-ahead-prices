"""Correlates PV generation data with negative price windows."""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from src.analyzer import PriceAnalyzer
from src.pv_fetcher import PVFetcher
from src.utils import load_config


class PVAnalyzer:
    """Calculates PV generation that fell within negative-price windows."""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or load_config()
        self.price_analyzer = PriceAnalyzer(config)
        self.pv_fetcher = PVFetcher(config)
        ha = self.config.get('homeassistant', {})
        grid_entity = ha.get('grid_export_entity', '')
        self.grid_fetcher = PVFetcher(config, entity_id=grid_entity, cache_dir='data/grid') if grid_entity else None

    @staticmethod
    def _find_meter_reading(sum_readings: List[Dict], ts: int) -> Optional[float]:
        """Return the last meter reading (kWh) at or before ts, or None."""
        result = None
        for r in sum_readings:
            if r['unix_seconds'] <= ts:
                result = r['sum_kwh']
            else:
                break
        return result

    def _negative_slot_set(self, periods: List[Dict], resolution_hours: float) -> set:
        """Return set of 15-min slot unix_seconds that are inside negative price windows."""
        slot_duration = int(resolution_hours * 3600)  # 900 or 3600
        negative_slots = set()
        for period in periods:
            start_ts = int(datetime.fromisoformat(period['start']).timestamp())
            end_ts = int(datetime.fromisoformat(period['end']).timestamp())
            # Align to price slot boundaries, then enumerate all 15-min PV sub-slots
            slot_start = (start_ts // slot_duration) * slot_duration
            while slot_start <= end_ts:
                # Emit all 15-min PV slots within this price slot
                pv_slot = slot_start
                pv_end = slot_start + slot_duration
                while pv_slot < pv_end:
                    negative_slots.add(pv_slot)
                    pv_slot += 900
                slot_start += slot_duration
        return negative_slots

    def analyze_day(self, date: str) -> Optional[Dict]:
        """Compute PV overlap with negative prices for one day."""
        pv_data = self.pv_fetcher.load_cached_data(date)
        if not pv_data:
            return None

        total_wh = pv_data.get('total_wh', 0.0)

        day_result = self.price_analyzer.analyze_day(date)
        if not day_result or not day_result.get('periods'):
            result = {
                'date': date,
                'total_wh': total_wh,
                'negative_window_wh': 0.0,
            }
            grid_data = self.grid_fetcher.load_cached_data(date) if self.grid_fetcher else None
            if grid_data:
                result['grid_export_wh'] = round(grid_data.get('total_wh', 0.0), 2)
                result['grid_export_negative_wh'] = 0.0
            return result

        resolution_hours = 0.25 if day_result['resolution'] == 'quarter_hourly' else 1.0
        grid_data = self.grid_fetcher.load_cached_data(date) if self.grid_fetcher else None

        pv_sum_readings = pv_data.get('sum_readings', [])
        grid_sum_readings = grid_data.get('sum_readings', []) if grid_data else []

        windows = []
        for period in day_result['periods']:
            period_slots = self._negative_slot_set([period], resolution_hours)
            start_ts = int(datetime.fromisoformat(period['start']).timestamp())
            end_ts = int(datetime.fromisoformat(period['end']).timestamp())

            m0 = self._find_meter_reading(pv_sum_readings, start_ts) if pv_sum_readings else None
            m1 = self._find_meter_reading(pv_sum_readings, end_ts) if pv_sum_readings else None

            if m0 is not None and m1 is not None:
                period_pv_wh = max(0.0, (m1 - m0) * 1000)
            else:
                period_pv_wh = sum(
                    slot['wh'] for slot in pv_data['slots'] if slot['unix_seconds'] in period_slots
                )

            window = {
                'start': period['start'],
                'end': period['end'],
                'pv_wh': round(period_pv_wh, 2),
            }
            if m0 is not None and m1 is not None:
                window['meter_start_kwh'] = m0
                window['meter_end_kwh'] = m1
            if grid_data:
                gm0 = self._find_meter_reading(grid_sum_readings, start_ts) if grid_sum_readings else None
                gm1 = self._find_meter_reading(grid_sum_readings, end_ts) if grid_sum_readings else None
                if gm0 is not None and gm1 is not None:
                    period_grid_wh = max(0.0, (gm1 - gm0) * 1000)
                    window['grid_meter_start_kwh'] = gm0
                    window['grid_meter_end_kwh'] = gm1
                else:
                    period_grid_wh = sum(
                        slot['wh'] for slot in grid_data['slots'] if slot['unix_seconds'] in period_slots
                    )
                window['grid_export_wh'] = round(period_grid_wh, 2)
            windows.append(window)

        negative_wh = sum(w['pv_wh'] for w in windows)

        result = {
            'date': date,
            'total_wh': round(total_wh, 2),
            'negative_window_wh': round(negative_wh, 2),
            'windows': windows,
        }

        if grid_data:
            grid_export_negative_wh = sum(w.get('grid_export_wh', 0.0) for w in windows)
            result['grid_export_wh'] = round(grid_data.get('total_wh', 0.0), 2)
            result['grid_export_negative_wh'] = round(grid_export_negative_wh, 2)

        return result

    def analyze_month(self, year: int, month: int) -> Dict:
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)

        total_wh = 0.0
        negative_wh = 0.0
        days_with_data = 0
        daily = []
        grid_export_wh = 0.0
        grid_export_negative_wh = 0.0
        has_grid_data = False

        current = start
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            result = self.analyze_day(date_str)
            if result:
                total_wh += result['total_wh']
                negative_wh += result['negative_window_wh']
                days_with_data += 1
                daily.append(result)
                if 'grid_export_wh' in result:
                    grid_export_wh += result['grid_export_wh']
                    grid_export_negative_wh += result['grid_export_negative_wh']
                    has_grid_data = True
            current += timedelta(days=1)

        total_kwh = round(total_wh / 1000, 3)
        negative_kwh = round(negative_wh / 1000, 3)
        pct = round(negative_kwh / total_kwh * 100, 1) if total_kwh > 0 else 0.0

        month_result = {
            'year': year,
            'month': month,
            'label': datetime(year, month, 1).strftime('%b %Y'),
            'total_kwh': total_kwh,
            'negative_window_kwh': negative_kwh,
            'negative_window_pct': pct,
            'days_with_data': days_with_data,
            'daily': daily,
        }

        if has_grid_data:
            grid_neg_kwh = round(grid_export_negative_wh / 1000, 3)
            month_result['grid_export_kwh'] = round(grid_export_wh / 1000, 3)
            month_result['grid_export_negative_kwh'] = grid_neg_kwh
            month_result['grid_export_negative_pct'] = (
                round(grid_neg_kwh / total_kwh * 100, 1) if total_kwh > 0 else 0.0
            )

        return month_result

    def analyze_all(self) -> Dict:
        """Aggregate monthly stats across all dates with both price and PV data."""
        pv_dates = set(self.pv_fetcher.get_cached_dates())
        price_dates = set(self.price_analyzer.fetcher.get_cached_dates())
        common_dates = sorted(pv_dates & price_dates)

        if not common_dates:
            return {'months': [], 'total_kwh': 0.0, 'total_negative_window_kwh': 0.0, 'total_negative_window_pct': 0.0}

        # Determine month range
        first = datetime.strptime(common_dates[0], '%Y-%m-%d')
        last = datetime.strptime(common_dates[-1], '%Y-%m-%d')

        months = []
        current = first.replace(day=1)
        while current <= last:
            result = self.analyze_month(current.year, current.month)
            if result['days_with_data'] > 0:
                months.append(result)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        total_kwh = round(sum(m['total_kwh'] for m in months), 3)
        total_neg_kwh = round(sum(m['negative_window_kwh'] for m in months), 3)
        total_pct = round(total_neg_kwh / total_kwh * 100, 1) if total_kwh > 0 else 0.0

        result = {
            'generated': datetime.now(ZoneInfo('Europe/Berlin')).isoformat(),
            'months': months,
            'total_kwh': total_kwh,
            'total_negative_window_kwh': total_neg_kwh,
            'total_negative_window_pct': total_pct,
        }

        grid_months = [m for m in months if 'grid_export_negative_kwh' in m]
        if grid_months:
            total_grid_neg_kwh = round(sum(m['grid_export_negative_kwh'] for m in grid_months), 3)
            result['total_grid_export_negative_kwh'] = total_grid_neg_kwh
            result['total_grid_export_negative_pct'] = (
                round(total_grid_neg_kwh / total_kwh * 100, 1) if total_kwh > 0 else 0.0
            )

        return result
