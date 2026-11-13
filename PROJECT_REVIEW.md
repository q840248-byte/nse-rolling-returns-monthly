# Full-project review — all ten tabs and supporting pipelines

**By Arena.ai Agent**<br>
**Review date:** 2026-11-13 UTC<br>
**Branch:** `arena/be81f877-nse-rolling-returns-monthly`<br>
**Baseline:** `b2f0877a7a92a6329bcbd28b721c0863c87c6f7b`

## Outcome

Completed a broad source-code and offline Chromium review of all ten tabs, shared calculations, allocation controls, export behavior, mobile layout, stock preprocessing/proxy handling, and automated update/test workflows. Found and fixed reproducible defects beyond the existing passing regression suite.

This is not a claim that every possible interaction, browser, or financial-source observation has been certified. No live financial-provider validation was performed. The custom orange-line methodology discussion was set aside as requested; its production data and formulas were not changed.

## Tab-by-tab coverage

| Tab | Review and outcome |
|---|---|
| Rolling Returns | Rechecked exact calendar CAGR, main chart, benchmark/recovery views, alpha toggle, search-filtered/select-all selection, mixed index/commodity allocation, empty selection, and export. Fixed allocation locks/negative-weight edge cases, stale investment simulator on deselection, invalid simulator capital, and export exception recovery. |
| Latest Stats | Checked selected/all scopes through existing UI and source paths. Fixed calendar-month underwater durations for sparse histories, zero-weight asset interference with portfolio drawdown, and price/EPS/P/E decomposition using inconsistent or substituted horizon endpoints. Fractional-year horizons now use exact month arithmetic. |
| Chart / Growth | Checked selection, rebasing/scale paths, timeline/empty handling, and category-axis callbacks. Fixed the callback to use the category value rather than the visible tick ordinal. |
| Cashflow Sim | Re-ran all six mode/view combinations: SIP, SWP, Lumpsum/STP × single/rolling. Rechecked XIRR, calendar windows, missing-month handling, and STP residual growth. Fixed invalid-input execution, fractional-year date synchronization, and the actual-tenure badge when dates differ from the end-date shortcut. Rolling-window years now explicitly require whole years rather than silently truncating them. |
| Raw P/E | Swept all 56 embedded index keys, scale/timeframe controls, empty histories, and tick callbacks. Removed the fixed 8x logarithmic floor that clipped legitimate low observations. |
| Harmonized P/E | Same coverage as Raw P/E. Removed log clipping; corrected claims of an audited uniform 18.5% adjustment. The UI now describes the actual fixed per-index pre-March-2021 approximation. Renamed the fixed 20x line from “Median” to “Reference.” |
| Dynamic Bands | Swept index choices/timeframes and verified a numerical population-SD/Z-score fixture. Fixed shortened startup windows and 60-observation windows spanning calendar gaps being called “5Y.” Now requires 60 consecutive positive monthly observations; zero dispersion has no defined Z-score. Fixed clipped mobile HUD caused by invalid `flex-wrap:gap`. |
| Yield Gap (BEER) | Rechecked earnings-yield/spread arithmetic and missing bond-yield handling. Fixed stale chart retention on empty data, stale selector contents when names change without a count change, and category ticks. |
| Smoothed P/E | Rechecked complete 36-/60-month nominal EPS smoothing and missing-window warnings. Fixed stale chart/selector behavior and category ticks. Preserved the distinction from inflation-adjusted Shiller CAPE. |
| Fundamentals | Re-ran all 24 focused browser checks, including 56 indices, 67 Indian stocks, nine US stocks, real wheel/drag interactions, zoom/reset, horizon decomposition, loss/zero EPS, visibility, missing trim observations, and mobile layout. No orange-history rebuild or methodology alteration. |

## Cross-cutting fixes and evidence

### Allocations

- Fully locked valid 80/20 allocations were being reset to equal weights. They now remain 80/20.
- The old integer equal-weight fallback could assign a negative final weight when many locked assets were selected. Normalization is now proportional (equal only for zero-total allocations), without that rounded remainder bug.
- Negative, non-finite, unselected, and locked-target allocation edits cannot improperly redistribute locked weights.

### Dates and statistics

- Sparse observations spanning January 2020 → April 2020 → January 2021 previously reported a two-month underwater/recovery span. The same fixture now reports **12 calendar months**.
- Zero-weight assets no longer remove otherwise usable portfolio drawdown dates. Portfolio NAV retains calendar dates for duration calculations.
- Stats decomposition no longer substitutes the earliest available history or an older nearby month while displaying the requested horizon. Price, earnings, and multiple changes require the same endpoint dates; unavailable components remain unavailable.
- Dynamic bands now have no fabricated startup mean/Z-score. A missing month invalidates its affected 60-month windows. Constant histories retain a mean/bands but explicitly show no defined Z-score.

### Rendering, controls, accessibility, and export

- All ten tabs fit a **390px** viewport in the new browser suite without page-level horizontal overflow. Table/long-row content retains its own scrolling rather than hiding the entire page overflow.
- Reviewed generated mobile tab screenshots; corrected the Dynamic Bands HUD wrapping defect found during visual inspection. Screenshots disable chart animation to avoid capturing partially drawn data.
- Added accessible labels for core valuation selectors and cashflow fields; active tabs announce pressed state after selection, and keyboard-operated collapse buttons expose expanded state. This is a targeted improvement, **not** a comprehensive accessibility certification.
- All five valuation charts destroy previous chart instances before returning from empty-data paths. Yield Gap and Smoothed P/E selectors compare names as well as option counts.
- Cashflow invalid amounts/rates clear stale results with a visible explanation rather than calculating on negative inputs or silently replacing blanks with defaults.
- Export restores the button on exceptions. An offline SheetJS writer fixture verifies construction of all five worksheet payloads; this does not validate an actual downloaded XLSX against Excel or LibreOffice.

### Supporting data pipelines and Worker

- Reviewed the index/commodity refresh paths, stock builder, Worker request handling, dependency setup, and CI/workflow responsibilities. Re-ran existing mock-provider pipeline and proxy tests; **no live update was run**.
- Stock preprocessing now rejects malformed price observations individually instead of abandoning otherwise valid histories. It validates dates before monthly grouping and rejects boolean EPS/price values rather than interpreting them as 0 or 1.
- Worker EPS cleanup now rejects impossible dates such as February 30, booleans/objects, and malformed observation collections; valid zero and negative EPS remain allowed.
- The separately hosted Cloudflare Worker has **not** been redeployed. Its improvements currently exist only as source changes on this branch.

## Verification

| Check | Result |
|---|---|
| JavaScript unit tests | **39 passed**, including 10 new cross-project tests and one new Worker test |
| Python unit tests | **30 passed**; includes the existing 11 chat-supplied trim-function characterization tests retained from earlier work and two new stock-pipeline tests |
| Existing all-tab browser smoke suite | Passed; all ten tabs and cashflow/stock scenarios |
| Focused Fundamentals browser suite | **24 passed**, including the 132-asset catalog sweep |
| New cross-project browser suite | **15 passed**, including 56 indices across five valuation tabs, controls, export fixture, empty states, and all-tab mobile containment |
| Inline JavaScript parsing | All seven inline script blocks parse |
| Financial data preservation | All **58 RAW blocks** and `RAW_PE`, `TOP_STOCKS_DATA`, `READY_US_STOCKS`, `ALL_INDICES_TRIMMED_EPS`, `SUBSIDIARY_FACTOR_MAP`, and `GSEC_10Y` unchanged against baseline |
| Whitespace and dependency check | `git diff --check` passed; npm install audit reported no known vulnerabilities in installed npm dependencies (not a security audit of vendored/CDN scripts) |

New commands:

```sh
npm run test:project
node --test tests/project-review.test.cjs
```

The project suite is added to the existing CI workflow. No new dependency or separate frontend engine was introduced.

## Remaining limitations and follow-up priorities

1. **Historical source validity:** provider revisions, corporate actions, EPS standalone/consolidated stitching, harmonization assumptions, bond yields, current-month provisional values, and constituent-level orange data remain unverified against original source records. Passing internal tests does not certify these financial histories.
2. **Portfolio models differ:** rolling endpoint returns and the simple investment simulator retain their available-asset/buy-and-hold conventions; cashflow simulations use monthly-rebalanced portfolios. Portfolio drawdown NAV uses shared observed dates, so gaps do not reconstruct unobserved monthly rebalancing. These conventions were not silently unified in this review.
3. **Interpretation of recovery:** the drawdown helper reports the longest observed underwater span, including ongoing episodes; it is not necessarily the time to recovery of the single deepest drawdown. Calendar timing is now correct, but those are distinct statistics.
4. **Descriptive valuation:** fixed P/E thresholds, Z-score labels, and full-history medians are estimates/heuristics—not fair-value guarantees or point-in-time investment strategies. The full-history median intentionally includes later observations relative to historical chart dates.
5. **External services/export:** financial-provider availability, quotas, CDN failures beyond the tested fallback/error paths, actual spreadsheet file compatibility, and Cloudflare deployment were not validated live.
6. **Browser/accessibility:** tested Chromium desktop and a 390px mobile viewport. Safari, Firefox, real-device touch/pinch, screen-reader workflows, contrast compliance, and exhaustive keyboard navigation still require dedicated testing.
7. **Security/performance:** safe identifiers, URL handling, malformed-input checks, and existing timeout/error paths were reviewed/tested. This is not a penetration test, load test, or supply-chain audit of external/vendor code.
8. Earlier uncommitted orange-audit documentation and the chat-function test fixture were preserved rather than deleted. They are separate from this project's runtime fixes.

## Publication status

Changes are on the current working branch only. **No commit, push, pull request, merge, website deployment, or Worker deployment was performed for this review.** See `VERSION_LOG.md` for the signed, timestamped work record.
