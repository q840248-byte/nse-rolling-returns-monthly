"""Monthly two-stage sweep for the NSE first-5-minute strategy.

WHAT THIS AUTOMATES
-------------------
The owner's manual workflow is:

    Stage 1 (universe screen)
        tokens.xlsx = ~2,500 stocks
        x=900000    analysis_days=185   filter_days=30
        trim=0.1    fixed_divisor=1     SR 1.4 -> 1.4
        end_date = D
        -> averages file; sort by "Total Trimmed Gain @ 1.4% / 1" desc; keep top 15

    Stage 2 (shortlist re-run)
        tokens.xlsx = those 15 stocks
        x=1         analysis_days=35    filter_days=1
        trim=0.1    fixed_divisor=1     SR 1.4 -> 1.4
        end_date = D + 1 month
        -> detailed file used for downstream analysis

Doing that by hand for many months means re-fetching ~2,500 symbols' worth of
5-minute candles every time. This script fetches once and then evaluates every
month in memory. Stage 1 for month D and stage 2 for month D cover different
windows, so both are sliced from the same day-level cache.

THE POINT OF THE DESIGN
-----------------------
Fetching is the only expensive part (~6 API calls per symbol). Everything after
that is pandas on one row per stock-day, so adding a month costs milliseconds.
Switching from 6 months to 24 months costs extra fetch time only, not 4x the
whole run.

OUTPUT LAYOUT
-------------
    <out>/2026-04-01/stage1_averages.xlsx
    <out>/2026-04-01/stage2_averages.xlsx
    <out>/2026-04-01/stage2_detailed.csv     <- same columns as the original run
    <out>/2026-04-01/run.json
    <out>/MASTER_picks.xlsx                  <- one row per month, top picks
    <out>/MASTER_stage2_detail.csv           <- all months stacked, Month column
    <out>/sweep_summary.json

Column names in stage2_detailed.csv are unchanged from High_5m.py so existing
downstream formulas keep working. MASTER_stage2_detail.csv only prepends one
extra `Month` column.

USAGE
-----
    python monthly_sweep.py --tokens tokens.xlsx \
        --start-month 2026-04-01 --end-month 2026-10-01

    # look before you leap
    python monthly_sweep.py --tokens tokens.xlsx \
        --start-month 2026-04-01 --end-month 2026-10-01 --plan

Requires kite_auth.py (providing `kite`) only when actually fetching, so the
offline test suite can import this module without credentials.

This module never contacts the network during tests; pass a fake client via
`run_sweep(..., make_kite=lambda: fake)`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd

try:  # python-dateutil is a declared dependency; keep an import-time guard anyway.
    from dateutil.relativedelta import relativedelta
except ImportError:  # pragma: no cover - dateutil is in requirements.txt
    relativedelta = None


# ============================================================================
# DEFAULTS — these reproduce the owner's two manual runs exactly
# ============================================================================

INTRADAY_INTERVAL = "5minute"
INTRADAY_CHUNK_DAYS = 99          # Kite allows 100 days per 5-minute request
DEFAULT_TRIM_PROP = 0.1
DEFAULT_FIXED_DIVISOR = 1
DEFAULT_THRESHOLD = 1.4
BUY_DAY_MIN_PCT = -3.88           # skip a trade if the buy day fell more than this %
MIN_LIQUID_FRACTION = 0.90        # >=90% of recent days must clear the turnover floor
DEFAULT_TOP_N = 15
DEFAULT_RATE_LIMIT = 3.0          # Kite historical + quote: 3 requests/second
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
LEAD_IN_DAYS = 10                 # fetched but not reported, so prev-close is always real

# Exceptions that will never succeed on retry.
NON_RETRYABLE = (
    "TokenException",
    "PermissionException",
    "AuthenticationException",
    "InputException",
    "OrderException",
    "NetworkException",
)


# ============================================================================
# SMALL HELPERS
# ============================================================================

def trim_mean_np(values: np.ndarray, proportion_to_cut: float) -> float:
    """Equivalent of scipy.stats.trim_mean, without the scipy dependency.

    scipy cuts ``int(n * proportiontocut)`` observations from each end. We match
    that so the turnover column stays identical to the original script's.
    """
    a = np.asarray(values, dtype=float)
    a = a[~np.isnan(a)]
    if a.size == 0:
        return float("nan")
    a = np.sort(a)
    npc = min(max(proportion_to_cut, 0.0), 0.5)
    k = int(math.floor(a.size * npc))
    if k == 0:
        return float(a.mean())
    if k * 2 >= a.size:
        return float(a.mean())
    return float(a[k:a.size - k].mean())


def trimmed_sum_divided(series: pd.Series, trim_prop: float, fixed_divisor: float) -> float:
    """Sum of the middle (1 - 2*trim_prop) of the values, divided by divisor.

    Deliberately keeps the original arithmetic, with one correction:

    The original used ``int(len(s) * trim_prop)`` and then ``s.iloc[trim_n:-trim_n]``.
    When ``len(s) < 10`` and ``trim_prop == 0.1``, ``trim_n`` is 0 and
    ``s.iloc[0:-0]`` is ``s.iloc[0:0]`` — an EMPTY slice, so the function
    returned NaN even though it had valid data. On a 35-day stage-2 window that
    silently blanks circuit-heavy or recently listed names. Here ``trim_n == 0``
    simply means "nothing to trim", which is the intent.
    """
    s = series.dropna().sort_values()
    if len(s) == 0:
        return float("nan")
    trim_n = int(len(s) * trim_prop)
    if trim_n <= 0:
        return float(s.sum() / fixed_divisor)
    if trim_n * 2 >= len(s):
        return float(s.sum() / fixed_divisor)
    trimmed = s.iloc[trim_n:-trim_n]
    if len(trimmed) == 0:
        return float("nan")
    return float(trimmed.sum() / fixed_divisor)


def build_thresholds(sr_start: float, sr_end: float, step: float = 0.1) -> list[float]:
    """Reproduce np.arange(sr_start, sr_end - 0.001, -step).round(2).tolist().

    Returns an empty list when sr_start < sr_end, matching numpy. Callers must
    warn, because an empty list silently produces an averages file with no gain
    column at all — which is easy to misread as "no stock scored".
    """
    return [float(v) for v in np.arange(sr_start, sr_end - 0.001, -step).round(2).tolist()]


def _to_naive(series: pd.Series) -> pd.Series:
    """Convert an ISO date column to naive datetimes, tolerating tz-aware input."""
    s = pd.to_datetime(series)
    try:
        if getattr(s.dt, "tz", None) is not None:
            return s.dt.tz_localize(None)
    except (AttributeError, TypeError):  # pragma: no cover - defensive
        pass
    return s


def add_months(d: date, months: int) -> date:
    if relativedelta is None:  # pragma: no cover - declared dependency
        raise RuntimeError("python-dateutil is required for month arithmetic")
    return d + relativedelta(months=months)


def month_series(start: date, end: date, step_months: int = 1) -> list[date]:
    """Inclusive list of month-start dates, e.g. 04-01 .. 10-01."""
    if step_months < 1:
        raise ValueError("step_months must be >= 1")
    if end < start:
        raise ValueError("end month is before start month")
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = add_months(cur, step_months)
    return out


class RateLimiter:
    """Global request pacer. Kite allows 3 requests/second across all endpoints.

    The original script used a bare Semaphore(3) with ThreadPoolExecutor(3),
    which caps concurrency but not rate — three threads can fire 50 requests in
    a burst and trigger 429s, which then get retried with a 2s sleep. Pacing is
    both safer and, in practice, faster overall.
    """

    def __init__(self, max_per_second: float):
        self._interval = 1.0 / float(max_per_second) if max_per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next = time.monotonic()

    def acquire(self) -> None:
        if self._interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next = max(now, self._next) + self._interval


def _is_retryable(exc: BaseException) -> bool:
    return type(exc).__name__ not in NON_RETRYABLE


def api_call_with_retry(func: Callable[..., Any], *args, retries: int = DEFAULT_RETRIES,
                        delay: float = DEFAULT_RETRY_DELAY, limiter: RateLimiter | None = None,
                        **kwargs) -> Any:
    last: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            if limiter is not None:
                limiter.acquire()
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last = exc
            if not _is_retryable(exc) or attempt == retries:
                raise
            time.sleep(delay)
    assert last is not None
    raise last


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class StageParams:
    """One stage's arithmetic. Mirrors one manual run of High_5m.py."""
    analysis_days: int
    min_turnover: float
    filter_days: int
    trim_prop: float = DEFAULT_TRIM_PROP
    fixed_divisor: float = DEFAULT_FIXED_DIVISOR
    thresholds: list[float] = field(default_factory=lambda: [DEFAULT_THRESHOLD])
    buy_day_min_pct: float = BUY_DAY_MIN_PCT
    min_liquid_fraction: float = MIN_LIQUID_FRACTION

    def window_start(self, end: date) -> date:
        return end - timedelta(days=self.analysis_days)


@dataclass
class SweepConfig:
    tokens_path: str
    out_dir: str
    months: list[date]
    stage1: StageParams
    stage2: StageParams
    stage2_lag_months: int = 1
    top_n: int = DEFAULT_TOP_N
    interval: str = INTRADAY_INTERVAL
    chunk_days: int = INTRADAY_CHUNK_DAYS
    max_workers: int = 4
    rate_limit: float = DEFAULT_RATE_LIMIT
    retries: int = DEFAULT_RETRIES
    retry_delay: float = DEFAULT_RETRY_DELAY
    cache_dir: str | None = None
    legacy_drop_first_day: bool = True
    limit_symbols: int | None = None
    today: date | None = None

    def stage2_end(self, month: date) -> date:
        return add_months(month, self.stage2_lag_months)


# ============================================================================
# PER-SYMBOL DATA BUILD  (the only network-facing code)
# ============================================================================

def build_day_frame(daily_records: Sequence[dict], intraday_records: Sequence[dict]
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reduce one symbol's raw candles to one row per trading day.

    Returns ``(days, closes)``:
      days   — merged frame carrying every column the detail CSV needs.
      closes — daily closes keyed by date_only, used for the Price column.

    Column order matches High_5m.py's df_merge so downstream excel formulas on
    the detailed file keep working.
    """
    if not daily_records or len(daily_records) < 2:
        raise ValueError("no daily data")
    if not intraday_records:
        raise ValueError("no intraday data")

    daily = pd.DataFrame(daily_records)
    daily["date"] = _to_naive(daily["date"])
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["date_only"] = daily["date"].dt.date

    # BUY-BLOCKED day: high == close or low == close (circuit / locked price).
    daily["entry_blocked"] = (
        (daily["high"] == daily["close"]) | (daily["low"] == daily["close"])
    ).astype(int)
    daily["daily_pct_change"] = daily["close"].pct_change() * 100

    aligned = daily[["date_only", "close", "entry_blocked", "daily_pct_change"]].copy()
    aligned["close_prev_day"] = aligned["close"].shift(1)
    aligned["entry_blocked_prev_day"] = aligned["entry_blocked"].shift(1)
    aligned["Buy Day % Chng"] = aligned["daily_pct_change"].shift(1)
    closes = daily[["date_only", "close"]].rename(columns={"close": "daily_close"}).copy()

    intra = pd.DataFrame(intraday_records)
    intra["date"] = _to_naive(intra["date"])
    intra["date_only"] = intra["date"].dt.date
    intra = intra.sort_values("date")
    first5 = intra.groupby("date_only", sort=True).first().reset_index()

    merged = pd.merge(
        first5,
        aligned[["date_only", "close_prev_day", "entry_blocked_prev_day", "Buy Day % Chng"]],
        on="date_only",
        how="inner",
    )
    merged = merged.dropna(subset=["open", "close_prev_day"]).reset_index(drop=True)
    if merged.empty:
        raise ValueError("no overlapping intraday/daily days")

    merged["entry_blocked_prev_day"] = merged["entry_blocked_prev_day"].fillna(0).astype(int)
    merged["Turnover (5m)"] = merged["volume"] * ((merged["high"] + merged["low"]) / 2)
    merged["%open"] = ((merged["open"] - merged["close_prev_day"]) / merged["close_prev_day"]) * 100
    merged["%high"] = ((merged["high"] - merged["close_prev_day"]) / merged["close_prev_day"]) * 100
    merged["%close"] = ((merged["close"] - merged["close_prev_day"]) / merged["close_prev_day"]) * 100
    return merged, closes


def fetch_symbol(kite, row: pd.Series, fetch_start: date, fetch_end: date,
                 interval: str, chunk_days: int, limiter: RateLimiter,
                 retries: int, retry_delay: float) -> tuple[pd.DataFrame | None, pd.DataFrame | None, str | None]:
    """Download and reduce one symbol. Returns (days, closes, error)."""
    token = int(row["instrument_token"])
    try:
        daily = api_call_with_retry(
            kite.historical_data, token, fetch_start, fetch_end, "day", False,
            retries=retries, delay=retry_delay, limiter=limiter,
        )
        intraday: list[dict] = []
        chunk_start = fetch_start
        while chunk_start <= fetch_end:
            chunk_end = min(chunk_start + timedelta(days=chunk_days), fetch_end)
            part = api_call_with_retry(
                kite.historical_data, token, chunk_start, chunk_end, interval, False,
                retries=retries, delay=retry_delay, limiter=limiter,
            )
            intraday.extend(part or [])
            chunk_start = chunk_end + timedelta(days=1)
        days, closes = build_day_frame(daily or [], intraday)
        return days, closes, None
    except Exception as exc:  # noqa: BLE001 - reported per symbol
        return None, None, str(exc)


def fetch_universe(cfg: SweepConfig, kite, df_input: pd.DataFrame,
                   fetch_start: date, fetch_end: date,
                   log: Callable[[str], None]
                   ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Fetch every symbol once.

    Returns ``(frames, failures)`` where frames maps symbol -> {"days","closes"}.
    Uses an on-disk cache when configured.
    """
    cache: dict[str, dict[str, Any]] = {}
    cache_dir = cfg.cache_dir
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    def cache_path(sym: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in sym)
        return os.path.join(cache_dir or "", f"{safe}.pkl")

    rows = list(df_input.iterrows())
    if cfg.limit_symbols:
        rows = rows[:cfg.limit_symbols]

    pending: list[tuple[str, pd.Series]] = []
    reused = 0
    for _, row in rows:
        sym = str(row["tradingsymbol"])
        if cache_dir and os.path.exists(cache_path(sym)):
            try:
                with open(cache_path(sym), "rb") as fh:
                    cache[sym] = pickle.load(fh)
                reused += 1
                continue
            except Exception:  # pragma: no cover - corrupt cache entry
                pass
        pending.append((sym, row))

    if reused:
        log(f"  cache: {reused} symbol(s) reused from {cache_dir}")
    total = len(pending)
    if total == 0:
        return cache, {}

    limiter = RateLimiter(cfg.rate_limit)
    done = 0
    failures: dict[str, str] = {}
    started = time.time()

    def flush(sym: str, payload: dict[str, Any]) -> None:
        if not cache_dir:
            return
        try:
            with open(cache_path(sym), "wb") as fh:
                pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:  # pragma: no cover - disk issues must not kill the run
            log(f"  ! cache write failed for {sym}: {exc}")

    log(f"  fetching {total} symbol(s), {cfg.rate_limit:g} req/s — this is the slow part")
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
        futures = {
            pool.submit(
                fetch_symbol, kite, row, fetch_start, fetch_end,
                cfg.interval, cfg.chunk_days, limiter, cfg.retries, cfg.retry_delay,
            ): sym
            for sym, row in pending
        }
        for future in as_completed(futures):
            sym = futures[future]
            days, closes, err = future.result()
            done += 1
            if err is None and days is not None and closes is not None:
                payload = {"days": days, "closes": closes}
                cache[sym] = payload
                flush(sym, payload)
            else:
                failures[sym] = err or "unknown"
            if done % 25 == 0 or done == total:
                elapsed = time.time() - started
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                sys.stdout.write(
                    f"\r  fetched {done}/{total}  ({len(failures)} failed)  "
                    f"ETA {eta/60:.1f} min   "
                )
                sys.stdout.flush()
    sys.stdout.write("\n")
    if failures:
        log(f"  {len(failures)} symbol(s) had no usable data")
    return cache, failures


# ============================================================================
# STAGE EVALUATION  (pure pandas, no network)
# ============================================================================

def slice_window(days: pd.DataFrame, start: date, end: date,
                 drop_first: bool = True) -> pd.DataFrame:
    """Rows inside [start, end].

    ``drop_first`` reproduces the original behaviour: each run's first day had a
    NaN previous close and was dropped. Prev closes here come from a longer
    series, so the value exists; dropping the row keeps the two runs identical
    rather than silently gaining one extra day per window.
    """
    mask = (days["date_only"] >= start) & (days["date_only"] <= end)
    window = days.loc[mask].sort_values("date_only")
    if drop_first and not window.empty:
        window = window.iloc[1:]
    return window.reset_index(drop=True)


def liquidity_ok(window: pd.DataFrame, params: StageParams, end: date) -> tuple[bool, str]:
    cutoff = end - timedelta(days=params.filter_days)
    recent = window.loc[window["date_only"] >= cutoff, "Turnover (5m)"]
    if len(recent) == 0:
        return True, ""
    low = int((recent < params.min_turnover).sum())
    total = int(len(recent))
    # Count in integers. The original compared float fractions, and because
    # 1 - 0.90 evaluates to 0.09999999999999998, a stock failing exactly 10% of
    # recent days (1 of 10) failed the test that was supposed to allow it.
    allowed = int(total * (1 - params.min_liquid_fraction) + 1e-9)
    if low > allowed:
        return False, (
            f"low turnover on {low}/{total} recent days "
            f"(allowed: {allowed})"
        )
    return True, ""


def capped_gain_frame(df_all: pd.DataFrame, threshold: float,
                      params: StageParams) -> pd.Series:
    """Daily recorded gain for one target threshold. Mirrors the original exactly.

    * open below target:  +threshold if the day's high touched it, else the close
    * open above target:  the open if the open was the day's high, else threshold
    * invalid day        : NaN
    """
    valid = (
        (df_all["entry_blocked_prev_day"] == 0)
        & (df_all["Buy Day % Chng"].isna() | (df_all["Buy Day % Chng"] >= params.buy_day_min_pct))
    )
    less_than_open = np.where(df_all["%high"] >= threshold, threshold, df_all["%close"])
    open_above = np.where(df_all["%high"] > df_all["%open"], df_all["%open"], threshold)
    capped = np.where(df_all["%open"] > threshold, open_above, less_than_open)
    return pd.Series(np.where(valid, capped, np.nan), index=df_all.index, dtype=float)


def evaluate_stage(frames: dict[str, dict[str, Any]], symbols: Iterable[str],
                   params: StageParams, end: date, metadata: pd.DataFrame,
                   drop_first: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Run one stage over the cached day frames.

    Returns (averages, detail, skipped). ``averages`` has the original columns;
    ``detail`` has the original detail columns with Symbol first.
    """
    start = params.window_start(end)
    pieces: list[pd.DataFrame] = []
    skipped: dict[str, str] = {}
    price_by_symbol: dict[str, float] = {}

    for sym in symbols:
        payload = frames.get(sym)
        if payload is None:
            skipped[sym] = "no cached data"
            continue
        window = slice_window(payload["days"], start, end, drop_first=drop_first)
        if window.empty:
            skipped[sym] = "no trading days in window"
            continue
        ok, reason = liquidity_ok(window, params, end)
        if not ok:
            skipped[sym] = reason
            continue
        window = window.copy()
        window.insert(0, "Symbol", sym)
        pieces.append(window)

        closes = payload["closes"]
        in_window = closes.loc[
            (closes["date_only"] >= start) & (closes["date_only"] <= end)
        ]
        if not in_window.empty:
            price_by_symbol[sym] = float(in_window.iloc[-1]["daily_close"])

    detail = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    if detail.empty:
        return pd.DataFrame(), detail, skipped

    actually_traded = detail[
        (detail["entry_blocked_prev_day"] == 0)
        & (detail["Buy Day % Chng"].isna() | (detail["Buy Day % Chng"] >= params.buy_day_min_pct))
    ]
    valid_days = (
        actually_traded.groupby("Symbol")["date_only"]
        .count()
        .reset_index(name="Total Valid Trading Days")
    )

    turnover_col = f"Turnover (5m) - {params.filter_days}d Avg"
    cutoff = end - timedelta(days=params.filter_days)
    recent = detail[detail["date_only"] >= cutoff]
    if recent.empty:
        summary = pd.DataFrame({"Symbol": sorted(detail["Symbol"].unique())})
        summary[turnover_col] = np.nan
    else:
        summary = (
            recent.groupby("Symbol")
            .agg(**{turnover_col: ("Turnover (5m)", lambda s: trim_mean_np(s.to_numpy(), params.trim_prop))})
            .reset_index()
        )
    summary = pd.merge(summary, valid_days, on="Symbol", how="left")

    for threshold in params.thresholds:
        scored = pd.DataFrame({
            "Symbol": detail["Symbol"].to_numpy(),
            "gain": capped_gain_frame(detail, threshold, params).to_numpy(),
        })
        per_symbol = {
            sym: trimmed_sum_divided(sub["gain"], params.trim_prop, params.fixed_divisor)
            for sym, sub in scored.groupby("Symbol")
        }
        col = f"Total Trimmed Gain @ {threshold}% / {params.fixed_divisor}"
        summary[col] = summary["Symbol"].map(per_symbol)

    meta = metadata[["tradingsymbol", "instrument_token", "exchange"]].drop_duplicates("tradingsymbol")
    summary = pd.merge(summary, meta, left_on="Symbol", right_on="tradingsymbol", how="left")
    summary["Price"] = summary["Symbol"].map(price_by_symbol)

    leading = ["instrument_token", "exchange", "Symbol", "Price", "Total Valid Trading Days"]
    trailing = [c for c in summary.columns if c not in leading and c != "tradingsymbol"]
    summary = summary[leading + trailing]
    return summary, detail, skipped


def rank_symbols(averages: pd.DataFrame, threshold: float, fixed_divisor: float,
                 top_n: int) -> tuple[list[str], float | None]:
    """Sort high->low on the gain column and take the top N, dropping blanks."""
    col = f"Total Trimmed Gain @ {threshold}% / {fixed_divisor}"
    if averages.empty or col not in averages.columns:
        return [], None
    ranked = averages.dropna(subset=[col]).sort_values(col, ascending=False)
    picks = ranked.head(top_n)
    if picks.empty:
        return [], None
    cutoff = float(picks[col].iloc[-1])
    return picks["Symbol"].tolist(), cutoff


# ============================================================================
# OUTPUT
# ============================================================================

def write_table(df: pd.DataFrame, stem: str) -> str:
    """Write .xlsx when openpyxl is available, otherwise fall back to .csv."""
    try:
        import openpyxl  # noqa: F401
        path = f"{stem}.xlsx"
        df.to_excel(path, index=False)
        return path
    except ImportError:
        path = f"{stem}.csv"
        df.to_csv(path, index=False)
        return path


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"not JSON serialisable: {type(obj)!r}")


# ============================================================================
# ORCHESTRATION
# ============================================================================

def _sniff_separator(path: str) -> str:
    """Pick tab vs comma from the header line.

    Kite's own instrument dump is tab-separated, and the owner's tokens file is
    usually pasted from one — often saved with a .csv or .txt extension. Sniffing
    the header avoids a "missing column" error that looks like a schema problem.
    """
    if path.lower().endswith(".tsv"):
        return "\t"
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as fh:
            header = fh.readline()
    except OSError:
        return ","
    return "\t" if header.count("\t") > header.count(",") else ","


def load_tokens(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, sep=_sniff_separator(path))
    df.columns = [str(c).strip() for c in df.columns]
    missing = {"instrument_token", "exchange", "tradingsymbol"} - set(df.columns)
    if missing:
        raise ValueError(f"tokens file is missing column(s): {sorted(missing)}")
    for col in ("tradingsymbol", "exchange"):
        df[col] = df[col].astype(str).str.strip()
    df["instrument_token"] = df["instrument_token"].astype("int64")
    return df


def plan_windows(cfg: SweepConfig) -> pd.DataFrame:
    """Show every stage window without touching the network."""
    rows = []
    today = cfg.today or date.today()
    for month in cfg.months:
        s1_end = month
        s1_start = cfg.stage1.window_start(s1_end)
        s2_end = cfg.stage2_end(month)
        s2_start = cfg.stage2.window_start(s2_end)
        rows.append({
            "Month": month,
            "Stage1": f"{s1_start} -> {s1_end}",
            "Stage2": f"{s2_start} -> {s2_end}",
            "Stage2 complete?": "yes" if s2_end <= today else "NOT YET — partial",
        })
    return pd.DataFrame(rows)


def run_sweep(cfg: SweepConfig, make_kite: Callable[[], Any] | None = None,
              log: Callable[[str], None] = print) -> dict[str, Any]:
    """Fetch once, then evaluate every month's two stages."""
    if not cfg.stage1.thresholds:
        log("⚠ Threshold list is empty (sr_start must be >= sr_end). "
            "No gain column will be produced.")
    if not cfg.stage2.thresholds:
        log("⚠ Stage-2 threshold list is empty. No gain column will be produced.")

    df_input = load_tokens(cfg.tokens_path)
    log(f"Universe: {len(df_input)} symbol(s) from {cfg.tokens_path}")

    months = cfg.months
    fetch_start = min(cfg.stage1.window_start(m) for m in months) - timedelta(days=LEAD_IN_DAYS)
    fetch_end = max(cfg.stage2_end(m) for m in months)
    log(f"Fetch range: {fetch_start} -> {fetch_end} (one pass, all months)")

    frames, failures = fetch_universe(cfg, make_kite(), df_input, fetch_start, fetch_end, log)
    if not frames:
        raise RuntimeError("no symbol produced usable data; nothing to evaluate")
    log(f"Cached day frames for {len(frames)} symbol(s)")

    metadata = df_input[["tradingsymbol", "instrument_token", "exchange"]].drop_duplicates("tradingsymbol")
    os.makedirs(cfg.out_dir, exist_ok=True)
    today = cfg.today or date.today()
    universe = list(frames.keys())

    master_picks: list[pd.DataFrame] = []
    master_detail: list[pd.DataFrame] = []
    month_reports: list[dict[str, Any]] = []

    for month in months:
        month_dir = os.path.join(cfg.out_dir, month.isoformat())
        os.makedirs(month_dir, exist_ok=True)
        stage2_end = cfg.stage2_end(month)
        log(f"\n=== {month} ===  stage2 window ends {stage2_end}")

        stage1_avg, stage1_detail, stage1_skipped = evaluate_stage(
            frames, universe, cfg.stage1, month, metadata,
            drop_first=cfg.legacy_drop_first_day,
        )
        s1_path = write_table(stage1_avg, os.path.join(month_dir, "stage1_averages"))
        picks, cutoff = rank_symbols(
            stage1_avg, cfg.stage1.thresholds[-1] if cfg.stage1.thresholds else DEFAULT_THRESHOLD,
            cfg.stage1.fixed_divisor, cfg.top_n,
        )
        log(f"  stage 1: {len(stage1_avg)} symbol(s) scored, "
            f"{len(stage1_skipped)} skipped -> {os.path.basename(s1_path)}")
        log(f"  top {len(picks)}: {', '.join(picks) if picks else '(none)'}")

        stage2_avg = pd.DataFrame()
        stage2_detail = pd.DataFrame()
        stage2_skipped: dict[str, str] = {}
        partial = stage2_end > today
        if picks:
            if partial:
                log(f"  ⚠ stage 2 ends {stage2_end}, after today ({today}); "
                    "these numbers are incomplete")
            stage2_avg, stage2_detail, stage2_skipped = evaluate_stage(
                frames, picks, cfg.stage2, stage2_end, metadata,
                drop_first=cfg.legacy_drop_first_day,
            )
            write_table(stage2_avg, os.path.join(month_dir, "stage2_averages"))
            if not stage2_detail.empty:
                stage2_detail.to_csv(os.path.join(month_dir, "stage2_detailed.csv"), index=False)
                stacked = stage2_detail.copy()
                stacked.insert(0, "Month", month.isoformat())
                master_detail.append(stacked)
            log(f"  stage 2: {len(stage2_avg)} symbol(s) scored, "
                f"{len(stage2_detail)} detail row(s)")

        if not stage2_avg.empty:
            pick_col = (f"Total Trimmed Gain @ {cfg.stage2.thresholds[-1]}% / "
                        f"{cfg.stage2.fixed_divisor}")
            picked = stage2_avg.copy()
            if pick_col in picked.columns:
                # Rank within the month the same way the owner sorts by hand:
                # high -> low on the gain column, blanks last.
                picked = picked.sort_values(pick_col, ascending=False, na_position="last")
            picked = picked.reset_index(drop=True)
            picked.insert(0, "Month", month.isoformat())
            picked.insert(1, "Rank", range(1, len(picked) + 1))
            master_picks.append(picked)
            if pick_col in picked.columns:
                best = picked.dropna(subset=[pick_col]).head(1)
                if not best.empty:
                    log(f"  stage 2 leader: {best.iloc[0]['Symbol']} "
                        f"@ {best.iloc[0][pick_col]:.2f}")

        report = {
            "month": month.isoformat(),
            "stage1_window": [cfg.stage1.window_start(month).isoformat(), month.isoformat()],
            "stage2_window": [cfg.stage2.window_start(stage2_end).isoformat(), stage2_end.isoformat()],
            "stage2_complete": not partial,
            "stage1_scored": int(len(stage1_avg)),
            "stage1_skipped": stage1_skipped,
            "selection_cutoff": cutoff,
            "picks": picks,
            "stage2_scored": int(len(stage2_avg)),
            "stage2_skipped": stage2_skipped,
            "stage2_detail_rows": int(len(stage2_detail)),
            "stage1_params": asdict(cfg.stage1),
            "stage2_params": asdict(cfg.stage2),
        }
        month_reports.append(report)
        with open(os.path.join(month_dir, "run.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=_json_default)

    if master_picks:
        combined = pd.concat(master_picks, ignore_index=True)
        path = write_table(combined, os.path.join(cfg.out_dir, "MASTER_picks"))
        log(f"\n✅ {path}")
    if master_detail:
        combined_detail = pd.concat(master_detail, ignore_index=True)
        path = os.path.join(cfg.out_dir, "MASTER_stage2_detail.csv")
        combined_detail.to_csv(path, index=False)
        log(f"✅ {path}  ({len(combined_detail):,} rows, {len(months)} month(s))")

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tokens_file": os.path.abspath(cfg.tokens_path),
        "months": [m.isoformat() for m in months],
        "fetch_range": [fetch_start.isoformat(), fetch_end.isoformat()],
        "symbols_requested": int(len(df_input)),
        "symbols_with_data": int(len(frames)),
        "fetch_failures": failures,
        "config": {
            "top_n": cfg.top_n,
            "stage2_lag_months": cfg.stage2_lag_months,
            "interval": cfg.interval,
            "rate_limit": cfg.rate_limit,
            "legacy_drop_first_day": cfg.legacy_drop_first_day,
            "stage1": asdict(cfg.stage1),
            "stage2": asdict(cfg.stage2),
        },
        "months_detail": month_reports,
    }
    with open(os.path.join(cfg.out_dir, "sweep_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=_json_default)
    log(f"✅ {os.path.join(cfg.out_dir, 'sweep_summary.json')}")
    return summary


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run the two-stage first-5-minute screen for many months at once.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--tokens", default="tokens.xlsx", help="tokens.xlsx (or .csv/.tsv)")
    p.add_argument("--out", default="sweeps", help="output root directory")
    p.add_argument("--start-month", required=True, help="first month-end date, e.g. 2026-04-01")
    p.add_argument("--end-month", help="last month-end date (default: start month)")
    p.add_argument("--step-months", type=int, default=1)
    p.add_argument("--plan", action="store_true", help="print the month windows and exit")

    s1 = p.add_argument_group("stage 1 (universe screen)")
    s1.add_argument("--s1-days", type=int, default=185)
    s1.add_argument("--s1-turnover", type=float, default=900000.0)
    s1.add_argument("--s1-filter-days", type=int, default=30)

    s2 = p.add_argument_group("stage 2 (shortlist re-run)")
    s2.add_argument("--s2-days", type=int, default=35)
    s2.add_argument("--s2-turnover", type=float, default=1.0)
    s2.add_argument("--s2-filter-days", type=int, default=1)
    s2.add_argument("--s2-lag-months", type=int, default=1,
                    help="how far after the month stage 2 ends")

    g = p.add_argument_group("shared arithmetic")
    g.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    g.add_argument("--trim", type=float, default=DEFAULT_TRIM_PROP)
    g.add_argument("--divisor", type=float, default=DEFAULT_FIXED_DIVISOR)
    g.add_argument("--sr-start", type=float, default=DEFAULT_THRESHOLD)
    g.add_argument("--sr-end", type=float, default=DEFAULT_THRESHOLD)
    g.add_argument("--buy-day-min", type=float, default=BUY_DAY_MIN_PCT)

    f = p.add_argument_group("fetching")
    f.add_argument("--workers", type=int, default=4)
    f.add_argument("--rate-limit", type=float, default=DEFAULT_RATE_LIMIT)
    f.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    f.add_argument("--cache-dir", default=".sweep_cache", help="reuse fetched candles across runs")
    f.add_argument("--no-cache", action="store_true")
    f.add_argument("--limit-symbols", type=int, default=None, help="debug: only the first N symbols")
    f.add_argument("--keep-first-day", action="store_true",
                   help="do NOT drop the first day of each window")
    return p


def config_from_args(args: argparse.Namespace) -> SweepConfig:
    start = datetime.strptime(args.start_month, "%Y-%m-%d").date()
    end = datetime.strptime(args.end_month, "%Y-%m-%d").date() if args.end_month else start
    months = month_series(start, end, args.step_months)
    thresholds = build_thresholds(args.sr_start, args.sr_end)
    if not thresholds:
        thresholds = [args.sr_start]
    common = dict(trim_prop=args.trim, fixed_divisor=args.divisor, thresholds=thresholds,
                  buy_day_min_pct=args.buy_day_min)
    return SweepConfig(
        tokens_path=args.tokens,
        out_dir=args.out,
        months=months,
        stage1=StageParams(analysis_days=args.s1_days, min_turnover=args.s1_turnover,
                           filter_days=args.s1_filter_days, **common),
        stage2=StageParams(analysis_days=args.s2_days, min_turnover=args.s2_turnover,
                           filter_days=args.s2_filter_days, **common),
        stage2_lag_months=args.s2_lag_months,
        top_n=args.top,
        max_workers=args.workers,
        rate_limit=args.rate_limit,
        retries=args.retries,
        cache_dir=None if args.no_cache else args.cache_dir,
        legacy_drop_first_day=not args.keep_first_day,
        limit_symbols=args.limit_symbols,
    )


def _load_kite() -> Any:
    """Import kite_auth lazily so importing this module never needs credentials."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (here, os.path.abspath(os.path.join(here, os.pardir))):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    try:
        from kite_auth import kite  # noqa: PLC0415
    except ImportError:
        print("⚠ kite_auth.py not found. It must expose an authenticated `kite` object.")
        print(f"  Looked in: {here} and {os.path.abspath(os.path.join(here, os.pardir))}")
        raise SystemExit(1)
    return kite


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config_from_args(args)
    if args.plan:
        print(plan_windows(cfg).to_string(index=False))
        return 0
    run_sweep(cfg, make_kite=_load_kite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
