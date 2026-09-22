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
        if p is None: continue
        ym = dt_str[:7]
        try:
            price_by_month[ym] = round(float(p), 2)
        except:
            pass

    # Sort EPS points
    eps_points = []
    for dt_str, e in eps_raw:
        if e is None: continue
        try:
            val = float(e)
            eps_points.append((dt_str[:7], val))
        except:
            pass
    eps_points.sort(key=lambda x: x[0])
    if not eps_points:
        return None

    all_months = sorted(price_by_month.keys())
    eps_by_month = {}
    pe_by_month = {}

    cur_eps = None
    eps_idx = 0

    for ym in all_months:
        while eps_idx < len(eps_points) and eps_points[eps_idx][0] <= ym:
            cur_eps = eps_points[eps_idx][1]
            eps_idx += 1
        if cur_eps is not None and cur_eps > 0:
            eps_by_month[ym] = round(cur_eps, 2)
            pe_by_month[ym] = round(price_by_month[ym] / cur_eps, 2)

    # Filter common valid dates
    common_dates = sorted([m for m in all_months if m in eps_by_month and eps_by_month[m] > 0 and m in price_by_month and price_by_month[m] > 0])
    if len(common_dates) < 12: # At least 1 year
        return None

    final_price = {m: price_by_month[m] for m in common_dates}
    final_eps = {m: eps_by_month[m] for m in common_dates}
    final_pe = {m: pe_by_month[m] for m in common_dates}

    return {
        "symbol": sym_info["symbol"],
        "name": sym_info["name"],
        "id": sym_info["id"],
        "dates": common_dates,
        "price": final_price,
        "eps": final_eps,
        "pe": final_pe
    }

def main():
    cache_file = "top_stocks_cache.json"
    all_stocks = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                all_stocks = json.load(f)
            print(f"Loaded {len(all_stocks)} existing cached stocks.")
        except Exception as e:
            print("Could not load cache:", e)

    missing = [s for s in STOCKS_CATALOG if s["symbol"] not in all_stocks]
    print(f"Need to fetch {len(missing)} stocks...")

    for i, stock in enumerate(missing):
        sym = stock["symbol"]
        wid = stock["id"]
        print(f"[{i+1}/{len(missing)}] Fetching {sym} (ID: {wid})...")
        processed = None
        for attempt in range(3):
            try:
                # 1. Try consolidated
                raw = fetch_stock_chart(wid, consolidated=True)
                processed = process_chart_data(raw, stock)
                # If consolidated has few dates (e.g. standalone company like Nestle), try standalone
                if not processed or len(processed['dates']) < 50:
                    time.sleep(1.0)
                    raw_sa = fetch_stock_chart(wid, consolidated=False)
                    processed_sa = process_chart_data(raw_sa, stock)
                    if processed_sa and (not processed or len(processed_sa['dates']) > len(processed['dates'])):
                        processed = processed_sa
                if processed:
                    all_stocks[sym] = processed
                    print(f"  ✓ {sym}: {len(processed['dates'])} months ({processed['dates'][0]} to {processed['dates'][-1]})")
                    break
                else:
                    print(f"  ✗ {sym}: processing returned None")
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
        time.sleep(1.5)

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
