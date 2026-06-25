"""Fetches PV generation data from HomeAssistant via WebSocket statistics API."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import websocket

from src.utils import load_config, ensure_dir


class PVFetcher:
    """Fetches and caches PV generation data from HomeAssistant."""

    def __init__(self, config: Optional[Dict] = None, entity_id: Optional[str] = None, cache_dir: Optional[str] = None):
        self.config = config or load_config()
        ha = self.config.get('homeassistant', {})
        self.ha_url = ha.get('url', 'http://homeassistant.local:8123').rstrip('/')
        self.ha_token = ha.get('token', '')
        self.entity_id = entity_id or ha.get('pv_entity', '')
        self.pv_start_date = ha.get('pv_start_date', '2025-09-09')
        self.cache_dir = Path(cache_dir or 'data/pv')
        ensure_dir(self.cache_dir)

    def _ws_statistics(self, start_dt: datetime, end_dt: datetime, period: str = '5minute') -> List[Dict]:
        """Fetch long-term statistics via HA WebSocket API.

        The recorder/statistics_during_period command is only available via
        WebSocket, not the REST API. Short-term 5-min stats are kept ~1 year.
        """
        ws_url = self.ha_url.replace('http://', 'ws://').replace('https://', 'wss://') + '/api/websocket'
        ws = websocket.create_connection(ws_url, timeout=30)
        try:
            msg = json.loads(ws.recv())  # auth_required
            if msg.get('type') != 'auth_required':
                raise RuntimeError(f"Expected auth_required, got: {msg.get('type')}")

            ws.send(json.dumps({'type': 'auth', 'access_token': self.ha_token}))
            msg = json.loads(ws.recv())  # auth_ok / auth_invalid
            if msg.get('type') != 'auth_ok':
                raise RuntimeError(f"HA auth failed: {msg.get('message', msg.get('type'))}")

            ws.send(json.dumps({
                'id': 1,
                'type': 'recorder/statistics_during_period',
                'start_time': start_dt.isoformat(),
                'end_time': end_dt.isoformat(),
                'statistic_ids': [self.entity_id],
                'period': period,
                'types': ['sum'],
            }))
            result = json.loads(ws.recv())
            if not result.get('success'):
                raise RuntimeError(f"Statistics request failed: {result.get('error', result)}")

            return result['result'].get(self.entity_id, [])
        finally:
            ws.close()

    def _stats_to_slots(
        self,
        stats: List[Dict],
        day_start_ts: float,
        day_end_ts: float,
        period_seconds: int,
    ) -> Dict[int, float]:
        """Convert sorted (start, sum) stats entries into {slot_ts: wh} dict."""
        slots: Dict[int, float] = {}
        prev_sum = None
        for entry in stats:
            cur_sum = entry.get('sum')
            if cur_sum is None:
                prev_sum = None
                continue
            if prev_sum is not None:
                delta_wh = max(0.0, cur_sum - prev_sum) * 1000.0
                entry_ts = entry['start']
                if period_seconds <= 900:
                    slot_start = int(entry_ts // 900) * 900
                    if day_start_ts <= slot_start < day_end_ts:
                        slots[slot_start] = slots.get(slot_start, 0.0) + delta_wh
                else:
                    sub_slots = period_seconds // 900
                    wh_per_sub = delta_wh / sub_slots
                    for i in range(sub_slots):
                        slot_start = int(entry_ts // 900) * 900 + i * 900
                        if day_start_ts <= slot_start < day_end_ts:
                            slots[slot_start] = slots.get(slot_start, 0.0) + wh_per_sub
            prev_sum = cur_sum
        return slots

    def _fetch_from_ha(self, date: str) -> Optional[Dict]:
        """Fetch HA statistics for one day and aggregate to 15-min slots.

        Always fetches both 5-minute and hourly statistics. 5-min data is used
        where available. For hours with no 5-min coverage (e.g. after a sensor
        outage backfilled via hourly import_statistics), the hourly delta is
        distributed evenly across four 15-min sub-slots.
        """
        tz = ZoneInfo('Europe/Berlin')
        day_start = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        fetch_start_5m = day_start - timedelta(minutes=5)
        fetch_start_1h = day_start - timedelta(hours=1)

        try:
            stats_5m = self._ws_statistics(fetch_start_5m, day_end, period='5minute')
            stats_1h = self._ws_statistics(fetch_start_1h, day_end, period='hour')
        except RuntimeError as e:
            raise RuntimeError(f"HA request failed for {date}: {e}") from e

        if not stats_5m and not stats_1h:
            return {'date': date, 'entity_id': self.entity_id, 'slots': [], 'total_wh': 0.0}

        # HA returns timestamps in milliseconds — convert to seconds
        for entry in stats_5m + stats_1h:
            entry['start'] = float(entry['start']) / 1000.0

        stats_5m.sort(key=lambda x: x['start'])
        stats_1h.sort(key=lambda x: x['start'])

        day_start_ts = day_start.timestamp()
        day_end_ts   = day_end.timestamp()

        # Build 15-min slots from 5-minute data
        slots = self._stats_to_slots(stats_5m, day_start_ts, day_end_ts, 300)

        # Build hourly reference (already per-sub-slot: delta/4 per 15-min)
        hourly_slots = self._stats_to_slots(stats_1h, day_start_ts, day_end_ts, 3600)

        # Fill slots missing from 5-min data using hourly reference
        for slot_ts, hourly_wh in hourly_slots.items():
            if slot_ts not in slots:
                slots[slot_ts] = hourly_wh

        # Replace spike artifacts: single 5-min slots >3× their hourly reference
        # (caused by sensor reconnection recording accumulated gap production at once)
        for slot_ts in list(slots.keys()):
            hourly_wh = hourly_slots.get(slot_ts, 0.0)
            if hourly_wh > 0 and slots[slot_ts] > hourly_wh * 3:
                slots[slot_ts] = hourly_wh

        sum_readings = [
            {'unix_seconds': int(e['start']), 'sum_kwh': round(e['sum'], 3)}
            for e in stats_5m + stats_1h if e.get('sum') is not None
        ]
        sum_readings.sort(key=lambda x: x['unix_seconds'])

        slot_list = [
            {'unix_seconds': ts, 'wh': round(wh, 2)}
            for ts, wh in sorted(slots.items())
        ]
        total_wh = round(sum(s['wh'] for s in slot_list), 2)
        return {
            'date': date,
            'entity_id': self.entity_id,
            'slots': slot_list,
            'total_wh': total_wh,
            'sum_readings': sum_readings,
        }

    def fetch_day(self, date: str, force: bool = False) -> Optional[Dict]:
        """Fetch PV statistics for one day. Returns cached data if available."""
        cache_file = self.cache_dir / f"{date}.json"
        if not force and cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)

        data = self._fetch_from_ha(date)
        if data is not None:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        return data

    def load_cached_data(self, date: str) -> Optional[Dict]:
        cache_file = self.cache_dir / f"{date}.json"
        if not cache_file.exists():
            return None
        with open(cache_file) as f:
            return json.load(f)

    def get_cached_dates(self) -> List[str]:
        return sorted(f.stem for f in self.cache_dir.glob('*.json'))

    def fetch_date_range(self, start_date: str, end_date: str, force: bool = False) -> List[str]:
        """Fetch all days in range, skipping already-cached dates unless force=True.

        The most-recently-cached date is always re-fetched because a previous
        mid-day run may have stored incomplete data for that day.
        """
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        today = datetime.now(ZoneInfo('Europe/Berlin')).date()
        fetched = []

        # Find the latest cached date in range so it can always be refreshed.
        latest_cached = None
        if not force:
            scan = current
            while scan.date() <= min(end.date(), today):
                date_str = scan.strftime('%Y-%m-%d')
                if (self.cache_dir / f"{date_str}.json").exists():
                    latest_cached = date_str
                scan += timedelta(days=1)

        while current.date() <= end.date():
            date_str = current.strftime('%Y-%m-%d')
            cache_file = self.cache_dir / f"{date_str}.json"
            # Skip future dates (no data yet); today is allowed (partial data is fine)
            if current.date() > today:
                current += timedelta(days=1)
                continue
            refresh = force or date_str == latest_cached
            if refresh or not cache_file.exists():
                data = self.fetch_day(date_str, force=refresh)
                if data is not None:
                    fetched.append(date_str)
            current += timedelta(days=1)

        return fetched
