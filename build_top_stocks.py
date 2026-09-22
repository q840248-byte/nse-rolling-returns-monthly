import urllib.request
import urllib.parse
import json
import time
import os
import re

STOCKS_CATALOG = [
    {"symbol": "RELIANCE", "id": 2726, "name": "Reliance Industries Ltd"},
    {"symbol": "TCS", "id": 3365, "name": "Tata Consultancy Services Ltd"},
    {"symbol": "HDFCBANK", "id": 1298, "name": "HDFC Bank Ltd"},
    {"symbol": "INFY", "id": 1489, "name": "Infosys Ltd"},
    {"symbol": "ICICIBANK", "id": 1384, "name": "ICICI Bank Ltd"},
    {"symbol": "ITC", "id": 1552, "name": "ITC Ltd"},
    {"symbol": "LT", "id": 1870, "name": "Larsen & Toubro Ltd"},
    {"symbol": "BHARTIARTL", "id": 467, "name": "Bharti Airtel Ltd"},
    {"symbol": "SBIN", "id": 3188, "name": "State Bank of India"},
    {"symbol": "TATAMOTORS", "id": 3370, "name": "Tata Motors Ltd"},
    {"symbol": "KOTAKBANK", "id": 1818, "name": "Kotak Mahindra Bank Ltd"},
    {"symbol": "AXISBANK", "id": 348, "name": "Axis Bank Ltd"},
    {"symbol": "HINDUNILVR", "id": 1350, "name": "Hindustan Unilever Ltd"},
    {"symbol": "BAJFINANCE", "id": 372, "name": "Bajaj Finance Ltd"},
    {"symbol": "MARUTI", "id": 2023, "name": "Maruti Suzuki India Ltd"},
    {"symbol": "SUNPHARMA", "id": 3245, "name": "Sun Pharmaceutical Industries Ltd"},
    {"symbol": "ASIANPAINT", "id": 295, "name": "Asian Paints Ltd"},
    {"symbol": "TITAN", "id": 3437, "name": "Titan Company Ltd"},
    {"symbol": "HCLTECH", "id": 1297, "name": "HCL Technologies Ltd"},
    {"symbol": "WIPRO", "id": 3763, "name": "Wipro Ltd"},
    {"symbol": "NTPC", "id": 2303, "name": "NTPC Ltd"},
    {"symbol": "ONGC", "id": 2320, "name": "Oil & Natural Gas Corpn Ltd"},
    {"symbol": "POWERGRID", "id": 2523, "name": "Power Grid Corporation of India Ltd"},
    {"symbol": "ADANIENT", "id": 56, "name": "Adani Enterprises Ltd"},
    {"symbol": "ADANIPORTS", "id": 57, "name": "Adani Ports & SEZ Ltd"},
    {"symbol": "TATASTEEL", "id": 3373, "name": "Tata Steel Ltd"},
    {"symbol": "JSWSTEEL", "id": 1657, "name": "JSW Steel Ltd"},
    {"symbol": "COALINDIA", "id": 681, "name": "Coal India Ltd"},
    {"symbol": "ULTRACEMCO", "id": 3525, "name": "UltraTech Cement Ltd"},
    {"symbol": "BAJAJFINSV", "id": 373, "name": "Bajaj Finserv Ltd"},
    {"symbol": "M&M", "id": 1973, "name": "Mahindra & Mahindra Ltd"},
    {"symbol": "NESTLEIND", "id": 2236, "name": "Nestle India Ltd"},
    {"symbol": "TECHM", "id": 100068, "name": "Tech Mahindra Ltd"},
    {"symbol": "GRASIM", "id": 1198, "name": "Grasim Industries Ltd"},
    {"symbol": "CIPLA", "id": 661, "name": "Cipla Ltd"},
    {"symbol": "DIVISLAB", "id": 837, "name": "Divis Laboratories Ltd"},
    {"symbol": "DRREDDY", "id": 852, "name": "Dr Reddys Laboratories Ltd"},
    {"symbol": "EICHERMOT", "id": 888, "name": "Eicher Motors Ltd"},
    {"symbol": "BPCL", "id": 462, "name": "Bharat Petroleum Corp Ltd"}
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

def fetch_stock_chart(wid, consolidated=True):
    cons_param = "&consolidated=true" if consolidated else ""
    url = f'https://www.screener.in/api/company/{wid}/chart/?q=Price-EPS&days=5475{cons_param}'
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def process_chart_data(raw_data, sym_info):
    price_raw = []
    eps_raw = []
    for ds in raw_data.get('datasets', []):
        if ds.get('metric') == 'Price':
            price_raw = ds.get('values', [])
        elif ds.get('metric') == 'EPS':
            eps_raw = ds.get('values', [])

    if not price_raw or not eps_raw:
        return None

    # Group price by month (last price in month)
    price_by_month = {}
    for dt_str, p in price_raw:
        if p is None:
            continue
        ym = dt_str[:7]
        try:
            val = float(p)
            if val > 0:
                price_by_month[ym] = round(val, 2)
        except Exception:
            pass

    # Sort EPS points
    eps_points = []
    for dt_str, e in eps_raw:
        if e is None:
            continue
        try:
            val = float(e)
            eps_points.append((dt_str[:7], val))
        except Exception:
            pass
    eps_points.sort(key=lambda x: x[0])
    if not eps_points:
        return None

    first_eps = eps_points[0][0]
    all_months = sorted([m for m in price_by_month.keys() if m >= first_eps])
    if len(all_months) < 12:
        return None

    eps_by_month = {}
    pe_by_month = {}

    cur_eps = None
    eps_idx = 0

    for ym in all_months:
        while eps_idx < len(eps_points) and eps_points[eps_idx][0] <= ym:
            cur_eps = eps_points[eps_idx][1]
            eps_idx += 1
        eps_by_month[ym] = round(cur_eps, 2)
        if cur_eps is not None and cur_eps > 0 and price_by_month[ym] > 0:
            pe_by_month[ym] = round(price_by_month[ym] / cur_eps, 2)
        else:
            pe_by_month[ym] = None

    return {
        "symbol": sym_info["symbol"],
        "name": sym_info["name"],
        "id": sym_info["id"],
        "dates": all_months,
        "price": {m: price_by_month[m] for m in all_months},
        "eps": eps_by_month,
        "pe": pe_by_month
    }

def main():
    raw_cache_file = "raw_screener_cache.json"
    raw_cache = {}
    if os.path.exists(raw_cache_file):
        try:
            with open(raw_cache_file, "r", encoding="utf-8") as f:
                raw_cache = json.load(f)
            print(f"Loaded {len(raw_cache)} raw screener cache responses.")
        except Exception as e:
            print("Could not load raw cache:", e)

    all_stocks = {}

    for i, stock in enumerate(STOCKS_CATALOG):
        sym = stock["symbol"]
        wid = stock["id"]
        raw = raw_cache.get(sym)

        if not raw:
            print(f"[{i+1}/{len(STOCKS_CATALOG)}] Fetching {sym} (ID: {wid})...")
            for attempt in range(3):
                try:
                    raw = fetch_stock_chart(wid, consolidated=True)
                    eps_ds = next((x for x in raw.get('datasets', []) if x.get('metric') == 'EPS'), None)
                    eps_len = len(eps_ds.get('values', [])) if eps_ds else 0
                    if eps_len < 30:
                        time.sleep(1.0)
                        raw_sa = fetch_stock_chart(wid, consolidated=False)
                        eps_sa = next((x for x in raw_sa.get('datasets', []) if x.get('metric') == 'EPS'), None)
                        sa_len = len(eps_sa.get('values', [])) if eps_sa else 0
                        if sa_len > eps_len:
                            raw = raw_sa
                    raw_cache[sym] = raw
                    time.sleep(0.5)
                    break
                except urllib.error.HTTPError as he:
                    if he.code == 429:
                        print(f"  ⚠️ Rate limit 429 for {sym}. Waiting 5 seconds before retry {attempt+1}...")
                        time.sleep(5)
                    else:
                        print(f"  ✗ {sym} HTTP error {he.code}: {he}")
                        break
                except Exception as e:
                    print(f"  ✗ {sym} failed: {e}")
                    break

        processed = process_chart_data(raw, stock) if raw else None
        if processed:
            all_stocks[sym] = processed
            print(f"  ✓ {sym}: {len(processed['dates'])} months ({processed['dates'][0]} to {processed['dates'][-1]})")
        else:
            print(f"  ✗ {sym}: processing returned None")

    # Save raw cache
    with open(raw_cache_file, "w", encoding="utf-8") as f:
        json.dump(raw_cache, f)

    print(f"\nFinal count: {len(all_stocks)} / {len(STOCKS_CATALOG)} stocks.")
    
    # Save cache JSON
    with open("top_stocks_cache.json", "w", encoding="utf-8") as f:
        json.dump(all_stocks, f, separators=(',', ':'))
    print("Saved to top_stocks_cache.json")

    # Generate top_stocks_data.js
    with open("top_stocks_data.js", "w", encoding="utf-8") as f:
        f.write("// Pre-cached 15-year Price, Real EPS, and P/E history for Top NSE Bluechips\n")
        f.write("const TOP_STOCKS_DATA = ")
        json.dump(all_stocks, f, separators=(',', ':'))
        f.write(";\nif (typeof window !== 'undefined') { window.TOP_STOCKS_DATA = TOP_STOCKS_DATA; }\n")
    print("Generated top_stocks_data.js")

if __name__ == "__main__":
    main()
