"""Command-line interface for EEG price analysis tool."""
import os
import sys
from datetime import datetime
from pathlib import Path

import click

from src.data_fetcher import DataFetcher
from src.analyzer import PriceAnalyzer
from src.output_generator import OutputGenerator
from src.utils import load_config


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """EEG §51 Day-Ahead Price Analysis Tool."""
    pass


@cli.command()
@click.option('--start-date', default=None, help='Start date (YYYY-MM-DD)')
@click.option('--end-date', default=None, help='End date (YYYY-MM-DD)')
def fetch(start_date, end_date):
    """Fetch and cache price data."""
    fetcher = DataFetcher()
    
    if not start_date:
        config = load_config()
        start_date = config['dates']['start_date']
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    click.echo(f"Fetching data from {start_date} to {end_date}...")
    fetched = fetcher.fetch_date_range(start_date, end_date)
    click.echo(f"✓ Successfully fetched {len(fetched)} days")


@cli.command()
@click.argument('date', required=False)
def analyze(date):
    """Analyze price data for a specific date or all dates."""
    analyzer = PriceAnalyzer()
    
    if not date:
        # Analyze all available data
        dates = analyzer.fetcher.get_cached_dates()
        if not dates:
            click.echo("No data available. Run 'eeg fetch' first.")
            sys.exit(1)
        
        click.echo(f"Analyzing {len(dates)} days...")
        all_periods = analyzer.get_all_negative_periods()
        total_negative = sum(p['duration_quarters'] for p in all_periods)
        
        click.echo(f"\nResults:")
        click.echo(f"  Total days analyzed: {len(dates)}")
        click.echo(f"  Negative periods: {len(all_periods)}")
        click.echo(f"  Total negative quarters: {total_negative}")
        click.echo(f"  Total negative hours: {total_negative * 0.25:.2f}")
    else:
        result = analyzer.analyze_day(date)
        if not result:
            click.echo(f"No data for {date}")
            sys.exit(1)
        
        click.echo(f"\nAnalysis for {date}:")
        click.echo(f"  Negative quarters: {result['negative_quarters']}")
        click.echo(f"  Negative hours: {result['negative_hours']:.2f}")
        click.echo(f"  Negative periods: {len(result['periods'])}")
        click.echo(f"  Min price: {result['min_price']:.2f} EUR/MWh")
        click.echo(f"  Max price: {result['max_price']:.2f} EUR/MWh")


@cli.command()
def generate():
    """Generate all output files."""
    generator = OutputGenerator()
    result = generator.generate_all()
    
    click.echo(f"\n✓ Output files generated in: {result['output_directory']}")
    click.echo(f"\nGenerated files:")
    click.echo(f"  - summary.json")
    click.echo(f"  - periods.json")
    click.echo(f"  - {result['files']['monthly_count']} monthly files")
    click.echo(f"  - {len(result['files']['csv_files'])} CSV file(s)")


@cli.command()
def update():
    """Fetch latest data and regenerate outputs."""
    config = load_config()
    fetcher = DataFetcher()
    
    # Fetch latest data
    start_date = config['dates']['start_date']
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    click.echo("Updating data...")
    fetched = fetcher.fetch_date_range(start_date, end_date)
    click.echo(f"✓ Updated {len(fetched)} days")
    
    # Regenerate outputs
    click.echo("\nRegenerating output files...")
    generator = OutputGenerator()
    generator.generate_all()
    
    click.echo("✓ Update complete")


@cli.command()
@click.option('--port', default=8000, help='Port number')
@click.option('--bind', default='localhost', help='Bind address')
def serve(port, bind):
    """Start a simple HTTP server to serve output files."""
    import http.server
    import socketserver
    
    output_dir = Path(load_config()['output']['directory'])
    
    if not output_dir.exists():
        click.echo(f"Output directory not found: {output_dir}")
        click.echo("Run 'eeg generate' first to create output files.")
        sys.exit(1)
    
    os.chdir(output_dir)
    
    Handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer((bind, port), Handler)
    
    click.echo(f"Serving files from {output_dir} at http://{bind}:{port}")
    click.echo("Press CTRL+C to stop")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nServer stopped")


@cli.command()
@click.argument('installation_date')
@click.option('--start-date', default=None)
@click.option('--end-date', default=None)
def calculate(installation_date, start_date, end_date):
    """Calculate compensation period extension for an installation."""
    from src.compensation import CompensationCalculator
    
    calc = CompensationCalculator()
    result = calc.calculate_for_installation(installation_date, start_date, end_date)
    
    click.echo(f"\nCompensation Calculation for Installation:")
    click.echo(f"  Installation date: {result['installation_date']}")
    click.echo(f"  Analysis period: {result['analysis_period']['start']} to {result['analysis_period']['end']}")
    click.echo(f"\nNegative Price Impact:")
    click.echo(f"  Total periods: {result['negative_periods_count']}")
    click.echo(f"  Negative quarters: {result['total_negative_quarters']}")
    click.echo(f"  Negative hours: {result['total_negative_hours']:.2f}")
    
    ext = result['extension']
    click.echo(f"\nCompensation Period Extension:")
    click.echo(f"  Original end date: {ext['original_end_date']}")
    click.echo(f"  Extended end date: {ext['extended_end_date']}")
    click.echo(f"  Extension: {ext['extension_days']} days")


if __name__ == '__main__':
    cli()
