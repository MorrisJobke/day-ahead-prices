<!-- 197d165a-0af6-48aa-ad61-226981d0318f 73a7aa73-2360-4a55-9c3d-94817fec5ac5 -->
# EEG § 51 Day-Ahead Price Analysis Tool

## Overview

Build a Python tool that:

1. Fetches quarter-hour day-ahead electricity prices from the Energy-Charts API
2. Identifies periods where § 51 EEG applies (negative prices from 2025 onwards)
3. Calculates compensation period extensions per § 51a EEG
4. Generates static JSON/CSV files for easy access
5. Provides a CLI interface for data processing

## Core Components

### 1. Data Fetching Module (`src/data_fetcher.py`)

- Integrate with Energy-Charts API endpoint: `https://api.energy-charts.info/price`
- Fetch quarter-hour day-ahead prices for Germany (DE)
- Implement caching mechanism:
  - Store historical data locally (won't change)
  - Fetch only new/missing data on updates
- Handle API rate limits and errors gracefully
- Save raw data in `data/raw/` as daily/monthly JSON files

### 2. Price Analysis Module (`src/analyzer.py`)

- Parse quarter-hour price data
- Identify negative price periods (§ 51 EEG applies from first negative quarter-hour for installations from Feb 25, 2025)
- Calculate:
  - Total negative quarter-hours per day/month/year
  - Cumulative negative periods for compensation extension
  - Statistics: frequency, duration patterns

### 3. Compensation Calculator (`src/compensation.py`)

- Implement § 51a EEG compensation period extension logic:
  - Track negative quarter-hours as "lost compensation time"
  - Calculate extension needed at end of 20-year period
  - Handle PV-specific monthly distribution mechanism (§ 51a Abs. 2)
- Generate reports showing:
  - Original 20-year compensation period
  - Total negative quarters accumulated
  - Extended period end date

### 4. Output Generator (`src/output_generator.py`)

- Generate static files in `output/` directory:
  - `summary.json`: Overall statistics and current year summary
  - `YYYY-MM.json`: Monthly detailed data with all negative periods
  - `YYYY.csv`: Annual CSV for spreadsheet analysis
  - `periods.json`: List of all continuous negative price periods
- Files can be served via simple HTTP server or CDN

### 5. CLI Interface (`src/cli.py`)

- Commands:
  - `fetch [start-date] [end-date]`: Fetch and cache price data
  - `analyze [year/month]`: Analyze specific period
  - `generate`: Generate all output files
  - `update`: Fetch latest data and regenerate outputs
  - `serve`: Start simple HTTP server for output files

## Project Structure

```
day-ahead-prices/
├── src/
│   ├── __init__.py
│   ├── cli.py
│   ├── data_fetcher.py
│   ├── analyzer.py
│   ├── compensation.py
│   └── output_generator.py
├── data/
│   ├── raw/          # Cached API responses
│   └── processed/    # Intermediate processed data
├── output/           # Generated static files
├── tests/
│   └── test_*.py
├── requirements.txt
├── README.md
└── config.yaml       # API endpoints, cache settings, etc.
```

## Implementation Details

### Data Model

- Store prices with ISO 8601 timestamps
- Track metadata: data source, fetch timestamp, API version
- Use pandas DataFrame for efficient processing

### Performance Optimizations

- Cache historical data (immutable after day passes)
- Use pandas for vectorized operations
- Parallel processing for multiple months/years
- Incremental updates (only process new data)

### Configuration (`config.yaml`)

- API endpoints and parameters
- Cache directory paths
- Output formats and destinations
- Date range for initial fetch
- Timezone settings (Europe/Berlin)

## Key Technical Considerations

1. **Timezone Handling**: Day-ahead prices are in CET/CEST; ensure proper timezone conversion
2. **Data Validation**: Verify price data completeness (96 quarter-hours per day)
3. **Missing Data**: Handle API outages or missing intervals gracefully
4. **Float Precision**: Use appropriate precision for price calculations (EUR/MWh)
5. **Date Boundaries**: Correctly handle period boundaries for compensation calculations

## Dependencies

- `requests`: API calls
- `pandas`: Data processing
- `pyyaml`: Configuration management
- `click`: CLI interface
- `python-dateutil`: Date handling
- `pytest`: Testing

## Deliverables

1. Fully functional Python package with CLI
2. Cached historical price data from 2025 onwards
3. Generated static files with analysis results
4. Documentation on usage and § 51/§ 51a EEG interpretation
5. Example queries and output interpretation guide

### To-dos

- [ ] Initialize project structure, create directories, setup requirements.txt and config.yaml
- [ ] Build data_fetcher.py to integrate with Energy-Charts API and implement caching
- [ ] Create analyzer.py to identify negative price periods and calculate statistics
- [ ] Develop compensation.py for § 51a EEG period extension calculations
- [ ] Build output_generator.py to create static JSON/CSV files
- [ ] Create CLI interface with commands for fetch, analyze, generate, and update
- [ ] Add tests, write README with usage examples and § 51 EEG interpretation guide