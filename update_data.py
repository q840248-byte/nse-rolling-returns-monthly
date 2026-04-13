"""
update_data.py  —  Fetches latest NSE index data and patches rolling_returns.html
==================================================================================
Run by GitHub Actions every night at 6:30pm IST (1:00pm UTC).
Also safe to run manually anytime.

How it works:
  1. Reads rolling_returns.html and finds all RAW["Index Name"] = {...} blocks
  2. For each index, finds the latest date already in the data
  3. Fetches any newer data from niftyindices.com API
  4. Patches the HTML in-place with the new data points
  5. Commits the updated HTML back to the repo (done by the workflow)
"""

import re
import json
import time
import requests
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

HTML_FILE = "rolling_returns.html"

API_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
HEADERS = {
    "Content-Type":     "application/json; charset=utf-8",
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/plain, */*",
    "Referer":          "https://www.niftyindices.com/reports/historical-data",
    "X-Requested-With": "XMLHttpRequest",
}

# Map display names used in HTML → API names used by niftyindices.com
API_NAME_MAP = {
    "Nifty 50":                                     "NIFTY 50",
    "Nifty Next 50":                                "NIFTY NEXT 50",
    "Nifty 100":                                    "NIFTY 100",
    "Nifty 200":                                    "NIFTY 200",
    "Nifty Total Market":                           "NIFTY TOTAL MKT",
    "Nifty 500":                                    "NIFTY 500",
    "Nifty500 LargeMidSmall Equal-Cap Weighted":    "NIFTY500 LARGEMIDSMALL EQUAL-CAP WEIGHTED",
    "Nifty Midcap 150":                             "NIFTY MIDCAP 150",
    "Nifty Midcap 50":                              "NIFTY MIDCAP 50",
    "Nifty Midcap Select":                          "NIFTY MID SELECT",
    "Nifty Midcap 100":                             "NIFTY MIDCAP 100",
    "Nifty Smallcap 500":                           "NIFTY SMALLCAP 500",
    "Nifty Smallcap 250":                           "NIFTY SMALLCAP 250",
    "Nifty Smallcap 50":                            "NIFTY SMALLCAP 50",
    "Nifty Smallcap 100":                           "NIFTY SMALLCAP 100",
    "Nifty Microcap 250":                           "NIFTY MICROCAP250",
    "Nifty LargeMidcap 250":                        "NIFTY LARGEMID250",
    "Nifty MidSmallcap 400":                        "NIFTY MIDSMALLCAP 400",
    "Nifty MidSmallcap400 50-50":                   "NIFTY MIDSMALLCAP400 50:50",
    "Nifty India FPI 150":                          "NIFTY INDIA FPI 150",
    "Nifty100 Equal Weight":                        "NIFTY100 EQL WGT",
    "Nifty100 Low Volatility 30":                   "NIFTY100 LOWVOL30",
    "Nifty 50 Arbitrage":                           "NIFTY 50 Arbitrage",
    "Nifty200 Alpha 30":                            "Nifty200 Alpha 30",
    "Nifty200 Momentum 30":                         "NIFTY200MOMENTM30",
    "Nifty100 Alpha 30":                            "NIFTY100 Alpha 30",
    "Nifty Alpha 50":                               "NIFTY Alpha 50",
    "Nifty Alpha Low Volatility 30":                "NIFTY Alpha Low-Volatility 30",
    "Nifty Alpha Quality Low Volatility 30":        "NIFTY Alpha Quality Low-Volatility 30",
    "Nifty Alpha Quality Value Low Volatility 30":  "NIFTY Alpha Quality Value Low-Volatility 30",
    "Nifty Dividend Opportunities 50":              "NIFTY DIV OPPS 50",
    "Nifty Growth Sectors 15":                      "NIFTY GROWSECT 15",
    "Nifty High Beta 50":                           "NIFTY HIGH BETA 50",
    "Nifty Low Volatility 50":                      "NIFTY LOW VOLATILITY 50",
    "Nifty Top 10 Equal Weight":                    "NIFTY TOP 10 EQUAL WEIGHT",
    "Nifty Top 15 Equal Weight":                    "NIFTY TOP 15 EQUAL WEIGHT",
    "Nifty Top 20 Equal Weight":                    "NIFTY TOP 20 EQUAL WEIGHT",
    "Nifty100 Quality 30":                          "NIFTY100 QUALTY30",
    "Nifty Midcap150 Momentum 50":                  "Nifty Midcap150 Momentum 50",
    "Nifty500 Flexicap Quality 30":                 "Nifty500 Flexicap Quality 30",
    "Nifty500 Low Volatility 50":                   "Nifty500 Low Volatility 50",
    "Nifty500 Momentum 50":                         "Nifty500 Momentum 50",
    "Nifty500 Quality 50":                          "Nifty500 Quality 50",
    "Nifty500 Multifactor MQVLv 50":                "Nifty500 Multifactor MQVLv 50",
    "Nifty Midcap150 Quality 50":                   "NIFTY Midcap150 Quality 50",
    "Nifty Smallcap250 Quality 50":                 "Nifty Smallcap250 Quality 50",
    "Nifty Total Market Momentum Quality 50":       "NIFTY TOTAL MARKET MOMENTUM QUALITY 50",
    "Nifty500 Multicap Momentum Quality 50":        "Nifty500 Multicap Momentum Quality 50",
    "Nifty MidSmallcap400 Momentum Quality 100":    "Nifty MidSmallcap400 Momentum Quality 100",
    "Nifty Smallcap250 Momentum Quality 100":       "Nifty Smallcap250 Momentum Quality 100",
    "Nifty Quality Low Volatility 30":              "NIFTY Quality Low-Volatility 30",
    "Nifty50 Equal Weight":                         "NIFTY50 EQL WGT",
    "Nifty50 USD":                                  "NIFTY50 USD",
    "Nifty50 Value 20":                             "NIFTY50 Value 20",
    "Nifty500 Equal Weight":                        "Nifty500 Equal Weight",
    "Nifty500 Value 50":                            "Nifty500 Value 50",
    "Nifty200 Value 30":                            "Nifty200 Value 30",
    "Nifty200 Quality 30":                          "Nifty200 Quality 30",
    "Nifty500 Multicap 50-25-25":                   "Nifty500 Multicap",
}

def fmt(d): return d.strftime("%d-%b-%Y")

def fetch_monthly(api_name, from_date, to_date):
    """Fetch monthly closing prices from niftyindices.com."""
    payload = {"cinfo": json.dumps({
        "name": api_name, "startDate": fmt(from_date),
        "endDate": fmt(to_date), "indexName": api_name,
    })}
    try:
        r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
        outer = r.json()
        raw = outer.get("d", "[]")
        rows = json.loads(raw) if isinstance(raw, str) else raw
        return rows or []
    except Exception as e:
        print(f"    API error: {e}")
        return []

def rows_to_monthly(rows):
    """Convert API rows to {YYYY-MM: close_value} dict."""
    monthly = {}
    for row in rows:
        # Find date field
        dt_str = row.get("TIMESTAMP") or row.get("HistoricalDate") or row.get("date") or ""
        close  = row.get("CLOSE") or row.get("close") or 0
        try:
            dt = datetime.strptime(dt_str.strip(), "%d %b %Y") if dt_str else None
            if not dt:
                # Try other formats
                for fmt_str in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
                    try: dt = datetime.strptime(dt_str.strip(), fmt_str); break
                    except: pass
            if dt:
                key = dt.strftime("%Y-%m")
                val = round(float(close), 2)
                # Keep last value of each month
                if key not in monthly or dt.day > datetime.strptime(monthly.get("_d_" + key, "1"), "%d").day:
                    monthly[key] = val
        except:
            pass
    # Remove internal day-tracking keys
    return {k: v for k, v in monthly.items() if not k.startswith("_d_")}

def get_last_month_in_data(data_dict):
    """Return the latest YYYY-MM key in a data dict."""
    keys = [k for k in data_dict.keys() if re.match(r"\d{4}-\d{2}", k)]
    return max(keys) if keys else None

def main():
    print(f"Reading {HTML_FILE}...")
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # Find all RAW["..."] = {...} blocks
    pattern = re.compile(
        r'(RAW\["([^"]+)"\]\s*=\s*)(\{[^;]+\})\s*;',
        re.DOTALL
    )

    today     = date.today()
    this_month = today.strftime("%Y-%m")
    updated   = 0
    total     = 0

    def replace_block(m):
        nonlocal updated, total
        prefix     = m.group(1)
        index_name = m.group(2)
        old_json   = m.group(3)

        # Skip commodity data (Gold, Silver etc.)
        if index_name in ("Gold (INR)", "Silver (INR)"):
            return m.group(0)

        total += 1
        api_name = API_NAME_MAP.get(index_name)
        if not api_name:
            print(f"  [{index_name}] ⚠️  No API mapping — skipping")
            return m.group(0)

        try:
            data = json.loads(old_json)
        except:
            print(f"  [{index_name}] ⚠️  Could not parse existing data — skipping")
            return m.group(0)

        last_month = get_last_month_in_data(data)
        if not last_month:
            return m.group(0)

        # Check if already up to date
        if last_month >= this_month:
            print(f"  [{index_name}] ✓ Already current ({last_month})")
            return m.group(0)

        # Fetch from last_month+1 to today
        last_dt   = datetime.strptime(last_month, "%Y-%m")
        fetch_from = (last_dt + relativedelta(months=1)).replace(day=1)
        fetch_to   = today

        print(f"  [{index_name}] Fetching {fmt(fetch_from)} → {fmt(fetch_to)}...", end=" ", flush=True)
        time.sleep(0.8)

        rows = fetch_monthly(api_name, fetch_from, fetch_to)
        if not rows:
            print("no new data")
            return m.group(0)

        new_monthly = rows_to_monthly(rows)
        added = 0
        for k, v in sorted(new_monthly.items()):
            if k > last_month and k <= this_month:
                data[k] = v
                added += 1

        if added == 0:
            print("no new months")
            return m.group(0)

        print(f"added {added} month(s) → latest: {max(data.keys())}")
        updated += 1

        # Rebuild compact JSON (no spaces, sorted by key)
        new_json = json.dumps(dict(sorted(data.items())), separators=(",", ":"))
        return f'{prefix}{new_json};'

    new_html = pattern.sub(replace_block, html)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"\n✅ Done. Updated {updated}/{total} indices.")
    print(f"   Saved: {HTML_FILE}")

if __name__ == "__main__":
    main()
