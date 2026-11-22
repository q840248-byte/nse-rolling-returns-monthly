#!/usr/bin/env python3
"""
Reliance-only Point-in-Time (PIT) collector proof-of-concept.

Supports:
  1. Fixture mode (--bhavcopy, --announcements, --pdf)
  2. Live NSE mode (--live) with explicit handling for WAF blocks (403/401),
     missing files (404), and network errors.

Reports found vs. missing monthly prices and filing records, extracts
consolidated Basic/Diluted EPS (before & after exceptional items) mapped to
period-end dates, and checks announcement dissemination timestamps against
the 15:30 IST market-close cutoff.
"""

import argparse
import csv
import datetime as dt
import http.cookiejar
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

MARKET_CLOSE_TIME = dt.time(15, 30, 0)

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def parse_nse_timestamp(ts_str):
    if not ts_str or not ts_str.strip():
        return None
    ts_str = ts_str.strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


def parse_bhavcopy(bhavcopy_path, symbol="RELIANCE", series="EQ"):
    with open(bhavcopy_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("SYMBOL") == symbol and row.get("SERIES") == series:
                return {
                    "symbol": symbol,
                    "series": series,
                    "date": row.get("TIMESTAMP"),
                    "close": float(row["CLOSE"]),
                }
    return None


def parse_announcements(ann_path, symbol="RELIANCE"):
    path = Path(ann_path)
    raw = path.read_text(encoding="utf-8").strip()
    if raw.startswith("[") or raw.startswith("{"):
        data = json.loads(raw)
        rows = data if isinstance(data, list) else data.get("data", [])
    else:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    results = []
    for row in rows:
        if row.get("symbol") and row.get("symbol") != symbol:
            continue
        desc = (row.get("desc") or "").lower()
        text = (row.get("attchmntText") or "").lower()
        if "financial result" in desc or "financial result" in text:
            dissem_str = row.get("exchdisstime") or row.get("an_dt") or ""
            dissem_dt = parse_nse_timestamp(dissem_str)
            results.append({
                "symbol": row.get("symbol") or symbol,
                "desc": row.get("desc"),
                "an_dt": row.get("an_dt"),
                "exchdisstime": row.get("exchdisstime"),
                "dissem_dt": dissem_dt,
                "has_xbrl": str(row.get("hasXbrl", "")).lower() == "true",
                "attachment_url": row.get("attchmntFile") or "",
            })
    return results


def extract_consolidated_eps_from_pdf(pdf_path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"usable": False, "reason": "pypdf not installed"}

    reader = PdfReader(str(pdf_path))
    full_text = "\n".join((p.extract_text() or "") for p in reader.pages)

    # Locate the Consolidated Financial Results table (preferring the one with EPS)
    m_hdr = re.search(
        r"CONSOLIDATED\s+FINANCIAL\s+RESULTS.*?(?=UNAUDITED\s+STANDALONE|AUDITED\s+STANDALONE|\Z)",
        full_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m_hdr:
        return {"usable": False, "reason": "No consolidated financial results section found"}

    cons_block = m_hdr.group(0)
    eps_idx = cons_block.lower().find("earnings per equity share")
    if eps_idx == -1:
        return {"usable": False, "reason": "No Earnings per equity share section in consolidated block"}

    # Look back slightly for the column header dates (e.g. 30 Sep'21 30 Jun'21 ...)
    window_start = max(0, eps_idx - 300)
    snippet = cons_block[window_start:eps_idx + 1200]

    date_matches = re.findall(r"\b\d{1,2}\s+[A-Za-z]{3}[’']\d{2}\b", snippet[:450])
    # Deduplicate preserving order if repeated
    periods = []
    for d in date_matches:
        d_norm = d.replace("’", "'")
        if d_norm not in periods:
            periods.append(d_norm)
        elif len(periods) >= 5:
            break

    def extract_line(pattern):
        m = re.search(pattern, snippet, re.IGNORECASE)
        if not m:
            return None
        nums = [float(x.replace(",", "")) for x in re.findall(r"-?\d+\.\d+", m.group(1))]
        if not nums:
            return None
        if periods and len(nums) == len(periods):
            return dict(zip(periods, nums))
        return {"unmapped_values": nums}

    basic_after = extract_line(r"\(a\.1\)\s*Basic[^\n]*After\s+Exceptional\s+Item\s+([^\n]+)")
    basic_before = extract_line(r"\(a\.2\)\s*Basic[^\n]*Before\s+Exceptional\s+Item\s+([^\n]+)")
    diluted_after = extract_line(r"\(b\.1\)\s*Diluted[^\n]*After\s+Exceptional\s+Item\s+([^\n]+)")
    diluted_before = extract_line(r"\(b\.2\)\s*Diluted[^\n]*Before\s+Exceptional\s+Item\s+([^\n]+)")

    if not any([basic_after, basic_before, diluted_after, diluted_before]):
        return {"usable": False, "reason": "Could not parse Basic/Diluted EPS lines"}

    return {
        "usable": True,
        "periods": periods,
        "basic_after_exceptional": basic_after,
        "basic_before_exceptional": basic_before,
        "diluted_after_exceptional": diluted_after,
        "diluted_before_exceptional": diluted_before,
    }


def fetch_live_nse(symbol="RELIANCE", cutoff_date="2021-10-29"):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def get_url(url):
        req = urllib.request.Request(url, headers=NSE_HEADERS)
        try:
            with opener.open(req, timeout=15) as resp:
                return {"ok": True, "status": resp.status, "body": resp.read().decode("utf-8", errors="replace")}
        except urllib.error.HTTPError as e:
            return {"ok": False, "status": e.code, "error": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"ok": False, "status": None, "error": str(e)}

    home = get_url("https://www.nseindia.com/")
    if not home["ok"]:
        return {"live_status": "blocked_or_unreachable", "detail": home}

    ann_url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={symbol}"
    ann_res = get_url(ann_url)
    return {
        "live_status": "ok" if ann_res["ok"] else "blocked_or_unavailable",
        "announcements_fetch": {k: v for k, v in ann_res.items() if k != "body"},
        "announcements_count": len(json.loads(ann_res["body"])) if ann_res["ok"] else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="RELIANCE PIT collector proof-of-concept")
    parser.add_argument("--bhavcopy", help="Path to NSE bhavcopy CSV")
    parser.add_argument("--announcements", help="Path to NSE announcements CSV/JSON")
    parser.add_argument("--pdf", action="append", help="Path(s) to financial results PDF to parse")
    parser.add_argument("--cutoff-date", default="2021-10-29", help="Month-end trading date (YYYY-MM-DD)")
    parser.add_argument("--live", action="store_true", help="Attempt live NSE fetch for RELIANCE")
    args = parser.parse_args()

    cutoff_dt = dt.datetime.combine(dt.date.fromisoformat(args.cutoff_date), MARKET_CLOSE_TIME)
    report = {"cutoff_ist": cutoff_dt.isoformat()}

    if args.live:
        report["live"] = fetch_live_nse("RELIANCE", args.cutoff_date)

    if args.bhavcopy:
        price_info = parse_bhavcopy(args.bhavcopy)
        report["price_found"] = price_info is not None
        report["price"] = price_info

    if args.announcements:
        anns = parse_announcements(args.announcements)
        report["financial_result_announcements_found"] = len(anns)
        report["announcements"] = [
            {
                "desc": a["desc"],
                "exchdisstime": a["exchdisstime"],
                "known_by_market_close": (a["dissem_dt"] is not None and a["dissem_dt"] <= cutoff_dt),
                "has_xbrl": a["has_xbrl"],
                "attachment_url": a["attachment_url"],
            }
            for a in anns
        ]

    if args.pdf:
        report["pdfs"] = [
            {"file": Path(p).name, **extract_consolidated_eps_from_pdf(p)}
            for p in args.pdf
        ]

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
