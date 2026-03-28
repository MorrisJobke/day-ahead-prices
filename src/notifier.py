"""Telegram notification module for negative day-ahead price alerts."""
from datetime import datetime, timezone
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

import requests

from src.utils import load_config, sunrise_sunset_utc


TZ_BERLIN = ZoneInfo('Europe/Berlin')


def _filter_daytime_periods(periods: List[Dict], sunrise_ts: float, sunset_ts: float) -> List[Dict]:
    """Keep only periods that overlap with the sunrise–sunset window."""
    result = []
    for p in periods:
        start_ts = datetime.fromisoformat(p['start']).timestamp()
        end_ts = datetime.fromisoformat(p['end']).timestamp()
        if start_ts < sunset_ts and end_ts > sunrise_ts:
            result.append(p)
    return result


def format_message(date: str, periods: List[Dict], lat: float, lng: float) -> Optional[str]:
    """Format a Telegram message for the given date and negative periods.

    Filters to daylight hours (sunrise–sunset) for the given coordinates.
    Returns None if there are no negative periods during daylight.
    """
    sunrise_ts, sunset_ts = sunrise_sunset_utc(date, lat, lng)

    if sunrise_ts is None:
        # Polar night — no solar generation anyway
        return None

    daytime_periods = _filter_daytime_periods(periods, sunrise_ts, sunset_ts)
    if not daytime_periods:
        return None

    sunrise_dt = datetime.fromtimestamp(sunrise_ts, tz=TZ_BERLIN)
    sunset_dt = datetime.fromtimestamp(sunset_ts, tz=TZ_BERLIN)

    date_dt = datetime.strptime(date, '%Y-%m-%d')
    date_formatted = date_dt.strftime('%d.%m.%Y')
    weekday = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'][date_dt.weekday()]

    total_hours = sum(p['duration_hours'] for p in daytime_periods)

    lines = [
        f"⚡ Negative Strompreise morgen ({weekday}, {date_formatted})",
        "",
        f"Tageszeitraum: {sunrise_dt.strftime('%H:%M')}–{sunset_dt.strftime('%H:%M')} Uhr",
        "",
        "Negative Preiszeiträume tagsüber:",
    ]

    for p in daytime_periods:
        start_dt = datetime.fromisoformat(p['start']).astimezone(TZ_BERLIN)
        end_dt = datetime.fromisoformat(p['end']).astimezone(TZ_BERLIN)
        hours = p['duration_hours']
        min_price = p['min_price']
        lines.append(f"  • {start_dt.strftime('%H:%M')}–{end_dt.strftime('%H:%M')} Uhr ({hours:.2g}h, min. {min_price:.0f} €/MWh)")

    lines.append("")
    lines.append(f"Gesamt: {total_hours:.2g}h negativer Preis tagsüber")

    return "\n".join(lines)


def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Send a message via the Telegram Bot API. Returns True on success."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    resp.raise_for_status()
    return resp.json().get('ok', False)


def check_and_notify(date: str, config: Optional[Dict] = None) -> Dict:
    """Check prices for `date` and send Telegram alert if negative daylight prices exist."""
    if config is None:
        config = load_config()

    tg = config.get('telegram', {})
    token = tg.get('bot_token', '')
    chat_id = tg.get('chat_id', '')

    if not token or not chat_id:
        return {'sent': False, 'message': None, 'periods': [],
                'error': 'telegram.bot_token or telegram.chat_id not configured'}

    lat = config['location']['lat']
    lng = config['location']['lng']

    from src.analyzer import PriceAnalyzer
    result = PriceAnalyzer(config).analyze_day(date)

    if result is None:
        return {'sent': False, 'message': None, 'periods': [], 'error': f'No data for {date}'}

    message = format_message(date, result['periods'], lat, lng)

    if message is None:
        return {'sent': False, 'message': None, 'periods': result['periods'], 'error': None}

    send_telegram_message(token, chat_id, message)
    return {'sent': True, 'message': message, 'periods': result['periods'], 'error': None}
