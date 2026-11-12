import urllib.request
import urllib.parse
import json
import time
import os
import re
import math
from pathlib import Path

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
    {"symbol": "BPCL", "id": 462, "name": "Bharat Petroleum Corp Ltd"},
    {"symbol": "BAJAJ-AUTO", "id": 369, "name": "Bajaj Auto Ltd"},
    {"symbol": "SHRIRAMFIN", "id": 3046, "name": "Shriram Finance Ltd"},
    {"symbol": "HINDALCO", "id": 1328, "name": "Hindalco Industries Ltd"},
    {"symbol": "APOLLOHOSP", "id": 218, "name": "Apollo Hospitals Enterprise Ltd"},
    {"symbol": "INDUSINDBK", "id": 1480, "name": "IndusInd Bank Ltd"},
    {"symbol": "TRENT", "id": 3467, "name": "Trent Ltd"},
    {"symbol": "BEL", "id": 456, "name": "Bharat Electronics Ltd"},
    {"symbol": "HAL", "id": 1274307, "name": "Hindustan Aeronautics Ltd"},
    {"symbol": "DLF", "id": 841, "name": "DLF Ltd"},
    {"symbol": "VBL", "id": 1273562, "name": "Varun Beverages Ltd"},
    {"symbol": "VEDL", "id": 2943, "name": "Vedanta Ltd"},
    {"symbol": "JIOFIN", "id": 1284422, "name": "Jio Financial Services Ltd"},
    {"symbol": "INDIGO", "id": 1273121, "name": "InterGlobe Aviation Ltd"},
    {"symbol": "SBILIFE", "id": 1274150, "name": "SBI Life Insurance Company Ltd"},
    {"symbol": "HDFCLIFE", "id": 1274197, "name": "HDFC Life Insurance Company Ltd"},
    {"symbol": "ADANIPOWER", "id": 58, "name": "Adani Power Ltd"},
    {"symbol": "TATACONSUM", "id": 3367, "name": "Tata Consumer Products Ltd"},
    {"symbol": "BSE", "id": 1273635, "name": "BSE Ltd"},
    {"symbol": "MCX", "id": 2156, "name": "Multi Commodity Exchange of India Ltd"},
    {"symbol": "CDSL", "id": 1274088, "name": "Central Depository Services (India) Ltd"},
    {"symbol": "PAYTM", "id": 1275094, "name": "One 97 Communications Ltd"},
    {"symbol": "NYKAA", "id": 1274992, "name": "FSN E-Commerce Ventures Ltd"},
    {"symbol": "IRCTC", "id": 1274700, "name": "Indian Railway Catering And Tourism Corp Ltd"},
    {"symbol": "IRFC", "id": 1274825, "name": "Indian Railway Finance Corp Ltd"},
    {"symbol": "PFC", "id": 2522, "name": "Power Finance Corporation Ltd"},
    {"symbol": "RECLTD", "id": 2809, "name": "REC Ltd"},
    {"symbol": "YESBANK", "id": 3783, "name": "Yes Bank Ltd"},
    {"symbol": "ETERNAL", "id": 1274894, "name": "Eternal Ltd"}
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json'
}

from datetime import datetime

def fetch_stock_chart(wid, consolidated=True, days=10000):
    cons_param = "&consolidated=true" if consolidated else ""
    url = f'https://www.screener.in/api/company/{wid}/chart/?q=Price-EPS&days={days}{cons_param}'
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))

def sanitize_eps_points(points):
    valid = []
    for point in points or []:
        try:
            dt, value = point
            dt = str(dt)[:10]
            datetime.strptime(dt, '%Y-%m-%d')
            value = float(value)
            if math.isfinite(value):
                valid.append((dt, value))
        except (ValueError, TypeError):
            continue
    valid.sort(key=lambda x: x[0])
    if len(valid) < 3:
        return valid
    start_idx = 0
    if len(valid) >= 4:
        tail = sorted(abs(p[1]) for p in valid[min(4, len(valid) // 2):min(len(valid), 15)])
        ref_med = tail[len(tail) // 2] if tail else 0
        end_abs = abs(valid[-1][1])
        if ref_med >= 0.5:
            while start_idx < min(4, len(valid) - 2) and (
                abs(valid[start_idx][1]) > max(15.0, 10.0 * ref_med) or
                (len(valid) <= 8 and end_abs >= 0.5 and abs(valid[start_idx][1]) > 50.0 * end_abs)
            ):
                start_idx += 1
    trimmed = valid[start_idx:]
    if len(trimmed) < 3:
        return trimmed
    cleaned = [trimmed[0]]
    for i in range(1, len(trimmed) - 1):
        prev_v = cleaned[-1][1]
        cur_v = trimmed[i][1]
        next_v = trimmed[i + 1][1]
        if prev_v > 0 and next_v > 0 and (cur_v > 4.0 * max(prev_v, next_v) or (0 < cur_v < 0.25 * min(prev_v, next_v))):
            continue
        cleaned.append(trimmed[i])
    cleaned.append(trimmed[-1])
    return cleaned

def choose_and_merge_charts(cons_raw, sa_raw):
    def get_eps(raw):
        if not raw: return []
        for ds in raw.get('datasets', []):
            if ds.get('metric') == 'EPS':
                return sanitize_eps_points(ds.get('values', []))
        return []

    ce = get_eps(cons_raw)
    se = get_eps(sa_raw)
    eps_basis = 'standalone' if sa_raw else 'consolidated'
    chosen_raw = sa_raw or cons_raw
    final_eps = se if sa_raw else ce

    if len(ce) >= 2:
        c_last = datetime.strptime(ce[-1][0], '%Y-%m-%d')
        s_last = datetime.strptime(se[-1][0], '%Y-%m-%d') if se else c_last
        if not se or (s_last - c_last).days <= 210:
            chosen_raw = cons_raw
            pre_sa = [pt for pt in se if pt[0] < ce[0][0]]
            stitched = list(pre_sa)
            used_mid = False
            for i in range(len(ce)):
                stitched.append(ce[i])
                if i + 1 < len(ce):
                    gap_days = (datetime.strptime(ce[i + 1][0], '%Y-%m-%d') - datetime.strptime(ce[i][0], '%Y-%m-%d')).days
                    if gap_days > 400:
                        mid_sa = [pt for pt in se if ce[i][0] < pt[0] < ce[i + 1][0]]
                        if mid_sa:
                            stitched.extend(mid_sa)
                            used_mid = True
            stitched.sort(key=lambda x: x[0])
            final_eps = stitched
            eps_basis = 'consolidated+standalone_splice' if (pre_sa or used_mid) else 'consolidated'

    if not chosen_raw:
        return None, eps_basis

    merged = dict(chosen_raw)
    merged['datasets'] = [
        {**ds, 'values': final_eps} if ds.get('metric') == 'EPS' else ds
        for ds in chosen_raw.get('datasets', [])
    ]
    return merged, eps_basis

def process_chart_data(raw_data, sym_info, eps_basis='consolidated'):
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
    for dt_str, p in sorted(price_raw, key=lambda x: str(x[0])):
        if p is None:
            continue
        ym = dt_str[:7]
        try:
            val = float(p)
            if math.isfinite(val) and val > 0:
                price_by_month[ym] = round(val, 2)
        except Exception:
            pass

    # Sort EPS points (keep full date for exact chronology, store latest within month)
    eps_points = sanitize_eps_points(eps_raw)
    if not eps_points:
        return None

    eps_by_pt_ym = {}
    for dt_s, val in eps_points:
        eps_by_pt_ym[dt_s[:7]] = val
    eps_months = sorted(eps_by_pt_ym.items())

    first_eps = eps_months[0][0]
    all_months = sorted([m for m in price_by_month.keys() if m >= first_eps])
    if len(all_months) < 12:
        return None

    eps_by_month = {}
    pe_by_month = {}

    cur_eps = None
    eps_idx = 0

    for ym in all_months:
        while eps_idx < len(eps_months) and eps_months[eps_idx][0] <= ym:
            cur_eps = eps_months[eps_idx][1]
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
        "epsBasis": eps_basis,
        "dates": all_months,
        "price": {m: price_by_month[m] for m in all_months},
        "eps": eps_by_month,
        "pe": pe_by_month
    }

def main(force_refresh=False):
    raw_cache_file = "raw_screener_cache.json"
    raw_cache = {}
    if not force_refresh and os.path.exists(raw_cache_file):
        try:
            with open(raw_cache_file, "r", encoding="utf-8") as f:
                raw_cache = json.load(f)
            print(f"Loaded {len(raw_cache)} raw screener cache responses.")
        except Exception as e:
            print("Could not load raw cache:", e)

    # Retain last-known-good stocks when an individual provider request fails.
    cache_path = Path("top_stocks_cache.json")
    all_stocks = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    refreshed = 0

    for i, stock in enumerate(STOCKS_CATALOG):
        sym = stock["symbol"]
        wid = stock["id"]
        entry = raw_cache.get(sym)
        raw_cons = entry.get("cons") if isinstance(entry, dict) and "cons" in entry else None
        raw_sa = entry.get("sa") if isinstance(entry, dict) and "sa" in entry else None

        if raw_cons is None and raw_sa is None:
            print(f"[{i+1}/{len(STOCKS_CATALOG)}] Fetching {sym} (ID: {wid})...")
            for attempt in range(3):
                try:
                    raw_cons = fetch_stock_chart(wid, consolidated=True)
                    time.sleep(0.25)
                    raw_sa = fetch_stock_chart(wid, consolidated=False)
                    raw_cache[sym] = {"cons": raw_cons, "sa": raw_sa}
                    time.sleep(0.25)
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

        merged_raw, basis = choose_and_merge_charts(raw_cons, raw_sa)
        processed = process_chart_data(merged_raw, stock, eps_basis=basis) if merged_raw else None
        if processed:
            all_stocks[sym] = processed
            refreshed += 1
            print(f"  ✓ {sym} [{basis}]: {len(processed['dates'])} months ({processed['dates'][0]} to {processed['dates'][-1]}), last EPS={processed['eps'][processed['dates'][-1]]}")
        else:
            print(f"  ✗ {sym}: processing returned None")

    if refreshed == 0:
        raise RuntimeError("No stocks refreshed; existing output files were preserved")

    # Prepare the embedded cache before writing outputs. The HTML is the app's
    # runtime source; writing only the standalone JS/JSON leaves it stale.
    html_path = Path("rolling_returns.html")
    html = html_path.read_text(encoding="utf-8")
    match = re.search(r'const TOP_STOCKS_DATA = (\{.*?\});', html)
    if not match:
        raise ValueError("Embedded TOP_STOCKS_DATA block not found; outputs were preserved")
    serialized = json.dumps(all_stocks, separators=(',', ':'), allow_nan=False)
    patched_html = html[:match.start(1)] + serialized + html[match.end(1):]

    with open(raw_cache_file, "w", encoding="utf-8") as f:
        json.dump(raw_cache, f)

    print(f"\nFinal count: {len(all_stocks)} / {len(STOCKS_CATALOG)} stocks.")
    
    with open("top_stocks_cache.json", "w", encoding="utf-8") as f:
        json.dump(all_stocks, f, separators=(',', ':'))
    print("Saved to top_stocks_cache.json")

    with open("top_stocks_data.js", "w", encoding="utf-8") as f:
        f.write("// Pre-cached Price, Real EPS, and P/E history for Top NSE Bluechips\n")
        f.write("const TOP_STOCKS_DATA = ")
        json.dump(all_stocks, f, separators=(',', ':'))
        f.write(";\nif (typeof window !== 'undefined') { window.TOP_STOCKS_DATA = TOP_STOCKS_DATA; }\n")
    html_path.write_text(patched_html, encoding="utf-8")
    print("Generated top_stocks_data.js and synchronized rolling_returns.html")

if __name__ == "__main__":
    main()
