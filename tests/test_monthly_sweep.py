"""Offline regression tests for monthly_sweep. No network, no credentials.

The point of these tests is *equivalence*: the sweep must reproduce what the
owner gets by running High_5m.py twice per month. The original arithmetic is
copied verbatim below (``legacy_*`` helpers) and compared against the sweep
implementation on identical fixtures.

The fake Kite client counts requests, so the "one fetch, many months" claim and
the rate pacer are both measurable rather than asserted.
"""
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import monthly_sweep as ms

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Original implementation, copied from High_5m.py (unmodified intent)
# ---------------------------------------------------------------------------

def legacy_trimmed_sum_divided(s, trim_prop, fixed_divisor):
    s = s.dropna().sort_values()
    if len(s) == 0:
        return np.nan
    trim_n = int(len(s) * trim_prop)
    if trim_n * 2 >= len(s):
        return s.sum() / fixed_divisor
    trimmed = s.iloc[trim_n:-trim_n]
    return trimmed.sum() / fixed_divisor if len(trimmed) > 0 else np.nan


def legacy_capped_gain(df_all, t):
    valid_trades = (
        (df_all["entry_blocked_prev_day"] == 0) &
        (df_all["Buy Day % Chng"].isna() | (df_all["Buy Day % Chng"] >= -3.88))
    )
    less_than_open_logic = np.where(df_all["%high"] >= t, t, df_all["%close"])
    open_above_target_logic = np.where(df_all["%high"] > df_all["%open"], df_all["%open"], t)
    capped_gain_col = np.where(df_all["%open"] > t, open_above_target_logic, less_than_open_logic)
    return np.where(valid_trades, capped_gain_col, np.nan)


def legacy_trim_mean(values, proportion_to_cut):
    from scipy.stats import trim_mean  # optional; guarded by caller
    return trim_mean(values, proportion_to_cut)


# ---------------------------------------------------------------------------
# Fake broker
# ---------------------------------------------------------------------------

class FakeKite:
    """Minimal stand-in for the Kite Connect client.

    Returns deterministic random-walk candles so screens produce spread.
    """

    def __init__(self, seed=7, fail_symbols=(), requests_log=None):
        self.seed = seed
        self.fail_symbols = set(fail_symbols)
        self.requests_log = requests_log if requests_log is not None else []

    def _series(self, token, start, end):
        rng = np.random.RandomState(self.seed + int(token) % 1000)
        days = pd.bdate_range(start, end)
        if len(days) == 0:
            return days, []
        steps = rng.normal(0.0015, 0.022, len(days))
        closes = 100 * np.cumprod(1 + steps)
        return days, closes

    def historical_data(self, token, start, end, interval, oi=False, **kwargs):
        self.requests_log.append((token, str(start), str(end), interval))
        if int(token) in self.fail_symbols:
            raise RuntimeError("boom")
        start_d = pd.Timestamp(start).date()
        end_d = pd.Timestamp(end).date()
        days, closes = self._series(token, start_d, end_d)
        rng = np.random.RandomState(self.seed + int(token) % 1000 + len(self.requests_log))
        records = []
        if interval == "day":
            for d, c in zip(days, closes):
                prev = c
                o = c * (1 + rng.normal(0, 0.004))
                h = max(o, c) * (1 + abs(rng.normal(0, 0.008)))
                lo = min(o, c) * (1 - abs(rng.normal(0, 0.008)))
                records.append({"date": d, "open": float(o), "high": float(h),
                                "low": float(lo), "close": float(c), "volume": int(rng.randint(1e4, 1e6))})
            return records
        # intraday: 75 candles per session, stamped in IST-ish naive local time
        for d, c in zip(days, closes):
            for k in range(75):
                stamp = datetime(d.year, d.month, d.day, 9, 15) + timedelta(minutes=5 * k)
                drift = c * (1 + rng.normal(0, 0.006))
                o = drift * (1 + rng.normal(0, 0.001))
                h = max(o, drift) * (1 + abs(rng.normal(0, 0.002)))
                lo = min(o, drift) * (1 - abs(rng.normal(0, 0.002)))
                records.append({"date": stamp, "open": float(o), "high": float(h),
                                "low": float(lo), "close": float(drift),
                                "volume": int(rng.randint(100, 400))})
        return records


def write_tokens(path, n=6):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    df = pd.DataFrame({
        "instrument_token": [1000 + i for i in range(n)],
        "exchange": ["NSE"] * n,
        "tradingsymbol": [f"SYM{i:02d}" for i in range(n)],
    })
    df.to_csv(path, index=False)
    return df


def make_cfg(tmp, months, n_symbols=6, **overrides):
    tokens = os.path.join(tmp, "tokens.csv")
    write_tokens(tokens, n_symbols)
    cfg = ms.SweepConfig(
        tokens_path=tokens,
        out_dir=os.path.join(tmp, "out"),
        months=months,
        stage1=ms.StageParams(analysis_days=120, min_turnover=1.0, filter_days=30),
        stage2=ms.StageParams(analysis_days=35, min_turnover=1.0, filter_days=1),
        rate_limit=0,          # no sleeping in tests
        cache_dir=None,
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TrimmedSumTests(unittest.TestCase):
    def test_matches_original_when_enough_observations(self):
        series = pd.Series(np.random.RandomState(3).uniform(-3, 1.4, 200))
        self.assertAlmostEqual(
            ms.trimmed_sum_divided(series, 0.1, 1),
            legacy_trimmed_sum_divided(series, 0.1, 1),
            places=10,
        )

    def test_matches_original_for_small_samples_above_threshold(self):
        for n in (10, 11, 21):
            series = pd.Series(np.arange(n, dtype=float))
            self.assertAlmostEqual(
                ms.trimmed_sum_divided(series, 0.1, 1),
                legacy_trimmed_sum_divided(series, 0.1, 1),
                places=10,
            )

    def test_small_sample_nan_bug_is_fixed(self):
        """The original returned NaN for <10 trades at trim=0.1 (iloc[0:-0] == empty)."""
        for n in (1, 3, 5, 9):
            series = pd.Series([1.4] * n)
            self.assertTrue(np.isnan(legacy_trimmed_sum_divided(series, 0.1, 1)),
                            msg="fixture should reproduce the original bug")
            self.assertAlmostEqual(ms.trimmed_sum_divided(series, 0.1, 1), 1.4 * n)

    def test_divisor_applies(self):
        series = pd.Series(np.full(20, 2.0))
        self.assertAlmostEqual(ms.trimmed_sum_divided(series, 0.1, 4), (2.0 * 16) / 4)

    def test_all_nan_returns_nan(self):
        self.assertTrue(np.isnan(ms.trimmed_sum_divided(pd.Series([np.nan, np.nan]), 0.1, 1)))


class TrimMeanTests(unittest.TestCase):
    def test_matches_scipy(self):
        try:
            from scipy.stats import trim_mean
        except ImportError:  # pragma: no cover
            self.skipTest("scipy not installed")
        rng = np.random.RandomState(11)
        values = rng.uniform(1e5, 5e6, 400)
        for prop in (0.0, 0.05, 0.1, 0.25):
            self.assertAlmostEqual(ms.trim_mean_np(values, prop), trim_mean(values, prop), places=6)

    def test_nan_is_ignored(self):
        self.assertAlmostEqual(ms.trim_mean_np(np.array([np.nan, 1.0, 2.0, 3.0]), 0.0), 2.0)


class ThresholdTests(unittest.TestCase):
    def test_single_threshold(self):
        self.assertEqual(ms.build_thresholds(1.4, 1.4), [1.4])

    def test_descending_ladder(self):
        self.assertEqual(ms.build_thresholds(1.4, 1.0), [1.4, 1.3, 1.2, 1.1, 1.0])

    def test_inverted_bounds_yield_empty_list(self):
        self.assertEqual(ms.build_thresholds(1.0, 1.4), [])


class MonthSeriesTests(unittest.TestCase):
    def test_inclusive_month_range(self):
        months = ms.month_series(date(2026, 4, 1), date(2026, 10, 1))
        self.assertEqual([m.isoformat() for m in months], [
            "2026-04-01", "2026-05-01", "2026-06-01",
            "2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01",
        ])

    def test_month_end_dates_roll_over_year(self):
        months = ms.month_series(date(2026, 11, 30), date(2027, 2, 28))
        self.assertEqual([m.isoformat() for m in months],
                         ["2026-11-30", "2026-12-30", "2027-01-30", "2027-02-28"])

    def test_step_months(self):
        months = ms.month_series(date(2026, 1, 1), date(2026, 7, 1), step_months=3)
        self.assertEqual([m.isoformat() for m in months], ["2026-01-01", "2026-04-01", "2026-07-01"])

    def test_rejects_backwards_range(self):
        with self.assertRaises(ValueError):
            ms.month_series(date(2026, 5, 1), date(2026, 4, 1))


class CappedGainTests(unittest.TestCase):
    def setUp(self):
        self.params = ms.StageParams(analysis_days=35, min_turnover=1, filter_days=1)

    def frame(self):
        return pd.DataFrame({
            "entry_blocked_prev_day": [0, 0, 0, 0, 0, 1, 0],
            "Buy Day % Chng": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -5.0],
            "%open": [5.0, 5.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            "%high": [5.0, 7.0, 1.6, 1.0, 3.0, 2.0, 2.0],
            "%close": [3.0, 6.0, 0.9, 0.4, 2.0, 1.0, 1.0],
        })

    def test_matches_original_logic(self):
        df = self.frame()
        expected = legacy_capped_gain(df, 1.4)
        actual = ms.capped_gain_frame(df, 1.4, self.params).to_numpy()
        np.testing.assert_allclose(actual, expected, equal_nan=True)

    def test_named_cases(self):
        df = self.frame()
        actual = ms.capped_gain_frame(df, 1.4, self.params).to_numpy()
        # gap up but opens AT the high -> the open, not the target
        self.assertAlmostEqual(actual[0], 1.4)
        # gap up and keeps running -> the open is recorded
        self.assertAlmostEqual(actual[1], 5.0)
        # opened flat, high tagged the target -> target
        self.assertAlmostEqual(actual[2], 1.4)
        # never reached the target -> close
        self.assertAlmostEqual(actual[3], 0.4)
        # opened below target, ran past it -> target
        self.assertAlmostEqual(actual[4], 1.4)
        # buy day blocked -> excluded
        self.assertTrue(np.isnan(actual[5]))
        # buy day fell past the -3.88% gate -> excluded
        self.assertTrue(np.isnan(actual[6]))


class FrameBuildTests(unittest.TestCase):
    def test_build_day_frame_columns_and_gates(self):
        kite = FakeKite()
        days, closes = ms.build_day_frame(
            kite.historical_data(1, date(2026, 1, 1), date(2026, 3, 31), "day"),
            kite.historical_data(1, date(2026, 1, 1), date(2026, 3, 31), "5minute"),
        )
        for col in ["date_only", "open", "high", "low", "close", "volume",
                    "close_prev_day", "entry_blocked_prev_day", "Buy Day % Chng",
                    "Turnover (5m)", "%open", "%high", "%close"]:
            self.assertIn(col, days.columns)
        self.assertFalse(days["close_prev_day"].isna().any())
        self.assertFalse(days["%open"].isna().any())
        self.assertEqual(days["date_only"].is_monotonic_increasing, True)
        self.assertGreater(len(closes), 0)

    def test_first_candle_of_day_is_used(self):
        kite = FakeKite()
        intraday = kite.historical_data(1, date(2026, 2, 2), date(2026, 2, 3), "5minute")
        daily = kite.historical_data(1, date(2026, 1, 1), date(2026, 3, 31), "day")
        days, _ = ms.build_day_frame(daily, intraday)
        first_day = days.iloc[0]["date_only"]
        first_stamp = min(r["date"] for r in intraday if r["date"].date() == first_day)
        expected_open = [r["open"] for r in intraday if r["date"] == first_stamp][0]
        self.assertAlmostEqual(days.iloc[0]["open"], expected_open)

    def test_empty_intraday_raises(self):
        kite = FakeKite()
        daily = kite.historical_data(1, date(2026, 1, 1), date(2026, 3, 31), "day")
        with self.assertRaises(ValueError):
            ms.build_day_frame(daily, [])


class SliceWindowTests(unittest.TestCase):
    def test_window_bounds_and_first_day_drop(self):
        days = pd.DataFrame({
            "date_only": [date(2026, 1, 1) + timedelta(days=i) for i in range(20)],
            "close": np.arange(20, dtype=float),
        })
        window = ms.slice_window(days, date(2026, 1, 5), date(2026, 1, 15))
        self.assertEqual(window.iloc[0]["date_only"], date(2026, 1, 6))
        self.assertEqual(window.iloc[-1]["date_only"], date(2026, 1, 15))

    def test_keep_first_day_option(self):
        days = pd.DataFrame({
            "date_only": [date(2026, 1, 1) + timedelta(days=i) for i in range(20)],
            "close": np.arange(20, dtype=float),
        })
        window = ms.slice_window(days, date(2026, 1, 5), date(2026, 1, 15), drop_first=False)
        self.assertEqual(window.iloc[0]["date_only"], date(2026, 1, 5))


class LiquidityTests(unittest.TestCase):
    def setUp(self):
        self.params = ms.StageParams(analysis_days=30, min_turnover=100, filter_days=10)

    def frame(self, recent_values):
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(10)]
        return pd.DataFrame({"date_only": dates + [date(2025, 12, 1)],
                             "Turnover (5m)": recent_values + [0.0]})

    def test_mostly_liquid_passes(self):
        # 1 of 10 recent days low = 10% fail, allowed (needs >10%)
        ok, _ = ms.liquidity_ok(self.frame([1000] * 9 + [1]), self.params, date(2026, 1, 10))
        self.assertTrue(ok)

    def test_mostly_illiquid_fails(self):
        ok, reason = ms.liquidity_ok(self.frame([1, 1, 1] + [1000] * 7),
                                     self.params, date(2026, 1, 10))
        self.assertFalse(ok)
        self.assertIn("low turnover", reason)
        self.assertIn("3/10", reason)

    def test_zero_threshold_never_fails(self):
        params = ms.StageParams(analysis_days=30, min_turnover=0.0, filter_days=10)
        ok, _ = ms.liquidity_ok(self.frame([0] * 10), params, date(2026, 1, 10))
        self.assertTrue(ok)


class RateLimiterTests(unittest.TestCase):
    def test_spaces_requests(self):
        limiter = ms.RateLimiter(20)
        stamps = []
        for _ in range(5):
            limiter.acquire()
            stamps.append(__import__("time").monotonic())
        gaps = np.diff(stamps)
        self.assertTrue(all(g >= 0.035 for g in gaps), gaps)

    def test_zero_disables_pacing(self):
        limiter = ms.RateLimiter(0)
        start = __import__("time").monotonic()
        for _ in range(50):
            limiter.acquire()
        self.assertLess(__import__("time").monotonic() - start, 0.1)


class RetryTests(unittest.TestCase):
    def test_retryable_error_is_retried(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        self.assertEqual(ms.api_call_with_retry(flaky, retries=3, delay=0), "ok")
        self.assertEqual(calls["n"], 3)

    def test_token_error_is_not_retried(self):
        class TokenException(Exception):
            pass

        calls = {"n": 0}

        def bad():
            calls["n"] += 1
            raise TokenException("invalid token")

        with self.assertRaises(TokenException):
            ms.api_call_with_retry(bad, retries=3, delay=0)
        self.assertEqual(calls["n"], 1)


class FetchTests(unittest.TestCase):
    def test_chunking_covers_range_without_gaps(self):
        kite = FakeKite()
        log = []
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp, [date(2026, 4, 1)], n_symbols=1, chunk_days=30)
            ms.fetch_universe(cfg, kite, ms.load_tokens(cfg.tokens_path),
                              date(2026, 1, 1), date(2026, 5, 1), log.append)
        intraday_calls = [c for c in kite.requests_log if c[3] == "5minute"]
        self.assertGreaterEqual(len(intraday_calls), 4)  # 121 days / 30-day chunks
        # no chunk should start after the previous one ended + 1 day
        parsed = sorted((pd.Timestamp(c[1]).date(), pd.Timestamp(c[2]).date()) for c in intraday_calls)
        for (s0, e0), (s1, _) in zip(parsed, parsed[1:]):
            self.assertLessEqual(s1, e0 + timedelta(days=1))

    def test_failed_symbol_is_reported_not_fatal(self):
        kite = FakeKite(fail_symbols=(1001,))
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp, [date(2026, 4, 1)], n_symbols=4)
            frames, failures = ms.fetch_universe(cfg, kite, ms.load_tokens(cfg.tokens_path),
                                                 date(2026, 1, 1), date(2026, 4, 1), lambda *_: None)
        self.assertNotIn("SYM01", frames)
        self.assertIn("SYM01", failures)
        self.assertEqual(len(frames), 3)

    def test_limit_symbols(self):
        kite = FakeKite()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp, [date(2026, 4, 1)], n_symbols=8, limit_symbols=3)
            frames, _ = ms.fetch_universe(cfg, kite, ms.load_tokens(cfg.tokens_path),
                                          date(2026, 1, 1), date(2026, 4, 1), lambda *_: None)
        self.assertEqual(len(frames), 3)

    def test_cache_round_trip_avoids_refetching(self):
        kite = FakeKite()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp, [date(2026, 4, 1)], n_symbols=3,
                           cache_dir=os.path.join(tmp, "cache"))
            ms.fetch_universe(cfg, kite, ms.load_tokens(cfg.tokens_path),
                              date(2026, 1, 1), date(2026, 4, 1), lambda *_: None)
            first_count = len(kite.requests_log)
            frames, _ = ms.fetch_universe(cfg, kite, ms.load_tokens(cfg.tokens_path),
                                          date(2026, 1, 1), date(2026, 4, 1), lambda *_: None)
        self.assertEqual(len(kite.requests_log), first_count, "cache should prevent refetch")
        self.assertEqual(len(frames), 3)


class EvaluateStageTests(unittest.TestCase):
    def setUp(self):
        self.kite = FakeKite()
        self.frames = {}
        for token in (1000, 1001, 1002):
            days, closes = ms.build_day_frame(
                self.kite.historical_data(token, date(2025, 6, 1), date(2026, 6, 1), "day"),
                self.kite.historical_data(token, date(2025, 6, 1), date(2026, 6, 1), "5minute"),
            )
            self.frames[f"SYM{token - 1000:02d}"] = {"days": days, "closes": closes}
        self.metadata = pd.DataFrame({
            "instrument_token": [1000, 1001, 1002],
            "exchange": ["NSE"] * 3,
            "tradingsymbol": ["SYM00", "SYM01", "SYM02"],
        })
        self.params = ms.StageParams(analysis_days=120, min_turnover=0, filter_days=30)

    def test_averages_columns_match_original(self):
        avg, detail, _ = ms.evaluate_stage(
            self.frames, ["SYM00", "SYM01"], self.params, date(2026, 5, 1), self.metadata)
        self.assertEqual(avg.columns.tolist(), [
            "instrument_token", "exchange", "Symbol", "Price",
            "Total Valid Trading Days",
            "Turnover (5m) - 30d Avg",
            "Total Trimmed Gain @ 1.4% / 1",
        ])
        self.assertEqual(detail.columns[0], "Symbol")

    def test_gain_matches_hand_computed_legacy_pipeline(self):
        """Recompute one symbol exactly as High_5m.py does and compare."""
        avg, detail, _ = ms.evaluate_stage(
            self.frames, ["SYM00"], self.params, date(2026, 5, 1), self.metadata)
        sub = detail[detail["Symbol"] == "SYM00"].copy()
        legacy_daily_gain = legacy_capped_gain(sub, 1.4)
        expected = legacy_trimmed_sum_divided(pd.Series(legacy_daily_gain), 0.1, 1)
        actual = avg.loc[avg["Symbol"] == "SYM00", "Total Trimmed Gain @ 1.4% / 1"].iloc[0]
        self.assertAlmostEqual(actual, expected, places=10)

    def test_price_is_last_close_in_window(self):
        avg, _, _ = ms.evaluate_stage(
            self.frames, ["SYM00"], self.params, date(2026, 5, 1), self.metadata)
        closes = self.frames["SYM00"]["closes"]
        expected = closes.loc[closes["date_only"] <= date(2026, 5, 1)].iloc[-1]["daily_close"]
        self.assertAlmostEqual(avg.iloc[0]["Price"], expected)

    def test_window_actually_limits_rows(self):
        _, detail, _ = ms.evaluate_stage(
            self.frames, ["SYM00"], self.params, date(2026, 5, 1), self.metadata)
        self.assertLessEqual(max(detail["date_only"]), date(2026, 5, 1))
        self.assertGreaterEqual(min(detail["date_only"]), date(2026, 5, 1) - timedelta(days=120))

    def test_wide_window_has_more_rows_than_narrow(self):
        _, wide, _ = ms.evaluate_stage(
            self.frames, ["SYM00"],
            ms.StageParams(analysis_days=120, min_turnover=0, filter_days=30),
            date(2026, 5, 1), self.metadata)
        _, narrow, _ = ms.evaluate_stage(
            self.frames, ["SYM00"],
            ms.StageParams(analysis_days=35, min_turnover=0, filter_days=1),
            date(2026, 6, 1), self.metadata)
        self.assertGreater(len(wide), len(narrow))

    def test_missing_symbol_is_skipped_with_reason(self):
        avg, _, skipped = ms.evaluate_stage(
            self.frames, ["SYM00", "NOPE"], self.params, date(2026, 5, 1), self.metadata)
        self.assertNotIn("NOPE", avg["Symbol"].tolist())
        self.assertIn("NOPE", skipped)

    def test_empty_selection_returns_empty(self):
        avg, detail, _ = ms.evaluate_stage(
            self.frames, [], self.params, date(2026, 5, 1), self.metadata)
        self.assertTrue(avg.empty)
        self.assertTrue(detail.empty)


class RankTests(unittest.TestCase):
    def test_ranks_high_to_low_and_drops_blanks(self):
        avg = pd.DataFrame({
            "Symbol": ["A", "B", "C", "D"],
            "Total Trimmed Gain @ 1.4% / 1": [5.0, np.nan, 9.0, 1.0],
        })
        picks, cutoff = ms.rank_symbols(avg, 1.4, 1, top_n=2)
        self.assertEqual(picks, ["C", "A"])
        self.assertAlmostEqual(cutoff, 5.0)

    def test_top_n_larger_than_universe(self):
        avg = pd.DataFrame({"Symbol": ["A", "B"],
                            "Total Trimmed Gain @ 1.4% / 1": [2.0, 1.0]})
        picks, _ = ms.rank_symbols(avg, 1.4, 1, top_n=15)
        self.assertEqual(picks, ["A", "B"])

    def test_missing_column_yields_nothing(self):
        picks, cutoff = ms.rank_symbols(pd.DataFrame({"Symbol": ["A"]}), 1.4, 1, top_n=5)
        self.assertEqual(picks, [])
        self.assertIsNone(cutoff)


class SweepIntegrationTests(unittest.TestCase):
    def run_sweep(self, tmp, months, n_symbols=6):
        cfg = make_cfg(tmp, months, n_symbols=n_symbols)
        return cfg, ms.run_sweep(cfg, make_kite=lambda: FakeKite(), log=lambda *_: None)

    def test_month_folders_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, summary = self.run_sweep(tmp, [date(2026, 4, 1), date(2026, 5, 1)])
            for month in ("2026-04-01", "2026-05-01"):
                folder = os.path.join(cfg.out_dir, month)
                self.assertTrue(os.path.isdir(folder))
                names = set(os.listdir(folder))
                self.assertIn("run.json", names)
                self.assertTrue(any(n.startswith("stage1_averages") for n in names))
            self.assertTrue(os.path.exists(os.path.join(cfg.out_dir, "sweep_summary.json")))
            self.assertEqual(len(summary["months_detail"]), 2)

    def test_stage2_detail_keeps_original_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, _ = self.run_sweep(tmp, [date(2026, 4, 1)])
            detail_path = None
            for name in os.listdir(os.path.join(cfg.out_dir, "2026-04-01")):
                if name == "stage2_detailed.csv":
                    detail_path = os.path.join(cfg.out_dir, "2026-04-01", name)
            self.assertIsNotNone(detail_path, "stage2 detail file missing")
            detail = pd.read_csv(detail_path, nrows=3)
            self.assertEqual(detail.columns[0], "Symbol")
            for col in ["date_only", "open", "high", "low", "close", "volume",
                        "close_prev_day", "entry_blocked_prev_day", "Buy Day % Chng",
                        "Turnover (5m)", "%open", "%high", "%close"]:
                self.assertIn(col, detail.columns)

    def test_master_detail_prepends_month_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, _ = self.run_sweep(tmp, [date(2026, 4, 1), date(2026, 5, 1)])
            master = pd.read_csv(os.path.join(cfg.out_dir, "MASTER_stage2_detail.csv"), nrows=5)
            self.assertEqual(master.columns[0], "Month")
            self.assertEqual(master.columns[1], "Symbol")
            single = pd.read_csv(
                os.path.join(cfg.out_dir, "2026-04-01", "stage2_detailed.csv"), nrows=2)
            self.assertEqual(master.columns[1:].tolist(), single.columns.tolist())

    def test_one_fetch_serves_every_month(self):
        """Six months must not mean six times the downloading.

        Each symbol is fetched exactly once (one daily request) no matter how
        many months are evaluated, and the total call count must stay far below
        the per-month-loop alternative.
        """
        with tempfile.TemporaryDirectory() as tmp:
            kite_one = FakeKite()
            cfg1 = make_cfg(os.path.join(tmp, "a"), [date(2026, 4, 1)], n_symbols=3)
            ms.run_sweep(cfg1, make_kite=lambda: kite_one, log=lambda *_: None)

            kite_many = FakeKite()
            cfg2 = make_cfg(os.path.join(tmp, "b"),
                            ms.month_series(date(2026, 4, 1), date(2026, 9, 1)), n_symbols=3)
            ms.run_sweep(cfg2, make_kite=lambda: kite_many, log=lambda *_: None)

        for log, label in ((kite_one.requests_log, "1 month"), (kite_many.requests_log, "6 months")):
            daily = {}
            for token, _s, _e, interval in log:
                if interval == "day":
                    daily[token] = daily.get(token, 0) + 1
            self.assertEqual(sorted(daily.values()), [1, 1, 1], f"{label}: one daily fetch each")

        self.assertLess(len(kite_many.requests_log), 6 * len(kite_one.requests_log),
                        "6 months should reuse one download, not repeat it per month")
        self.assertLessEqual(len(kite_many.requests_log), 2 * len(kite_one.requests_log))

    def test_stage1_pick_becomes_stage2_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, summary = self.run_sweep(tmp, [date(2026, 4, 1)])
            picks = summary["months_detail"][0]["picks"]
            stage2 = pd.read_csv(os.path.join(cfg.out_dir, "2026-04-01", "stage2_averages.csv")) \
                if os.path.exists(os.path.join(cfg.out_dir, "2026-04-01", "stage2_averages.csv")) \
                else pd.read_excel(os.path.join(cfg.out_dir, "2026-04-01", "stage2_averages.xlsx"))
            self.assertEqual(sorted(stage2["Symbol"].tolist()), sorted(picks))

    def test_stage2_window_is_lag_months_ahead(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, summary = self.run_sweep(tmp, [date(2026, 4, 1)])
            report = summary["months_detail"][0]
            self.assertEqual(report["stage2_window"][1], "2026-05-01")
            detail = pd.read_csv(os.path.join(cfg.out_dir, "2026-04-01", "stage2_detailed.csv"))
            self.assertLessEqual(pd.to_datetime(detail["date_only"]).max().date(), date(2026, 5, 1))

    def test_incomplete_stage2_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp, [date(2026, 4, 1)], n_symbols=3)
            cfg.today = date(2026, 4, 15)  # stage 2 ends 2026-05-01, in the future
            summary = ms.run_sweep(cfg, make_kite=lambda: FakeKite(), log=lambda *_: None)
        self.assertFalse(summary["months_detail"][0]["stage2_complete"])

    def test_run_json_is_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg, _ = self.run_sweep(tmp, [date(2026, 4, 1)])
            with open(os.path.join(cfg.out_dir, "2026-04-01", "run.json")) as fh:
                payload = json.load(fh)
        self.assertEqual(payload["month"], "2026-04-01")
        self.assertIn("stage2_window", payload)


class PlanTests(unittest.TestCase):
    def test_plan_reports_the_owners_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_cfg(tmp, [date(2026, 10, 1)], n_symbols=1)
            cfg.stage1 = ms.StageParams(analysis_days=185, min_turnover=900000, filter_days=30)
            cfg.stage2 = ms.StageParams(analysis_days=35, min_turnover=1, filter_days=1)
            cfg.today = date(2026, 11, 21)
            plan = ms.plan_windows(cfg)
        self.assertEqual(plan.iloc[0]["Stage1"], "2026-03-30 -> 2026-10-01")
        self.assertEqual(plan.iloc[0]["Stage2"], "2026-09-27 -> 2026-11-01")
        self.assertEqual(plan.iloc[0]["Stage2 complete?"], "yes")


class TokenLoadingTests(unittest.TestCase):
    def test_loads_tsv_with_owner_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tokens.tsv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("instrument_token\texchange\ttradingsymbol\n"
                         "4741121\tNSE\tCUPID\n185\tNSE\tSAKAR\n")
            df = ms.load_tokens(path)
        self.assertEqual(df["tradingsymbol"].tolist(), ["CUPID", "SAKAR"])
        self.assertEqual(df["instrument_token"].tolist(), [4741121, 185])

    def test_missing_column_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.csv")
            pd.DataFrame({"tradingsymbol": ["X"]}).to_csv(path, index=False)
            with self.assertRaises(ValueError) as ctx:
                ms.load_tokens(path)
        self.assertIn("instrument_token", str(ctx.exception))

    def test_tab_separated_file_with_csv_extension(self):
        """Owner pastes tab-separated data; the extension may still say .csv."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tokens.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("instrument_token\texchange\ttradingsymbol\n")
                fh.write("4741121\tNSE\tCUPID\n")
            df = ms.load_tokens(path)
        self.assertEqual(df["tradingsymbol"].tolist(), ["CUPID"])

    def test_whitespace_is_stripped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\t".join(["instrument_token", "exchange", "tradingsymbol"]) + "\n")
                fh.write("\t".join(["1", "NSE ", " CUPID "]) + "\n")
            df = ms.load_tokens(path)
        self.assertEqual(df.iloc[0]["tradingsymbol"], "CUPID")
        self.assertEqual(df.iloc[0]["exchange"], "NSE")


class CliTests(unittest.TestCase):
    def test_config_from_args_defaults_match_manual_runs(self):
        parser = ms.build_parser()
        args = parser.parse_args(["--tokens", "t.xlsx", "--start-month", "2026-04-01"])
        cfg = ms.config_from_args(args)
        self.assertEqual(cfg.stage1.analysis_days, 185)
        self.assertEqual(cfg.stage1.min_turnover, 900000)
        self.assertEqual(cfg.stage1.filter_days, 30)
        self.assertEqual(cfg.stage2.analysis_days, 35)
        self.assertEqual(cfg.stage2.filter_days, 1)
        self.assertEqual(cfg.stage1.thresholds, [1.4])
        self.assertEqual(cfg.top_n, 15)
        self.assertEqual(cfg.months, [date(2026, 4, 1)])

    def test_inverted_thresholds_fall_back_to_single(self):
        parser = ms.build_parser()
        args = parser.parse_args(["--tokens", "t.xlsx", "--start-month", "2026-04-01",
                                  "--sr-start", "1.0", "--sr-end", "1.4"])
        cfg = ms.config_from_args(args)
        self.assertEqual(cfg.stage1.thresholds, [1.0])

    def test_no_cache_flag(self):
        parser = ms.build_parser()
        args = parser.parse_args(["--tokens", "t.xlsx", "--start-month", "2026-04-01", "--no-cache"])
        self.assertIsNone(ms.config_from_args(args).cache_dir)


if __name__ == "__main__":
    unittest.main()
