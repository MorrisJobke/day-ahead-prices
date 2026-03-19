# EEG § 51 Day-Ahead Price Analysis Tool

A Python tool to analyze German day-ahead electricity prices and determine when § 51 EEG applies, calculating compensation period extensions according to § 51a EEG.

## Overview

This tool:
- Fetches quarter-hour day-ahead electricity prices from the Energy-Charts API
- Identifies periods with negative prices (when § 51 EEG applies)
- Calculates compensation period extensions per § 51a EEG
- Generates static JSON/CSV files for analysis
- **Correlates own PV generation with negative-price windows** via HomeAssistant

## Legal Background

### § 51 EEG - Reduction of Remuneration
According to § 51 EEG 2023, remuneration is reduced during periods when the day-ahead spot market price is negative.

**Key points:**
- For installations commissioned on or after February 25, 2025: remuneration is reduced from the first negative quarter-hour
- The regulation applies differently based on installation date and size

### § 51a EEG - Extension of Compensation Period
According to § 51a EEG, the compensation period (normally 20 years) is extended by the amount of time lost due to negative prices.

**Key points:**
- The standard 20-year compensation period is extended by the accumulated negative hours
- PV installations have a special mechanism that distributes compensation over months after the 20-year period (§ 51a Abs. 2)

**References:**
- [Clearingstelle EEG/KWKG - FAQ 264](https://www.clearingstelle-eeg-kwkg.de/haeufige-rechtsfrage/264)
- [EEG 2023 § 51](https://www.gesetze-im-internet.de/eeg_2023/__51.html)
- [EEG 2023 § 51a](https://www.gesetze-im-internet.de/eeg_2023/__51a.html)

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd day-ahead-prices
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Install as a package:
```bash
pip install -e .
```

## Usage

### Fetch Price Data

Fetch price data for a date range (data is cached locally):

```bash
# Fetch from config start date to today
python -m src.cli fetch

# Fetch specific date range
python -m src.cli fetch --start-date 2025-01-01 --end-date 2025-01-31
```

### Analyze Data

Analyze price data:

```bash
# Analyze all available data
python -m src.cli analyze

# Analyze specific date
python -m src.cli analyze 2025-01-15
```

### Generate Output Files

Generate static JSON and CSV files for analysis:

```bash
python -m src.cli generate
```

This creates:
- `output/summary.json` - Overall statistics
- `output/periods.json` - All negative price periods
- `output/YYYY-MM.json` - Monthly detailed data
- `output/YYYY.csv` - Annual CSV for spreadsheet analysis

### Update Data

Fetch latest data and regenerate outputs:

```bash
python -m src.cli update
```

### Serve Output Files

Start a simple HTTP server to serve output files:

```bash
python -m src.cli serve --port 8000
```

Access files at `http://localhost:8000`

### PV Generation vs. Negative-Price Windows

Correlates your own PV generation data (fetched from HomeAssistant) with negative-price periods to show how many kWh you produced during § 51 EEG windows, broken down by month.

**Setup** — add your HomeAssistant details to `config.yaml`:

```yaml
homeassistant:
  url: "http://homeassistant.local:8123"
  token: "<long-lived-access-token>"   # HA → Profile → Security → Create Token
  pv_entity: "sensor.pv_gesamtenergieertrag"  # cumulative kWh sensor
  pv_start_date: "2025-09-09"          # first day with PV data
```

**Fetch PV data** (fetches once, then caches in `data/pv/`):

```bash
python -m src.cli pv fetch
```

**Generate analysis and dashboard page:**

```bash
python -m src.cli pv generate
```

This creates:
- `output/pv_analysis.json` — monthly breakdown of total vs. affected generation
- `output/pv_history.html` — web dashboard with stacked bar chart and table

Then open `http://localhost:8000/pv_history.html` after `eeg serve`.

**Notes:**
- HomeAssistant provides 5-minute statistics for the most recent ~3 months; older data is automatically retrieved at hourly resolution
- Run `eeg pv fetch && eeg pv generate` alongside `eeg update` to keep data current

### Calculate Compensation Extension

Calculate compensation period extension for a specific installation:

```bash
python -m src.cli calculate 2025-03-01
```

## Configuration

Edit `config.yaml` to customize:

```yaml
api:
  base_url: "https://api.energy-charts.info"
  endpoint: "/price"
  country: "DE"
  timeout: 30

dates:
  start_date: "2025-01-01"
  timezone: "Europe/Berlin"

eeg:
  rule_start_date: "2025-02-25"
  compensation_period_years: 20

homeassistant:
  url: "http://homeassistant.local:8123"
  token: ""                               # Long-Lived Access Token
  pv_entity: "sensor.pv_gesamtenergieertrag"
  pv_start_date: "2025-09-09"
```

## Project Structure

```
day-ahead-prices/
├── src/
│   ├── cli.py              # CLI interface
│   ├── data_fetcher.py     # Price API integration and caching
│   ├── analyzer.py         # Price analysis
│   ├── compensation.py     # § 51a EEG calculations
│   ├── output_generator.py # File generation
│   ├── pv_fetcher.py       # HomeAssistant PV data via WebSocket
│   ├── pv_analyzer.py      # PV vs. negative-price correlation
│   └── utils.py            # Utilities
├── data/
│   ├── raw/                # Cached price API responses
│   └── pv/                 # Cached PV generation data (per day)
├── output/                 # Generated files
├── web/
│   ├── index.html          # Daily price dashboard template
│   ├── history.html        # Price history dashboard
│   └── pv_history.html     # PV vs. negative-price dashboard
├── tests/                  # Unit tests
├── config.yaml             # Configuration
└── requirements.txt        # Dependencies
```

## API Reference

### DataFetcher

Fetches and caches day-ahead electricity prices.

```python
from src.data_fetcher import DataFetcher

fetcher = DataFetcher()
fetcher.fetch_date_range("2025-01-01", "2025-01-31")
```

### PriceAnalyzer

Analyzes price data to identify negative periods.

```python
from src.analyzer import PriceAnalyzer

analyzer = PriceAnalyzer()
result = analyzer.analyze_day("2025-01-15")
```

### CompensationCalculator

Calculates compensation period extensions.

```python
from src.compensation import CompensationCalculator

calc = CompensationCalculator()
result = calc.calculate_for_installation("2025-03-01")
```

## Data Sources

- **Energy-Charts API**: Day-ahead electricity prices
  - API: https://api.energy-charts.info
  - Documentation: https://api.energy-charts.info/#/
  - **Note**: The API currently returns only current day prices, regardless of the date parameter. Historical data for specific dates may not be available through this endpoint.

## Limitations

- Currently analyzes data from 2025 onwards
- Focuses on quarter-hour price intervals
- Simplified implementation of PV-specific extension mechanism

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

[Specify your license here]

## Disclaimer

This tool is provided for informational purposes only. It is not a substitute for professional legal or financial advice. Always consult qualified professionals for decisions regarding EEG compensation and legal matters.

