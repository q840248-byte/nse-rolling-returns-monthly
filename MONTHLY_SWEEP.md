# Monthly sweep — run the two-stage screen for many months at once

`monthly_sweep.py` automates a workflow that was being done by hand, once per month.

## What it replaces

Per month, two manual runs of `High_5m.py`:

| Field | Stage 1 (universe) | Stage 2 (shortlist) |
|---|---|---|
| `tokens.xlsx` | ~2,500 stocks | the top 15 from stage 1 |
| `x` (turnover floor) | 900000 | 1 |
| `analysis_days` | 185 | 35 |
| `filter_days` | 30 | 1 |
| `trim_prop` | 0.1 | 0.1 |
| `fixed_divisor` | 1 | 1 |
| `SR start / end` | 1.4 / 1.4 | 1.4 / 1.4 |
| `end_date` | month *D* | *D* + 1 month |

Then: sort stage-1 averages by `Total Trimmed Gain @ 1.4% / 1` descending, take the
top 15, and use stage 2's detail file for downstream work.

To cover six months by hand that is twelve runs, twelve downloads of thousands of
symbols, and two files that get overwritten every time.

## What it does instead

**One download, every month.** All 5-minute candles for the whole span are fetched
once and reduced to one row per stock-day. Every month's two stages are then sliced
from that cache. Six months cost the same download as one month; the extra months
are pure pandas.

**Nothing is overwritten.** Each month gets its own folder.

```
sweeps/
  MASTER_picks.xlsx            one sheet, every month's ranked picks
  MASTER_stage2_detail.csv     every month's detail stacked, with a Month column
  sweep_summary.json           windows, parameters, skips and failures
  2026-04-01/
    stage1_averages.xlsx       the 2,500-stock screen
    stage2_averages.xlsx       the 15-stock re-run
    stage2_detailed.csv        your working file (columns unchanged)
    run.json                   exactly what produced these files
  2026-05-01/
    ...
```

`stage2_detailed.csv` keeps the column names and order of `detailed_daily_output.csv`,
so existing downstream formulas keep working. `MASTER_stage2_detail.csv` is the same
data for all months with a single `Month` column prepended.

## Usage

```sh
# see every window before spending 45 minutes on downloads
python monthly_sweep.py --tokens tokens.xlsx \
    --start-month 2026-04-01 --end-month 2026-10-01 --plan
```

```
     Month                   Stage1                   Stage2 Stage2 complete?
2026-04-01 2025-09-28 -> 2026-04-01 2026-03-27 -> 2026-05-01              yes
2026-04-02 2025-10-28 -> 2026-05-01 2026-04-27 -> 2026-06-01              yes
...
```

```sh
# the real run
python monthly_sweep.py --tokens tokens.xlsx \
    --start-month 2026-04-01 --end-month 2026-10-01

# resume after an interruption — cached symbols are not re-downloaded
python monthly_sweep.py --tokens tokens.xlsx \
    --start-month 2026-04-01 --end-month 2026-10-01 --cache-dir .sweep_cache

# a quick 25-symbol trial before committing to the full list
python monthly_sweep.py --tokens tokens.xlsx \
    --start-month 2026-04-01 --limit-symbols 25 --out sweeps_trial
```

Defaults already match the table above; every value can be overridden
(`--s1-days`, `--s1-turnover`, `--s1-filter-days`, `--s2-days`, `--s2-turnover`,
`--s2-filter-days`, `--s2-lag-months`, `--top`, `--trim`, `--divisor`,
`--sr-start`, `--sr-end`, `--buy-day-min`).

`tokens.xlsx`, `tokens.csv`, `tokens.tsv` and a tab-separated file named `.csv` are
all accepted — the separator is detected from the header.

## Behaviour worth knowing

- **Windows are calendar days, as in the original.** `analysis_days=185` is 185
  calendar days (≈130 trading days), not 185 trading days.
- **The first day of each window is dropped**, reproducing the original behaviour
  where day one had no previous close. `--keep-first-day` turns that off.
- **Stage 2 can be incomplete.** If a month's stage-2 window ends after today, the
  numbers are partial and the run log, `run.json` and the plan all say so.
- **The price column is filled.** The original made one `kite.ltp()` call for the
  whole universe, which exceeds the 1,000-instrument limit and silently produced an
  empty column. The sweep uses the last close in the window, so no extra API calls.
- **Liquidity is compared in whole days.** The original compared float fractions,
  and because `1 - 0.90` is `0.09999999999999998`, a stock failing exactly 10% of
  recent days was rejected even though the rule allowed it.
- **Small samples are no longer blanked.** The original's `trimmed_sum_divided`
  returned `NaN` for fewer than 10 valid trades at `trim=0.1` (`iloc[0:-0]` is an
  empty slice). On a 35-day stage-2 window that silently dropped names to the bottom
  of the sort.
- **Retries skip permanent errors.** Token, permission and input errors fail
  immediately instead of being retried three times with a 2-second sleep.
- **Requests are paced, not just capped.** Kite allows 3 requests/second; a bare
  thread pool bursts past it. `--rate-limit` defaults to 3.

## Cost

For 2,500 symbols over 24 months: one daily request each plus 5-minute data in
99-day chunks (≈9 chunks). That is roughly 25,000 requests, so ~2.3 hours at
3 requests/second. Six months is roughly half that. Adding more months grows the
chunk count linearly, so widening 6 → 24 months is ~4× the download and still a
single pass.

## Tests

```sh
python -m unittest tests.test_monthly_sweep -v
```

58 offline tests, no network and no credentials. They assert equivalence with the
original script by recomputing the same fixtures with the original arithmetic
(screen logic, trimmed sum, trimmed mean) and comparing values. They also cover the
one-fetch-per-symbol invariant, chunk continuity, cache reuse, partial windows,
month arithmetic across year boundaries, and the output column contracts.
