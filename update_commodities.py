#!/usr/bin/env python3
"""
update_commodities.py
================================================================================
Automatically fetches, processes, and updates Gold and Silver prices in INR:
- Gold: International futures proxy converted to INR per 10 grams (₹ / 10g)
- Silver: International futures proxy converted to INR per 1 kilogram (₹ / 1kg)
- Zero tax, customs duty, or cess (pure physical weight parity)
- Smart incremental update: only fetches new days if CSV already exists
- Can also export monthly series and optionally patch rolling_returns.html

Usage:
  python update_commodities.py              # Incremental update (or full if no file)
  python update_commodities.py --full       # Re-fetch full history from 2020-01-01
  python update_commodities.py --monthly    # Also export monthly month-end CSV
  python update_commodities.py --update-html # Also update rolling_returns.html
================================================================================
"""

import os
import sys
import json
import math
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# Standard physical weight constant (1 Troy Ounce = 31.1034768 grams)
TROY_OZ_TO_GRAMS = 31.1034768

# Default paths
DEFAULT_DOWNLOADS_CSV = Path.home() / "Downloads" / "gold_silver_inr_adjusted.csv"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LOCAL_CSV = SCRIPT_DIR / "gold_silver_inr_adjusted.csv"
HTML_PATH = SCRIPT_DIR / "rolling_returns.html"

TICKERS = ["GC=F", "SI=F", "INR=X"]
COLUMN_MAP = {"GC=F": "Gold_USD", "SI=F": "Silver_USD", "INR=X": "USD_INR"}


def fetch_raw_data(start_date: str, retries: int = 3) -> pd.DataFrame:
    """Download daily close prices for Gold, Silver, and USD/INR from Yahoo Finance."""
    print(f"📡 Fetching tickers {TICKERS} from {start_date}...")
    for attempt in range(1, retries + 1):
        try:
            df = yf.download(TICKERS, start=start_date, progress=False)["Close"]
            if isinstance(df.columns, pd.MultiIndex):
                df = df.droplevel(0, axis=1)
            df = df.rename(columns=COLUMN_MAP)
            
            # Ensure all 3 required columns are present
            missing = [col for col in COLUMN_MAP.values() if col not in df.columns]
            if missing:
                raise ValueError(f"Missing expected columns in downloaded data: {missing}")
            
            # Forward-fill any mismatched holiday dates and drop remaining NaNs
            df = df.ffill().dropna()
            if not df.empty:
                return df
        except Exception as e:
            print(f"  ⚠️ Attempt {attempt}/{retries} failed: {e}")
            if attempt == retries:
                raise

    raise RuntimeError("Failed to download commodity and FX data after multiple attempts.")


def calculate_pure_inr_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Apply zero-tax pure physical weight conversion formulas."""
    result = pd.DataFrame(index=df.index)
    result.index.name = "Date"

    # Gold: Futures proxy converted to INR per 10 grams (rounded to 2 decimal places)
    result["gold_inr_per_10g"] = (
        ((df["Gold_USD"] * df["USD_INR"]) / TROY_OZ_TO_GRAMS) * 10
    ).round(2)

    # Silver: Futures proxy converted to INR per 1 kilogram (1000g) (rounded to 2 decimal places)
    result["silver_inr_per_1kg"] = (
        ((df["Silver_USD"] * df["USD_INR"]) / TROY_OZ_TO_GRAMS) * 1000
    ).round(2)

    result.index = pd.to_datetime(result.index).strftime("%Y-%m-%d")
    return result


def load_existing_csv(csv_path: Path) -> pd.DataFrame:
    """Load existing CSV if present, returning an empty DataFrame otherwise."""
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, index_col="Date")
            df.index = df.index.astype(str)
            return df
        except Exception as e:
            print(f"  ⚠️ Could not read existing CSV at {csv_path}: {e}")
    return pd.DataFrame()


def update_dataset(full_mode: bool = False, start_override: str = None, custom_output: str = None) -> pd.DataFrame:
    """Main pipeline to download, calculate, and save updated commodity prices."""
    target_csv = Path(custom_output) if custom_output else DEFAULT_DOWNLOADS_CSV

    existing_df = pd.DataFrame()
    fetch_start = "2020-01-01"

    if start_override:
        fetch_start = start_override
    elif not full_mode and target_csv.exists():
        existing_df = load_existing_csv(target_csv)
        if not existing_df.empty:
            last_date_str = str(existing_df.index.max())
            try:
                # Go back 7 days from the latest saved date to handle any revisions or recent holidays
                last_dt = datetime.strptime(last_date_str, "%Y-%m-%d")
                fetch_start = (last_dt - timedelta(days=7)).strftime("%Y-%m-%d")
                print(f"🔄 Existing data found (latest: {last_date_str}). Updating from {fetch_start}...")
            except Exception:
                fetch_start = "2020-01-01"

    # Fetch and process
    raw_df = fetch_raw_data(fetch_start)
    new_df = calculate_pure_inr_prices(raw_df)

    # Merge with existing data if doing incremental update
    if not existing_df.empty and not full_mode:
        combined = new_df.combine_first(existing_df)
        # Overwrite with newest calculated values for overlapping recent dates
        combined.update(new_df)
        combined = combined.sort_index()
    else:
        combined = new_df.sort_index()

    # Save to primary target (Downloads)
    target_csv.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(target_csv)
    print(f"✅ Saved daily data ({len(combined)} rows) to: {target_csv}")

    # Also save a synchronized local copy in the script directory
    try:
        combined.to_csv(DEFAULT_LOCAL_CSV)
        print(f"📁 Synced local copy to: {DEFAULT_LOCAL_CSV}")
    except Exception:
        pass

    # Print summary of latest rates
    latest_date = combined.index[-1]
    latest_gold = combined.loc[latest_date, "gold_inr_per_10g"]
    latest_silver = combined.loc[latest_date, "silver_inr_per_1kg"]
    print(f"\n📊 Latest Prices ({latest_date}):")
    print(f"   • Gold   (₹ / 10g): ₹{latest_gold:,.2f}")
    print(f"   • Silver (₹ / 1kg): ₹{latest_silver:,.2f}")

    return combined


def export_monthly_csv(daily_df: pd.DataFrame, custom_output: str = None):
    """Resample daily prices to month-end values (YYYY-MM)."""
    monthly = daily_df.sort_index().copy()
    monthly["Month"] = monthly.index.str[:7]
    monthly = monthly.groupby("Month").last()
    monthly.index.name = "Month"

    out_path = Path(custom_output) if custom_output else DEFAULT_DOWNLOADS_CSV.with_name("gold_silver_inr_monthly.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out_path)
    print(f"📅 Saved monthly month-end data ({len(monthly)} months) to: {out_path}")
    return monthly


def update_html_app(daily_df: pd.DataFrame):
    """Optional helper to update recent monthly values in rolling_returns.html."""
    if not HTML_PATH.exists():
        print(f"⚠️ HTML file not found at {HTML_PATH}, skipping app update.")
        return

    # Extract month-end prices
    monthly = daily_df.sort_index().copy()
    monthly["Month"] = monthly.index.str[:7]
    monthly = monthly.groupby("Month").last()

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # The single-page app initializes RAW = {} and assigns each asset separately.
    # Store the same units as update_data.py: gold INR/10g, silver INR/kg.
    columns = {"Gold (INR)": "gold_inr_per_10g", "Silver (INR)": "silver_inr_per_1kg"}
    updated_months = 0
    for asset, column in columns.items():
        pattern = re.compile(r'(RAW\["' + re.escape(asset) + r'"\]\s*=\s*)(\{[^;]+\})(\s*;)')
        match = pattern.search(content)
        if not match:
            raise ValueError(f"Missing RAW block for {asset}; HTML was not changed")
        existing = json.loads(match.group(2))
        for month, value in monthly[column].items():
            value = float(value)
            if math.isfinite(value) and value > 0:
                existing[month] = round(value, 2)
                updated_months += 1
        serialized = json.dumps(dict(sorted(existing.items())), separators=(",", ":"), allow_nan=False)
        content = content[:match.start(2)] + serialized + content[match.end(2):]

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"🌐 Patched {updated_months} asset-month values into: {HTML_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Auto-fetch and update pure tax-free Gold and Silver INR prices.")
    parser.add_argument("--full", action="store_true", help="Re-fetch complete history from 2020-01-01 instead of incremental update.")
    parser.add_argument("--start", type=str, default=None, help="Custom start date in YYYY-MM-DD format.")
    parser.add_argument("--output", type=str, default=None, help="Custom output CSV file path.")
    parser.add_argument("--monthly", action="store_true", help="Also generate monthly month-end CSV.")
    parser.add_argument("--update-html", action="store_true", help="Also patch monthly prices into rolling_returns.html.")

    args = parser.parse_args()

    daily_data = update_dataset(
        full_mode=args.full,
        start_override=args.start,
        custom_output=args.output
    )

    if args.monthly:
        export_monthly_csv(daily_data)

    if args.update_html:
        update_html_app(daily_data)


if __name__ == "__main__":
    main()
