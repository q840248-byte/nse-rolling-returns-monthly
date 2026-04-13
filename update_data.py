"""
update_data.py  —  Fetches latest NSE index data and patches rolling_returns.html
==================================================================================
Run by GitHub Actions every weekday at 6:30pm IST (1:00pm UTC).
Also safe to run manually anytime.

Modes:
  python update_data.py               → fetches last 6 months (daily auto-update)
  python update_data.py --full        → fetches ALL history from each index base date
"""

import re
import sys
import json
import time
import requests
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

HTML_FILE  = "rolling_returns.html"
FULL_MODE  = "--full" in sys.argv

API_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
HEADERS = {
    "Content-Type":     "application/json; charset=utf-8",
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/plain, */*",
    "Referer":          "https://www.niftyindices.com/reports/historical-data",
    "X-Requested-With": "XMLHttpRequest",
}

# Map display names → (api_name, base_date)
# base_date is only used in --full mode to know where to start fetching from
INDEX_CONFIG = {
    "Nifty 50":                                     ("NIFTY 50",                                    "1995-11-03"),
    "Nifty Next 50":                                ("NIFTY NEXT 50",                               "1996-01-01"),
    "Nifty 100":                                    ("NIFTY 100",                                   "1996-01-01"),
    "Nifty 200":                                    ("NIFTY 200",                                   "1999-01-01"),
    "Nifty Total Market":                           ("NIFTY TOTAL MKT",                             "2005-04-01"),
    "Nifty 500":                                    ("NIFTY 500",                                   "1999-01-01"),
    "Nifty500 LargeMidSmall Equal-Cap Weighted":    ("NIFTY500 LARGEMIDSMALL EQUAL-CAP WEIGHTED",   "2005-04-01"),
    "Nifty Midcap 150":                             ("NIFTY MIDCAP 150",                            "2004-04-01"),
    "Nifty Midcap 50":                              ("NIFTY MIDCAP 50",                             "2004-04-01"),
    "Nifty Midcap Select":                          ("NIFTY MID SELECT",                            "2005-04-01"),
    "Nifty Midcap 100":                             ("NIFTY MIDCAP 100",                            "2004-04-01"),
    "Nifty Smallcap 500":                           ("NIFTY SMALLCAP 500",                          "2004-04-01"),
    "Nifty Smallcap 250":                           ("NIFTY SMALLCAP 250",                          "2004-04-01"),
    "Nifty Smallcap 50":                            ("NIFTY SMALLCAP 50",                           "2004-04-01"),
    "Nifty Smallcap 100":                           ("NIFTY SMALLCAP 100",                          "2004-04-01"),
    "Nifty Microcap 250":                           ("NIFTY MICROCAP250",                           "2004-04-01"),
    "Nifty LargeMidcap 250":                        ("NIFTY LARGEMID250",                           "2004-04-01"),
    "Nifty MidSmallcap 400":                        ("NIFTY MIDSMALLCAP 400",                       "2004-04-01"),
    "Nifty MidSmallcap400 50-50":                   ("NIFTY MIDSMALLCAP400 50:50",                  "2004-04-01"),
    "Nifty India FPI 150":                          ("NIFTY INDIA FPI 150",                         "2012-01-01"),
    "Nifty100 Equal Weight":                        ("NIFTY100 EQL WGT",                            "2003-01-01"),
    "Nifty100 Low Volatility 30":                   ("NIFTY100 LOWVOL30",                           "2005-04-01"),
    "Nifty 50 Arbitrage":                           ("NIFTY 50 Arbitrage",                          "2005-04-01"),
    "Nifty200 Alpha 30":                            ("Nifty200 Alpha 30",                           "2005-04-01"),
    "Nifty200 Momentum 30":                         ("NIFTY200MOMENTM30",                           "2005-04-01"),
    "Nifty100 Alpha 30":                            ("NIFTY100 Alpha 30",                           "2005-04-01"),
    "Nifty Alpha 50":                               ("NIFTY Alpha 50",                              "2005-04-01"),
    "Nifty Alpha Low Volatility 30":                ("NIFTY Alpha Low-Volatility 30",               "2005-04-01"),
    "Nifty Alpha Quality Low Volatility 30":        ("NIFTY Alpha Quality Low-Volatility 30",       "2005-04-01"),
    "Nifty Alpha Quality Value Low Volatility 30":  ("NIFTY Alpha Quality Value Low-Volatility 30", "2005-04-01"),
    "Nifty Dividend Opportunities 50":              ("NIFTY DIV OPPS 50",                           "2005-04-01"),
    "Nifty Growth Sectors 15":                      ("NIFTY GROWSECT 15",                           "2005-04-01"),
    "Nifty High Beta 50":                           ("NIFTY HIGH BETA 50",                          "2005-04-01"),
    "Nifty Low Volatility 50":                      ("NIFTY LOW VOLATILITY 50",                     "2005-04-01"),
    "Nifty Top 10 Equal Weight":                    ("NIFTY TOP 10 EQUAL WEIGHT",                   "2005-04-01"),
    "Nifty Top 15 Equal Weight":                    ("NIFTY TOP 15 EQUAL WEIGHT",                   "2005-04-01"),
    "Nifty Top 20 Equal Weight":                    ("NIFTY TOP 20 EQUAL WEIGHT",                   "2005-04-01"),
    "Nifty100 Quality 30":                          ("NIFTY100 QUALTY30",                           "2005-04-01"),
    "Nifty Midcap150 Momentum 50":                  ("Nifty Midcap150 Momentum 50",                 "2005-04-01"),
    "Nifty500 Flexicap Quality 30":                 ("Nifty500 Flexicap Quality 30",                "2005-04-01"),
    "Nifty500 Low Volatility 50":                   ("Nifty500 Low Volatility 50",                  "2005-04-01"),
    "Nifty500 Momentum 50":                         ("Nifty500 Momentum 50",                        "2005-04-01"),
    "Nifty500 Quality 50":                          ("Nifty500 Quality 50",                         "2005-04-01"),
    "Nifty500 Multifactor MQVLv 50":                ("Nifty500 Multifactor MQVLv 50",               "2005-04-01"),
    "Nifty Midcap150 Quality 50":                   ("NIFTY Midcap150 Quality 50",                  "2005-04-01"),
    "Nifty Smallcap250 Quality 50":                 ("Nifty Smallcap250 Quality 50",                "2005-04-01"),
    "Nifty Total Market Momentum Quality 50":       ("NIFTY TOTAL MARKET MOMENTUM QUALITY 50",      "2005-04-01"),
    "Nifty500 Multicap Momentum Quality 50":        ("Nifty500 Multicap Momentum Quality 50",       "2005-04-01"),
    "Nifty MidSmallcap400 Momentum Quality 100":    ("Nifty MidSmallcap400 Momentum Quality 100",   "2005-04-01"),
    "Nifty Smallcap250 Momentum Quality 100":       ("Nifty Smallcap250 Momentum Quality 100",      "2005-04-01"),
    "Nifty Quality Low Volatility 30":              ("NIFTY Quality Low-Volatility 30",              "2005-04-01"),
    "Nifty50 Equal Weight":                         ("NIFTY50 EQL WGT",                             "2003-01-01"),
    "Nifty50 USD":                                  ("NIFTY50 USD",                                 "2003-01-01"),
    "Nifty50 Value 20":                             ("NIFTY50 Value 20",                            "2005-04-01"),
    "Nifty500 Equal Weight":                        ("Nifty500 Equal Weight",                       "2005-04-01"),
    "Nifty500 Value 50":                            ("Nifty500 Value 50",                           "2005-04-01"),
    "Nifty200 Value 30":                            ("Nifty200 Value 30",                           "2005-04-01"),
    "Nifty200 Quality 30":                          ("Nifty200 Quality 30",                         "2005-04-01"),
    "Nifty500 Multicap 50-25-25":                   ("Nifty500 Multicap",                           "2005-04-01"),
}

def fmt(d):
    return d.strftime("%d-%b-%Y")

def parse_date(dt_str):
    dt_str = dt_str.strip()
    for fmt_str in ["%d %b %Y", "%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(dt_str, fmt_str)
        except:
            pass
    return None

def fetch_data(api_name, from_date, to_date, retries=3):
    """Fetch daily rows from niftyindices.com for a date range, with retries."""
    payload = {"cinfo": json.dumps({
        "name":      api_name,
        "startDate": fmt(from_date),
        "endDate":   fmt(to_date),
        "indexName": api_name,
    })}
    for attempt in range(retries):
        try:
            r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
            r.raise_for_status()
            outer = r.json()
            raw   = outer.get("d", "[]")
            rows  = json.loads(raw) if isinstance(raw, str) else raw
            return rows or []
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3)
            else:
                print(f"    API error: {e}")
    return []

def rows_to_month_end_close(rows):
    """
    Convert daily rows to {YYYY-MM: close} dict.
    Picks the LAST trading day's closing price for each month.
    """
    month_best = {}
    for row in rows:
        dt_str = (
            row.get("TIMESTAMP") or
            row.get("HistoricalDate") or
            row.get("date") or ""
        )
        close_raw = row.get("CLOSE") or row.get("close") or 0
        dt = parse_date(dt_str) if dt_str else None
        if not dt:
            continue
        try:
            close_val = round(float(str(close_raw).replace(",", "")), 2)
        except:
            continue
        if close_val <= 0:
            continue
        key = dt.strftime("%Y-%m")
        if key not in month_best or dt > month_best[key][0]:
            month_best[key] = (dt, close_val)
    return {k: v[1] for k, v in month_best.items()}

def fetch_full_history(api_name, base_date_str, today):
    """
    Fetch ALL data from base_date to today in 12-month chunks.
    Returns merged {YYYY-MM: close} dict.
    """
    start = datetime.strptime(base_date_str, "%Y-%m-%d").date().replace(day=1)
    all_monthly = {}
    chunk_start = start
    while chunk_start <= today:
        chunk_end = min((chunk_start + relativedelta(months=12) - relativedelta(days=1)), today)
        rows = fetch_data(api_name, chunk_start, chunk_end)
        if rows:
            chunk_monthly = rows_to_month_end_close(rows)
            all_monthly.update(chunk_monthly)
        time.sleep(1.2)
        chunk_start = chunk_start + relativedelta(months=12)
    return all_monthly

def get_last_month_in_data(data_dict):
    keys = [k for k in data_dict.keys() if re.match(r"^\d{4}-\d{2}$", k)]
    return max(keys) if keys else None

def main():
    mode = "FULL HISTORY" if FULL_MODE else "LAST 6 MONTHS"
    print(f"Reading {HTML_FILE}... [Mode: {mode}]")
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    pattern = re.compile(
        r'(RAW\["([^"]+)"\]\s*=\s*)(\{[^;]+\})\s*;',
        re.DOTALL
    )

    today      = date.today()
    this_month = today.strftime("%Y-%m")
    updated    = 0
    total      = 0

    def replace_block(m):
        nonlocal updated, total
        prefix     = m.group(1)
        index_name = m.group(2)
        old_json   = m.group(3)

        if index_name in ("Gold (INR)", "Silver (INR)"):
            return m.group(0)

        total += 1
        config = INDEX_CONFIG.get(index_name)
        if not config:
            print(f"  [{index_name}] ⚠️  No config — skipping")
            return m.group(0)

        api_name, base_date_str = config

        try:
            data = json.loads(old_json)
        except:
            print(f"  [{index_name}] ⚠️  Could not parse existing data — skipping")
            return m.group(0)

        if FULL_MODE:
            # Fetch everything from base date in 12-month chunks
            print(f"  [{index_name}] Full fetch from {base_date_str}...", flush=True)
            new_monthly = fetch_full_history(api_name, base_date_str, today)
        else:
            # Fetch only last 6 months
            fetch_from = (today - relativedelta(months=5)).replace(day=1)
            fetch_to   = today
            print(f"  [{index_name}] Fetching {fmt(fetch_from)} → {fmt(fetch_to)}...", end=" ", flush=True)
            time.sleep(0.8)
            rows = fetch_data(api_name, fetch_from, fetch_to)
            if not rows:
                print("❌ no data returned from API")
                return m.group(0)
            new_monthly = rows_to_month_end_close(rows)

        if not new_monthly:
            print("❌ could not parse any rows")
            return m.group(0)

        added = 0
        for k, v in sorted(new_monthly.items()):
            if k <= this_month:
                if k not in data or data[k] != v:
                    data[k] = v
                    added += 1

        if added == 0:
            print("✓ no changes")
            return m.group(0)

        latest = max(k for k in data if re.match(r'^\d{4}-\d{2}$', k))
        print(f"✅ updated {added} month(s) → latest: {latest} (close: {data[latest]})")
        updated += 1

        new_json = json.dumps(dict(sorted(data.items())), separators=(",", ":"))
        return f'{prefix}{new_json};'

    new_html = pattern.sub(replace_block, html)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"\n✅ Done. Updated {updated}/{total} indices.")
    print(f"   Saved: {HTML_FILE}")

if __name__ == "__main__":
    main()
