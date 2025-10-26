# Quick Start Guide

## Installation

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

Or if you prefer a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Optional: Install as a package**
```bash
pip install -e .
```

This will enable the `eeg` command globally.

## Usage

### Basic Workflow

1. **Fetch price data from the Energy-Charts API:**
```bash
python3 -m src.cli fetch
```

This will fetch data from 2025-01-01 to today (as configured in `config.yaml`).

2. **Analyze the fetched data:**
```bash
python3 -m src.cli analyze
```

This analyzes all available data and shows summary statistics.

3. **Generate output files:**
```bash
python3 -m src.cli generate
```

This creates JSON and CSV files in the `output/` directory.

4. **Serve the output files via HTTP:**
```bash
python3 -m src.cli serve --port 8000
```

Then access http://localhost:8000 to view the generated files.

### Advanced Usage

**Fetch specific date range:**
```bash
python3 -m src.cli fetch --start-date 2025-01-01 --end-date 2025-12-31
```

**Analyze specific date:**
```bash
python3 -m src.cli analyze 2025-01-15
```

**Update data and regenerate outputs:**
```bash
python3 -m src.cli update
```

**Calculate compensation extension for an installation:**
```bash
python3 -m src.cli calculate 2025-03-01
```

## Output Files

The tool generates the following files in the `output/` directory:

- `summary.json` - Overall statistics and current year summary
- `periods.json` - All continuous negative price periods
- `YYYY-MM.json` - Monthly detailed data with all negative periods
- `YYYY.csv` - Annual CSV for spreadsheet analysis

## Configuration

Edit `config.yaml` to customize:
- API endpoints and parameters
- Cache directory paths
- Output formats
- Date ranges
- Timezone settings
- EEG rule start date

## Troubleshooting

**No data available error:**
- Make sure you've run `fetch` first
- Check your internet connection
- Verify the API endpoint in `config.yaml`

**Import errors:**
- Make sure you've installed requirements: `pip install -r requirements.txt`
- Check that you're using Python 3.8 or higher

## Next Steps

- Read the [README.md](README.md) for detailed documentation
- Check the configuration in `config.yaml`
- Review the generated output files in the `output/` directory
