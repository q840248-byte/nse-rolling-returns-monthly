# Trimmed EPS audit — all embedded index series

**By Arena.ai Agent**

**Generated (UTC):** 2026-11-13 03:36:44

**Audited file:** `rolling_returns.html`

**HTML SHA-256:** `a42ae1aff88990bc0bdd47b6d537e3404326d61445475ec2c4403094f5ca70da`

## Verdict

**The project does not provide enough evidence to certify the trimmed-EPS calculation for any of these indices.** It contains precomputed output values but no accessible constituent-trimming generator, input snapshots, or exclusion ledger. This is an **unverified** result, not proof that every value is wrong.

**Follow-up:** the owner has supplied the intended methodology, external generator filenames, and a complete trimming-function excerpt tested separately. See [TRIMMED_EPS_METHOD.md](TRIMMED_EPS_METHOD.md) for the supplied rule, its assessment, and remaining implementation questions. The excerpt implements the cap but has loss-gate and weighted-median discontinuities; see the supplement for tested examples. Local Windows links do not supply the full generator or inputs.

Earlier chart tests established rendering and arithmetic behavior, not the financial validity of the supplied trimmed data. This audit does not modify that data or replace the user’s method with a guessed formula.

## What the webpage actually computes

- The ordinary index EPS is inferred as index price / harmonized P/E, not loaded from a separate EPS series. For months before March 2021, P/E is multiplied by an index-specific fixed factor and rounded to two decimals.
- The orange input is read from `ALL_INDICES_TRIMMED_EPS`. The webpage does not select constituents, rank them, discard 5%, or aggregate retained earnings. Existing tooltip/comment claims about constituent-level 5% trimming are not substantiated by a reproducible calculation in this repository.
- The orange plotted ordinate is `100 × supplied trimmed EPS × median multiple / first visible index price`. It is rebased **trimmed intrinsic value**, not an unscaled EPS value. Hover text shows the supplied EPS separately.
- For all currently covered indices with a positive raw/harmonized P/E history, orange and green share the raw/harmonized full-history median P/E. Although the renderer collects Price / trimmed-EPS multiples, it does not normally use their own median. This is a shared valuation assumption, not evidence of a correctly computed trim.
- The scheduled and full-history workflows invoke `update_data.py`, which updates prices, commodities, and P/E. No trimmed-EPS rebuild is present in that path. Raw updates and this static table can therefore become unsynchronized.

### Source locations

- `nse-rolling-returns-monthly/rolling_returns.html:3549` — Stored trimmed-EPS table.
- `nse-rolling-returns-monthly/rolling_returns.html:13736` — Historical P/E harmonization.
- `nse-rolling-returns-monthly/rolling_returns.html:14901` — Index EPS inference.
- `nse-rolling-returns-monthly/rolling_returns.html:15008` — Shared median-multiple selection.
- `nse-rolling-returns-monthly/rolling_returns.html:15067` — Orange plotted-value formula.
- `update_data.py`, `update_commodities.py`, `build_top_stocks.py`, and `.github/workflows/` were inspected for data-generation/update responsibilities. `build_top_stocks.py` processes individual-stock histories; it is not an index constituent-trimming generator.

## Whole-table structural checks

- **56 index series; 5,889 supplied observations.**
- Invalid month keys: **0**; non-finite/non-numeric EPS values: **0**.
- Non-positive supplied EPS values: **0**; internal calendar gaps: **0**.
- Missing matching positive price observations: **0**.
- Supplied EPS months without a matching positive stored P/E: **626**, across **15** indices. This prevents same-month comparison with inferred EPS; it does not, by itself, disprove an independent constituent calculation.
- Latest trimmed month distribution: `2026-11`: 56 indices.
- Price-series indices with no trimmed table: none (excluding gold and silver).
- Positivity, continuity, coverage, or a smooth curve cannot establish that historical members, earnings, and weights were correct.

## Specific observations requiring reconciliation

### Large differences from the inferred EPS comparator

Screening rule: supplied trimmed EPS >100× price/harmonized-P/E EPS. This arbitrary diagnostic threshold is **not a correctness test**. Near-zero aggregate earnings can legitimately create very large ratios; the stored P/E itself also needs source verification. These values must not be automatically clipped or “repaired.”

| Index | Month | Index price | Stored P/E | Inferred harmonized EPS | Supplied trimmed EPS | Ratio |
|---|---|---:|---:|---:|---:|---:|
| Nifty Smallcap 250 | 2016-07 | 4,778.33 | 44,692.09 | 0.1178 | 282.25 | 2,395.7× |
| Nifty100 Equal Weight | 2020-04 | 10,890.30 | 31,345.18 | 0.4111 | 891.44 | 2,168.4× |
| Nifty Smallcap 250 | 2016-08 | 4,898.93 | 38,546.16 | 0.1400 | 296.33 | 2,115.9× |
| Nifty100 Equal Weight | 2020-05 | 10,949.20 | 26,223.48 | 0.4941 | 881.45 | 1,784.1× |
| Nifty100 Equal Weight | 2020-03 | 9,463.00 | 5,007.89 | 2.2360 | 890.09 | 398.1× |
| Nifty Smallcap 250 | 2016-10 | 5,201.36 | 6,169.87 | 0.9290 | 266.36 | 286.7× |
| Nifty Smallcap 250 | 2016-06 | 4,586.69 | 1,979.15 | 2.5537 | 297.33 | 116.4× |

### Large consecutive-month changes

Screening rule: absolute change >50% between adjacent calendar months. Reconstitution, weighting changes, financial results, or a source error can all cause jumps. The aggregate curve alone cannot identify the cause; index EPS growth can include composition effects, not just underlying company earnings growth.

| Index | Interval | Before | After | Change |
|---|---|---:|---:|---:|
| Nifty200 Momentum 30 | 2021-05 → 2021-06 | 529.51 | 978.57 | +84.8% |
| Nifty200 Momentum 30 | 2025-11 → 2025-12 | 731.78 | 1,226.42 | +67.6% |
| Nifty500 Momentum 50 | 2025-11 → 2025-12 | 1,117.08 | 1,796.77 | +60.8% |
| Nifty Alpha 50 | 2025-11 → 2025-12 | 991.16 | 1,575.30 | +58.9% |
| Nifty200 Momentum 30 | 2024-11 → 2024-12 | 1,931.02 | 840.24 | -56.5% |
| Nifty500 Momentum 50 | 2024-11 → 2024-12 | 2,154.89 | 970.09 | -55.0% |
| Nifty100 Alpha 30 | 2026-02 → 2026-03 | 680.35 | 1,048.20 | +54.1% |
| Nifty Midcap 50 | 2014-02 → 2014-03 | 157.73 | 241.99 | +53.4% |
| Nifty500 Multicap Momentum Quality 50 | 2024-11 → 2024-12 | 2,060.84 | 963.64 | -53.2% |
| Nifty200 Alpha 30 | 2025-11 → 2025-12 | 608.67 | 923.43 | +51.7% |

## Per-index findings

**Financial calculation status for every row: UNVERIFIED — supplied method is documented, but generator and historical source inputs remain unavailable.** “No P/E” counts trimmed observations lacking a positive stored P/E; “largest move” is a diagnostic, not a failure.

| Index | Trimmed history | Months | No P/E | Largest monthly move |
|---|---|---:|---:|---:|
| Nifty 100 | 2009-01 → 2026-11 | 215 | 0 | 11.0% |
| Nifty 200 | 2013-06 → 2026-11 | 162 | 0 | 8.1% |
| Nifty 50 | 2009-01 → 2026-11 | 215 | 0 | 11.2% |
| Nifty 500 | 2013-06 → 2026-11 | 162 | 0 | 7.8% |
| Nifty Alpha 50 | 2012-11 → 2026-11 | 169 | 5 | 58.9% |
| Nifty Alpha Low Volatility 30 | 2017-07 → 2026-11 | 113 | 0 | 35.8% |
| Nifty Alpha Quality Low Volatility 30 | 2017-07 → 2026-11 | 113 | 0 | 46.8% |
| Nifty Alpha Quality Value Low Volatility 30 | 2017-07 → 2026-11 | 113 | 0 | 26.3% |
| Nifty Dividend Opportunities 50 | 2015-06 → 2026-11 | 138 | 0 | 23.7% |
| Nifty Growth Sectors 15 | 2014-05 → 2026-11 | 151 | 0 | 39.0% |
| Nifty High Beta 50 | 2012-11 → 2026-11 | 169 | 19 | 44.4% |
| Nifty LargeMidcap 250 | 2016-04 → 2026-11 | 128 | 19 | 9.8% |
| Nifty Low Volatility 50 | 2012-11 → 2026-11 | 169 | 0 | 18.6% |
| Nifty Microcap 250 | 2021-05 → 2026-11 | 67 | 0 | 21.8% |
| Nifty MidSmallcap 400 | 2016-04 → 2026-11 | 128 | 0 | 14.5% |
| Nifty MidSmallcap400 50-50 | 2016-04 → 2026-11 | 128 | 118 | 11.8% |
| Nifty MidSmallcap400 Momentum Quality 100 | 2024-02 → 2026-11 | 34 | 0 | 21.2% |
| Nifty Midcap 100 | 2013-06 → 2026-11 | 162 | 1 | 28.0% |
| Nifty Midcap 150 | 2016-04 → 2026-11 | 128 | 0 | 17.8% |
| Nifty Midcap 50 | 2012-10 → 2026-11 | 170 | 3 | 53.4% |
| Nifty Midcap Select | 2021-09 → 2026-11 | 63 | 0 | 23.7% |
| Nifty Midcap150 Momentum 50 | 2022-08 → 2026-11 | 52 | 0 | 32.6% |
| Nifty Midcap150 Quality 50 | 2019-10 → 2026-11 | 86 | 0 | 19.0% |
| Nifty Next 50 | 2009-01 → 2026-11 | 215 | 0 | 34.0% |
| Nifty Quality Low Volatility 30 | 2017-07 → 2026-11 | 113 | 0 | 12.8% |
| Nifty Smallcap 100 | 2013-06 → 2026-11 | 162 | 12 | 27.5% |
| Nifty Smallcap 250 | 2016-04 → 2026-11 | 128 | 5 | 14.0% |
| Nifty Smallcap 50 | 2016-04 → 2026-11 | 128 | 2 | 28.5% |
| Nifty Smallcap 500 | 2026-01 → 2026-11 | 11 | 0 | 5.0% |
| Nifty Smallcap250 Momentum Quality 100 | 2023-12 → 2026-11 | 36 | 0 | 16.9% |
| Nifty Smallcap250 Quality 50 | 2023-03 → 2026-11 | 45 | 0 | 19.6% |
| Nifty Top 10 Equal Weight | 2024-06 → 2026-11 | 30 | 0 | 6.2% |
| Nifty Top 15 Equal Weight | 2024-10 → 2026-11 | 26 | 0 | 6.7% |
| Nifty Top 20 Equal Weight | 2024-10 → 2026-11 | 26 | 0 | 7.2% |
| Nifty Total Market | 2021-05 → 2026-11 | 67 | 5 | 7.7% |
| Nifty Total Market Momentum Quality 50 | 2025-08 → 2026-11 | 16 | 0 | 35.3% |
| Nifty100 Alpha 30 | 2019-06 → 2026-11 | 90 | 0 | 54.1% |
| Nifty100 Equal Weight | 2009-01 → 2026-11 | 215 | 53 | 16.1% |
| Nifty100 Low Volatility 30 | 2016-07 → 2026-11 | 125 | 0 | 19.3% |
| Nifty100 Quality 30 | 2015-03 → 2026-11 | 141 | 0 | 12.4% |
| Nifty200 Alpha 30 | 2022-07 → 2026-11 | 53 | 0 | 51.7% |
| Nifty200 Momentum 30 | 2020-08 → 2026-11 | 76 | 0 | 84.8% |
| Nifty200 Quality 30 | 2018-04 → 2026-11 | 104 | 0 | 14.3% |
| Nifty200 Value 30 | 2024-06 → 2026-11 | 30 | 0 | 8.9% |
| Nifty50 Equal Weight | 2009-01 → 2026-11 | 215 | 99 | 21.5% |
| Nifty50 Value 20 | 2015-06 → 2026-11 | 138 | 0 | 36.4% |
| Nifty500 Equal Weight | 2013-06 → 2026-11 | 162 | 131 | 14.4% |
| Nifty500 Flexicap Quality 30 | 2025-04 → 2026-11 | 20 | 0 | 8.5% |
| Nifty500 LargeMidSmall Equal-Cap Weighted | 2016-04 → 2026-11 | 128 | 98 | 10.1% |
| Nifty500 Low Volatility 50 | 2024-12 → 2026-11 | 24 | 0 | 22.8% |
| Nifty500 Momentum 50 | 2024-06 → 2026-11 | 30 | 0 | 60.8% |
| Nifty500 Multicap 50-25-25 | 2016-04 → 2026-11 | 128 | 56 | 9.5% |
| Nifty500 Multicap Momentum Quality 50 | 2024-09 → 2026-11 | 27 | 0 | 53.2% |
| Nifty500 Multifactor MQVLv 50 | 2025-02 → 2026-11 | 22 | 0 | 13.8% |
| Nifty500 Quality 50 | 2024-12 → 2026-11 | 24 | 0 | 21.3% |
| Nifty500 Value 50 | 2018-09 → 2026-11 | 99 | 0 | 30.0% |

## Nifty 50: why the two EPS baselines need care

| Month | Stored price | Stored P/E | Price / stored P/E | Price / harmonized P/E (green EPS) | Supplied trimmed EPS |
|---|---:|---:|---:|---:|---:|
| 2009-01 | 2,874.80 | 13.40 | 214.54 | 250.64 | 268.03 |
| 2020-09 | 11,247.55 | 32.69 | 344.07 | 402.13 | 503.21 |
| 2021-02 | 14,529.15 | 39.65 | 366.44 | 428.34 | 537.59 |
| 2021-03 | 14,690.70 | 33.20 | 442.49 | 442.49 | 534.76 |
| 2026-11 | 25,299.35 | 20.62 | 1226.93 | 1226.93 | 1,182.28 |

The harmonization factor is an assumption applied to old observations, not a reconstruction of each historical constituent’s consolidated financial statements. The orange generator must use a compatible earnings/accounting/index scale before these lines can be interpreted as a clean raw-versus-trimmed comparison.

## What is needed to validate your method

1. The actual `compute_pit_trimmed_eps.py` generator identified by the owner, plus its inputs and configuration. The written methodology is now recorded in the supplement.
2. Verify that the full generator calls the supplied function with sorted, valid inputs and documented missing-data handling. Decide whether its tested loss-gate and median-switch discontinuities are intended.
3. For each historical date: constituent identifiers, effective memberships, index weights/free-float or cap adjustments, and prices.
4. Matching TTM earnings with declared standalone/consolidated and basic/diluted basis, share/split adjustments, loss/exceptional-item treatment, and reporting availability dates.
5. Verify the described retained-weight renormalization and index-price scaling in the script; reconcile the untrimmed aggregate against the official baseline.
6. A reproducible ledger: removed names, their metric values/weights, retained weight total, intermediate earnings aggregate, and final EPS.

A simple average of company EPS is generally not a comparable index EPS: per-share units, splits, and index weighting matter. That is a methodological caution, not a claim that your unavailable generator actually uses that shortcut.

### Aggregation identity — not an implementation of the custom cap

With portfolio-consistent weights `w_i` and earnings yields `y_i = TTM EPS_i / share price_i`, an aggregate yield is `Y = Σ(w_i × y_i)`. If your rule removes a set of names and reweights the survivors, `Y_trim = Σ_retained(w_i × y_i) / Σ_retained(w_i)`, and `index_level × Y_trim` is one synthetic index-scale earnings measure. Leaving the retained weights unnormalized defines a different measure. The supplied method uses renormalization and also adds an upper-tail cap; this identity alone does not implement it or establish equivalence to NSE’s convention.

## Recommended next step

Supply the actual generator identified in the methodology supplement and at least one constituent-level input snapshot. Reproduce Nifty 50 on an ordinary month, then a flagged stress month, then equal-weight/capped/momentum indices before certifying all 56. Until that is done, treat orange as an unverified custom earnings/valuation estimate—not a validated 5% trimmed-earnings benchmark.

## Repository-history provenance check

The checkout is shallow, so GitHub commit/file/tree APIs were also inspected. This was targeted investigation of the relevant implementation revisions, not an exhaustive search of every branch or external workspace.

- [`71e3a9d465`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/71e3a9d465aa8bebdf423aae15a2716bd3c20f02) introduced an embedded Nifty 50 trimmed-EPS table.
- [`d61abc3b91`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/d61abc3b9140a41d7481de4a15402a476918ef8f) used the Nifty 50 table but derived other indices’ orange EPS as `price / clamp(current P/E, full-history 5th percentile P/E, full-history 95th percentile P/E)`. That old algorithm was historical P/E winsorization, **not** cross-sectional constituent EPS trimming. It is not the current table-lookup implementation.
- [`3fcdfc45e7`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/3fcdfc45e77d0836ecfa64e337271d4fca862f05), [`679c4acd0f`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/679c4acd0fb27362291912e037d5bd2cb646a6fc), [`e1b84d4f34`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/e1b84d4f34b5f1ed44aa6d4bee3dc741e76a4e7b), and [`5462cdc30e`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/5462cdc30e9a81127ec37d413dba7dd17253a17b) have messages describing company-level trimming, point-in-time constituents, weighting, and momentum/equal-cap rules. Their changed-file lists contain only `rolling_returns.html`; they do not supply a separate reproducible generator or input snapshots.
- [`0bc7e9b2bb`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/0bc7e9b2bb7ea8104848cbccc2d7a1dcbd88cc0d) describes restricting history starts and sharing a median multiple. Its tree, and the inspected trees at `d61abc3b91`, `3fcdfc45e7`, and `679c4acd0f`, contain no identifiable constituent-trimming pipeline or constituent source dataset.
- Commit messages describe intended work; they do not prove historical membership, weights, earnings, or rounding were correct. The external script/notebook or prior working files may still exist outside this repository.

## Scope and limits

- Audit inputs are the checked-out HTML and repository scripts, not independently downloaded NSE constituent/financial histories.
- No live NSE, Screener, SEC, or Yahoo verification was performed. GitHub deployment/source identity can be checked separately through its API.
- On the audit date November 2026 is incomplete; a `2026-11` key alone does not establish final month-end availability or matching as-of timestamps.
- This script checks stored output and generates this report only. It never writes the webpage, adjusts a financial value, or runs a data update.
