# Version log

Entries are signed by the agent doing the work and timestamped in **UTC**. This file is maintained inside the project repository. Changes listed here do not imply a production deployment, a live-provider audit, or a guarantee that every defect has been found.

## Review 2026-11-13.1 — Mobile stock search/fetch failure in Tab 9

**By Arena.ai Agent**<br>
**Started:** 2026-11-13 (UTC)<br>
**Verification completed:** 2026-11-13 (UTC)<br>
**Branch:** `arena/fc7de468-nse-rolling-returns-monthly`<br>
**Base commit:** `9d98e6fd58fcca09d54e4f62c81a10731019aac0`<br>
**Status:** Implemented and locally verified; not committed, pushed, merged, or deployed by the agent.

### 1. Reported symptom

Searching a stock in Tab 9 Fundamentals worked on a desktop browser but failed on Android Chrome, whether on Wi-Fi or mobile data, for symbols outside the embedded cache. Cached bluechips (e.g. RELIANCE) still loaded on the phone, which localised the fault to the live lookup path rather than CORS, TLS, or the page itself.

### 2. Root causes

1. **Unsaved symbol input on the phone keyboard.** The search field had no enclosing form. Mobile keyboards report their action key as "Go", which does not emit the `Enter` keystroke the field listened for, so tapping Go could do nothing at all.
2. **Timeout budget too small for uncached symbols.** `/api/stock` must resolve an unknown symbol through a Screener search (plus a page fallback) and then fetch consolidated and standalone charts. Each upstream call had a 15 s Worker timeout while the browser aborted the whole request at 30 s, so a slow mobile link failed with a bare `Failed to fetch`.
3. **`localStorage` access outside `try`.** Private mode and several in-app browsers throw on `localStorage.getItem`, which aborted `fetchCustomStock` before any request was sent.
4. **`AbortSignal.timeout` unavailable.** Older Android WebViews and iOS Safari lack it, so constructing the request threw immediately.
5. **Serial search variants in the Worker.** Hyphenated symbols queried the hyphenated and spaced forms one after another, doubling latency exactly where mobile links are slowest.
6. **No visible in-progress state.** Loading was deliberately silent, so a multi-second mobile fetch looked like a dead button.
7. **Proxy dialog off-screen on phones (found during verification).** `#panel9` uses `backdrop-filter`, which makes it a containing block for `position: fixed` descendants. The settings dialog anchored to the tall card instead of the viewport and rendered below the fold, leaving a dark overlay with no visible dialog.

### 3. Changes

1. **Form-wrapped search:** `#fundStockInput` now lives in `#fundStockForm`; submit (keyboard Go/Enter) calls `fetchAndSelectStock(true)` with `preventDefault`, so no navigation occurs. Added `enterkeyhint="go"`, `autocapitalize="characters"`, `autocorrect="off"`, and an `onchange` normaliser so phone-typed input such as `" reliance industries "` becomes `RELIANCE`.
2. **Safe storage helpers:** `fundGetProxyUrl` / `fundSetProxyUrl` wrap `localStorage` and fall back to the default Worker so private-mode browsing cannot abort a lookup.
3. **Timeout compatibility:** `fundTimeoutSignal` prefers `AbortSignal.timeout`, falls back to `AbortController`, and finally to no signal. The lookup budget rose from 30 s to 75 s to match the real upstream cost of an uncached symbol.
4. **One retry for transient failures only:** `fetchStockProxyJson` retries once after 600 ms on network errors, aborts, timeouts, 429, 408, and 5xx. Deterministic answers such as 404 are not retried.
5. **Actionable mobile errors:** `fundDescribeFetchError` explains "Failed to fetch" in terms of degraded connectivity, private DNS/ad-blocker filtering of `*.workers.dev`, or private browsing, and points at the new connection test. Provider messages pass through unchanged.
6. **Visible progress:** the Fetch button shows `Fetching…` with `aria-busy` and `disabled` while the request is in flight, then restores.
7. **Cache policy kept honest:** a first-time lookup may be served from the Worker cache (`cache: 'default'`), while an explicit Fetch ⚡ refresh bypasses it (`cache: 'no-store'`), so existing refresh semantics are unchanged.
8. **Proxy URL normalisation:** `buildStockProxyUrl` accepts a bare host, a `.../api` base, or a full `.../api/stock` endpoint without producing a doubled `/api/api/stock` segment.
9. **Device connection test:** the proxy dialog gained a `Test Connection` button that calls `/api/search?q=RELIANCE` and reports reachability plus round-trip latency, so a blocked network is diagnosed on the device instead of guessed at.
10. **Dialog placement:** the dialog is promoted to `<body>` on load, so it is centred on the screen (verified at 390×844) instead of below the fold.
11. **Worker latency and caching:** hyphenated search variants now run concurrently with per-variant failure isolation; successful chart and search responses carry `Cache-Control` so repeats are instant on a slow link, while error responses stay uncached.

### 4. Verification

- `npm test`: 55/55, including 12 new mobile-fetch unit tests and 3 new proxy tests (concurrent search, failure isolation, cacheability).
- `npm run test:browser`: 19/19. `npm run test:fundamentals`: 32/32. `npm run test:project`: 15/15.
- `python -m unittest discover -s tests`: 30/30, unchanged, confirming the data pipeline is untouched.
- New `npm run test:mobile` (wired into CI): 9/9 in a touch-emulated 390×844 Android profile — form submit, no navigation, symbol normalisation, busy state, error guidance, private-mode fallback, dialog centring, device connection test, and no sideways overflow.

### 5. Remaining risks

- The Worker changes require redeploying `stock-proxy-worker.js` to Cloudflare. Until then the client-side fixes apply but server-side latency and caching improvements do not.
- Screener.in rate limiting can still fail a lookup; the retry now covers it but does not guarantee success.
- The reported device was not tested directly. The reproduction used an emulated Android profile with external hosts blocked, so a device-specific network filter can only be confirmed with the in-app connection test.

## Review 2026-11-12.1 — Integrated application review and regression fixes

**By Arena.ai Agent**<br>
**Started:** 2026-11-12 18:15 UTC<br>
**Verification completed:** 2026-11-12 18:30 UTC<br>
**Branch:** `arena/81718381-nse-rolling-returns-monthly`<br>
**Base commit:** `a307a9f90cd696218c005584f31cf4ec6a013d9c`<br>
**Status:** Implemented and locally verified; not committed, pushed, merged, or deployed by the agent.

### 1. Scope and architecture

- Reviewed the application as one integrated system: the single HTML webpage, shared selection/allocation state, calculations, all ten tabs, embedded datasets, three Python data scripts, Cloudflare stock proxy, and existing automation/tests.
- Preserved the single-page application architecture. No frontend framework, runtime build step, backend service, or additional user-facing page was introduced.
- Added reusable monthly-portfolio helpers inside the existing webpage so cashflow journeys and historical stress tests use the same missing-data and allocation rules.
- Kept existing financial datasets intact. No live market-history refresh or speculative correction of historical values was performed.
- Added development-only Node tooling for repeatable offline JavaScript and browser tests.

### 2. `rolling_returns.html` — calendar calculations and recovery

1. **Sparse-history rolling CAGR:** Previously, iteration began at the horizon's number of observations. For quarterly/gapped history this skipped valid calendar endpoints. The calculation now checks each endpoint against its actual calendar-month start.
2. **Whole-month arithmetic:** `addMonths` now uses normalized month arithmetic and rounds floating-point month offsets. Invalid month strings and non-finite offsets are rejected rather than producing malformed dates or unbounded loops.
3. **Invalid input handling:** Rolling CAGR rejects zero/invalid horizons, and shared monthly price access excludes NaN/Infinity. Non-finite computed returns are not published.
4. **Recovery across missing observations:** Individual-asset recovery no longer stops at the first absent month. It can find the next observed qualifying recovery within the existing 120-month cap; it does not interpolate a recovery date.
5. **Portfolio recovery cleanup:** Removed an unused duplicate portfolio-CAGR calculation from each recovery iteration. An unavailable observation no longer immediately terminates the portfolio search. Existing available-asset weighting semantics were retained, not silently redefined.

### 3. `rolling_returns.html` — cashflow engine and financial math

1. **Shared monthly history:** Added `getPortfolioMonthlyHistory`, using positive allocations, their overlapping coverage, normalized weights, and a complete calendar-month timeline.
2. **Missing-data integrity:** A month lacking a required asset price is marked `null`. The old calculation could omit months, treat a multi-month movement as one month, use 0% for an unavailable return, or redistribute missing assets' weights. These substitutions are no longer used in cashflow simulations.
3. **Single journeys:** Reject incomplete or empty monthly ranges with an explicit message, rather than showing invented monthly returns.
4. **Rolling cohorts:** Exclude windows containing unavailable returns. If no complete windows exist, clear the old chart and KPIs and display an explanation.
5. **Zero allocations:** Zero-weight assets do not shorten valid coverage. An all-zero portfolio does not silently turn into an equal-weight portfolio in cashflow calculations.
6. **Exact-length history:** SIP, SWP, and lumpsum rolling simulations now accept exactly the required number of monthly returns. A one-year cohort correctly needs 12 returns and 13 endpoints, not an extra return.
7. **No-data UI:** Consolidated clearing of the cashflow chart, summary, insight panel, and HUD so old results are not left behind after a no-data selection.
8. **Stress-test allocations:** Historical SIP/SWP insights now use the shared allocation state. The old code queried a nonexistent `.idx-weight-slider` selector and consequently defaulted to equal weighting.
9. **Stress-test boundaries:** A SIP history with fewer than 120 usable monthly returns no longer reaches an empty-array statistic and crashes. Fifteen-year SWP insights now execute all 180 withdrawals instead of 179.
10. **Strategy disclosure:** Fixed-withdrawal SWP insights are suppressed for percentage-withdrawal mode rather than describing a different strategy as the selected result.
11. **SWP inflation timing:** The single-journey inflation increase starts on withdrawal 13, matching the rolling engine's first full year of 12 withdrawals.
12. **STP residual interest:** The residual liquid balance continues earning the modeled liquid rate after the twelve principal transfers. Previously that balance stopped compounding after month 12.
13. **XIRR sign handling:** Root-finding follows the sign of the bracket rather than assuming one cashflow orientation. Reversed-sign cashflows now solve correctly.
14. **XIRR bounds:** Added logarithmic-rate bracketing and expansion for large returns. Removed the inaccurate total-in/total-out CAGR fallback, which ignored cashflow timing.
15. **XIRR undefined cases:** Invalid, same-time-only, or unbracketed/no-solution inputs return an unavailable value rather than a fabricated zero/CAGR. The single-SIP KPI displays `N/A` for an undefined result.
16. **XIRR numerical stability:** Scaled the NPV near -100% and avoided per-iteration exponent-array allocation. This is not a claim to enumerate all roots of arbitrary non-conventional cashflows.
17. **Labels:** Corrected the last rolling cohort start-date reference and removed the assertion that nominal terminal wealth exceeding initial capital necessarily means growth above inflation.

### 4. `rolling_returns.html` — valuation integrity

1. **Missing bond yields:** Removed the hard-coded 6.68% substitution for absent `GSEC_10Y` observations. Bond yield and spread remain unavailable, and the HUD does not issue a valuation signal for the missing comparison.
2. **Accurate tab naming:** Renamed the user-facing “Shiller CAPE” tool to **Smoothed P/E**. The implemented series uses nominal inferred earnings, not CPI-adjusted ten-year real earnings; the old label overstated the methodology.
3. **Explicit disclosure:** Added explanatory text identifying the nominal 3-/5-year method, the absence of CPI adjustment, and the fact that smoothing does not establish fair value or predict returns. Removed an unsupported claim that the indicator proved a historical deep-value opportunity.
4. **Full calendar windows:** Added `computeNominalSmoothedPe`. Results require every monthly observation in the requested window; short warm-up periods and missing-month windows are not presented as complete multi-year averages.
5. **Unavailable-window rendering:** Excluded missing values from the displayed median, removed the fabricated 20x median fallback, and made the HUD safe when hovering over incomplete windows.
6. **Compatibility:** Retained existing `cape*` element/function identifiers internally so controls and integrations continue to work.

### 5. `rolling_returns.html` — stock fetching and UI safety

1. **Chronological prices:** Sort live price points before taking month-end values. Descending provider responses no longer accidentally make the earliest trading observation the month's close.
2. **Finite financial values:** Exclude non-finite prices/EPS from the live processor and validate month/date shapes before using price observations.
3. **Request races:** Added a monotonically increasing request identifier. A late result may populate its cache but cannot replace a newer stock selection, mode, status, or fetch-button state.
4. **Safe status text:** Replaced dynamic stock-fetch status/error `innerHTML` with `textContent`. Provider error messages, names, and EPS-basis text are no longer interpreted as markup in that status area.
5. **Stale charts:** Unknown/unavailable stock selections clear the previous fundamentals chart and decomposition rows instead of leaving a different stock's results on display.
6. **Force refresh:** Explicit refresh now reaches the configured proxy even when the symbol is pre-cached and the default proxy is used. Previously the default-proxy path silently reused the cache despite a refresh request.
7. **Failure fallback:** When a refresh fails and cached data exists, retain it and explicitly say that cached—not freshly fetched—data is being shown.
8. **Timeout:** Added a 30-second browser fetch timeout to avoid indefinitely disabled fetch controls.
9. **Proxy URL construction:** Added a URL-based builder that preserves query parameters, encodes symbols correctly (including `M&M`), supports existing `/stock` and `/api/stock` endpoints, and rejects non-HTTP(S) schemes.
10. **Currency header:** Replaced the blanket “All values in INR” header with India-INR/US-USD wording to match the US-stock tab.

### 6. `update_data.py` — history preservation and updater correctness

1. Reject NaN/Infinity index closes and P/E ratios before serializing data into JavaScript.
2. Check P/E HTTP status before interpreting the response body.
3. Merge full-history P/E responses into existing history rather than replacing the entire index series. A provider's truncated response no longer deletes months it omitted.
4. Fixed anomaly repair's reuse of the regex-match variable `m` as a month string. That could crash later `m.group(...)` calls.
5. Preserve old months absent from a partial anomaly-repair response; only replace observations actually returned and parsed.
6. Track repair changes independently of recent-month changes. Verified repairs are saved even if the recent fetch is unchanged or returns no rows.
7. Normalized this file from CRLF to LF and removed trailing whitespace. Use `git diff --ignore-space-at-eol` to focus on the functional changes.

### 7. `update_commodities.py` — HTML patching and unit consistency

1. Replaced the old `const RAW = ...` object patcher with asset-specific `RAW["Gold (INR)"]` and `RAW["Silver (INR)"]` block updates. The app initializes `RAW = {}` and assigns assets afterward, so the old patch was overwritten by later assignments.
2. Removed the incorrect reconversion into rupees per troy ounce. Updated values retain the daily updater's units: gold INR/10g and silver INR/kg.
3. Preserve older history and unrelated index blocks. Raise an error before writing if a required commodity block is missing.
4. Sort daily observations before month-end aggregation so row order does not change which day becomes the monthly observation.
5. Exclude invalid/non-positive commodity update values and use strict JSON serialization for the replacement blocks.
6. Create a custom monthly CSV output's parent directories when needed.
7. Move output date-string formatting after the price calculations to make index alignment explicit. **This was defensive cleanup, not a reproduced defect:** the original alignment test passed with pandas 2.3.3. An initial review suspicion was corrected after testing.
8. Corrected descriptive comments from physical spot to futures proxy; the actual Yahoo source symbols and formulas were not changed.

### 8. `build_top_stocks.py` — resilient and synchronized caches

1. Skip malformed/non-finite EPS observations instead of failing on a single bad point; validate EPS dates before chronology calculations.
2. Preserve the available consolidated EPS dataset and its basis label when standalone data is absent and consolidated history has fewer than two points.
3. Reject non-finite prices during monthly processing.
4. Start from the existing processed cache, retaining failed symbols' last-known-good values during a partial rebuild.
5. Refuse to overwrite processed output files when no stock can be processed successfully.
6. Locate and prepare the embedded `TOP_STOCKS_DATA` replacement before writing processed outputs.
7. Synchronize `rolling_returns.html` alongside `top_stocks_cache.json` and `top_stocks_data.js`. Previously the builder updated the external files but left the webpage's actual embedded runtime cache unchanged.
8. Added tests ensuring all three cache representations agree.

### 9. `stock-proxy-worker.js` — validation and bounded requests

1. Preserve OPTIONS/CORS support and reject unsupported HTTP methods with 405 and an Allow header.
2. Validate client-supplied company IDs as positive bounded integers before embedding them into provider paths.
3. Validate requested history days as an integer between 1 and 20,000, blocking malformed query injection and unbounded requests.
4. Add a 15-second timeout to provider requests.
5. Reject malformed/non-finite EPS observations and normalize valid dates to date-only strings.
6. Regression-tested consolidated-only fallback, CORS headers, unsupported methods, malformed parameters, and explicit 502 results when both chart requests fail.
7. The deployed Worker was **not** changed by these repository edits; deployment remains a separate operation.

### 10. Tests, automation, and repository maintenance

- Added `tests/test_data_pipeline.py`: offline Python regression fixtures using temporary files and mocked responses; no provider calls.
- Added `tests/engine.test.cjs`: tests the actual named calculation functions extracted from the HTML, not copied implementations.
- Added `tests/proxy.test.cjs`: executes the actual Worker source with mocked upstream requests.
- Added `tests/browser-smoke.cjs`: serves the real app on an ephemeral local port, blocks external requests, uses bundled vendor fallbacks, and closes browser/server resources afterward.
- Added `package.json` and `package-lock.json` with exact development dependencies for Playwright Core and npm-packaged Chromium. The package version is tooling metadata, not a declared production application release.
- Added `requirements.txt` and used it from both existing data workflows.
- Added `.github/workflows/test.yml` for offline Python, JavaScript, and browser checks on pushes/PRs/manual runs, with read-only repository permissions.
- Added a shared per-branch concurrency group to scheduled/manual data updates to prevent those workflows from writing simultaneously. Added a 60-minute timeout to the scheduled job; retained the full-history job's 120-minute timeout.
- Added `.gitignore` for virtual environments, Node modules, Python bytecode, raw provider cache, generated commodity CSVs, and QA artifacts.
- Added `README.md` documenting startup, the single-page architecture, script roles, units, calculation conventions, test commands, and known limitations.
- Retained the two original Windows Edge CDP scripts unchanged; they are not counted as executed by this Linux verification.
- Normalized the two edited data-workflow YAML files from CRLF to LF.

### 11. Verification evidence

**Before fixes:** The initial regression batch reproduced six Python failures/errors and six JavaScript failures. The unchanged commodity-alignment test and existing cache-consistency check passed; those were not misclassified as reproduced defects.

**Final local checks:**

| Check | Result |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests -v` | **11 tests passed** |
| `npm test` | **24 tests passed** |
| `npm run test:browser` | **Passed**, no uncaught page exceptions |
| Python compilation of changed scripts and Python tests | Passed |
| Parse all inline HTML scripts with `vm.Script` | All 4 parsed |
| `node --input-type=module --check < stock-proxy-worker.js` | Passed |
| `npm audit --audit-level=high` | 0 reported vulnerabilities in the installed npm dependency tree |
| `git diff --check` | Passed |

Browser verification covered:

- Opening every tab, 0 through 9.
- Missing-bond-yield warnings and incomplete smoothed-P/E windows.
- Cached Indian and US stock fundamentals.
- Log/linear changes, timeframe controls, zoom, programmatic pan, scale-switch zoom retention, and reset.
- Clearing unavailable-stock charts/decomposition.
- A delayed request completing after a different stock selection.
- Explicit refresh reaching the fetch path, cached fallback on error, and malicious-looking error text remaining text.
- Descending live-price fixtures producing chronological month ends.
- All six SIP/SWP/lumpsum × single/rolling cashflow combinations with an unequal-weight portfolio.
- Empty cashflow selection clearing results.
- A 390px mobile viewport smoke check (not a complete responsive-layout/accessibility audit).

**Embedded data checks:**

- 58 RAW price/commodity series; all 56 non-commodity series have updater configurations.
- 119 P/E series, 67 cached Indian stocks, 9 cached US stocks, and 56 trimmed-EPS series were identified in the existing HTML.
- RAW month keys and values passed positive/finite/valid-month checks; no duplicate HTML IDs were found in the inspected markup.
- All 58 RAW blocks and the six auxiliary constants (`RAW_PE`, `TOP_STOCKS_DATA`, `READY_US_STOCKS`, `ALL_INDICES_TRIMMED_EPS`, `SUBSIDIARY_FACTOR_MAP`, `GSEC_10Y`) were compared with HEAD and remained byte-for-byte unchanged.
- A QA screenshot was generated under ignored `artifacts/` and visually inspected. It is not a versioned deliverable.

### 12. Remaining risks and verification limits

1. **Live providers and deployment:** Network access here permits GitHub/package registries, not NSE, Yahoo Finance, Screener, the deployed Worker, or SEC. Live compatibility, credentials, rate limits, and deployed responses were not verified. No external data-refresh scripts or deployed Worker updates were run.
2. **Financial-source provenance:** Existing stock EPS sanitization/splicing, harmonization factors, trimmed EPS, US-stock history, and bond-yield data were preserved—not independently reconciled with source filings or exchange records.
3. **Portfolio conventions still differ:** The rolling-return endpoint portfolio uses an existing buy-and-hold/available-asset normalization rule. Cashflows and portfolio NAV statistics use rebalanced paths. A true unified portfolio-policy decision and clearer cross-tab labels remain important follow-up work; this review did not silently make all tabs use a different model.
4. **Drawdown interpretation:** Some existing recovery/drawdown statistics count observations, and SIP drawdown is based on account balances including deposits. These should not be assumed to be a uniform cashflow-neutral/calendar-time measure across tabs.
5. **Current-month data:** All 58 RAW series currently end in November 2026. As of this review date the month is incomplete; current-month observations are provisional, not certified completed month ends.
6. **Valuation models:** Smoothed P/E is now accurately disclosed, but no CPI-backed Shiller CAPE engine was added. Full-history median-based “intrinsic value” and valuation bands remain descriptive heuristics, not an independently validated point-in-time trading backtest.
7. **Updates/provenance:** The scheduled workflow updates indices/commodities/P/E, not every embedded dataset. Per-source freshness timestamps and explicit partial-provider-failure reporting remain desirable. Stock raw-cache reuse is documented and should not be mistaken for a forced network refresh.
8. **Storage transactions:** Multi-file stock output writes are synchronized by the builder logic but are not one atomic filesystem transaction. Interruption during writes can still require rerunning the builder; the consistency test detects mismatches afterward.
9. **Browser coverage:** Verified with Chromium only. Original Windows Edge CDP suites, Safari, Firefox, comprehensive keyboard/screen-reader behavior, Excel download, full manual touch gestures, and every input combination remain outside the executed checks.
10. **Operational security:** Worker CORS remains intentionally permissive for the existing static-app design. Production abuse/rate limiting and deployment-level access controls require separate review.
11. **No remote publication claim:** These changes and this log are saved in the repository working branch. GitHub-hosted CI has not been observed running against them, and no push, PR, merge, release, or deployment was performed.

---

## Review 2026-11-12.2 — Focused Fundamentals tab audit

**By Arena.ai Agent**<br>
**Started:** 2026-11-12 18:35 UTC<br>
**Verification completed:** 2026-11-12 18:46 UTC<br>
**Branch:** `arena/81718381-nse-rolling-returns-monthly`<br>
**Scope:** Fundamentals (Tab 9), its calculation/rendering/input paths, and focused regression coverage. Earlier working-branch changes were preserved.

### Request and method

The user identified Fundamentals as their current focus and requested a proper, detailed check. This pass went beyond opening the tab: controlled price/EPS/P/E fixtures, edge-case histories, every embedded Fundamentals asset, real mouse-wheel/drag interactions, and desktop/mobile layout checks were used. No live financial provider was contacted.

### Reproduced before making this pass's fixes

The initial focused browser suite produced **12 failures and 1 pass**:

1. Hidden stock price/IV lines left the main axis visible because a nonexistent trimmed stock series was still treated as enabled.
2. An empty stock cache crashed decomposition with `Cannot read properties of undefined (reading 'split')`.
3. Unsorted/duplicate/stale `dates` metadata produced incorrect chronology and omitted otherwise valid price history.
4. A loss-only stock with no positive P/E history received an invented 20x valuation multiple.
5. A 13-month return could be presented under a 1Y rolling label.
6. A four-year interval could be presented under a three-year decomposition heading.
7. Zoomed x-axis labels used local tick positions rather than category values, producing wrong years.
8. Switching scale restored the zoomed chart but left the HUD on a different date.
9. Resetting zoom unexpectedly changed a 5Y timeframe to MAX.
10. A stale mouseleave callback could restore the previous stock's HUD after clearing its chart.
11. An index with no overlapping price/P/E/trimmed observations left an unrelated chart on screen.
12. Missing trimmed EPS after the final observation was silently extrapolated from a historical ratio.

The passing controlled example verified **20% price CAGR, 10% EPS CAGR, and approximately 9.09% P/E-multiple CAGR**. Those components compound multiplicatively; they must not be added. The core positive-endpoint decomposition formula was preserved.

### Changes in `rolling_returns.html`

#### Calculation inputs and financial integrity

1. Added `normalizeFundamentalsStock`, shared by Indian and US cached/live-rendered stock data. It uses sorted valid monthly price keys rather than trusting the optional `dates` list, drops invalid/non-finite/non-positive prices, and preserves zero/negative EPS as distinct from missing EPS.
2. Derive stock P/E at render time from positive finite EPS and price so `Price = EPS × P/E` is internally consistent. Rounded stored P/E does not become a separate inconsistent input to decomposition. Persisted stock data was not rewritten.
3. Removed the fabricated 20x median fallback. An asset without positive P/E history has no raw median-based IV series; labels show `N/A`.
4. Kept the existing comparison convention: the harmonized/index EPS series and supplied trimmed EPS series share the raw/harmonized median multiple when available. A trimmed-only asset may use its own positive observed multiples. No automatic recalibration of ordinary trimmed histories was introduced.
5. Removed post-history trimmed-EPS extrapolation. Missing constituent-derived observations now remain missing in charts, medians, hover values, and decomposition.
6. Require exact calendar endpoints for the Fundamentals rolling overlay and 3Y/5Y/10Y decomposition. No nearby longer history is silently relabelled as the selected horizon.
7. Stop bridging unavailable IV points and log-suppressed non-positive values with a continuous trajectory (`spanGaps: false`). Linear mode still shows negative/zero IV where an observed historical median exists.
8. Distinguish unavailable endpoint EPS from non-positive endpoint EPS in decomposition messages.
9. Updated the active valuation-gap/loss calculation to follow the visible raw/harmonized or trimmed model. A trimmed-only loss now produces a trimmed-loss badge; hiding both valuation models no longer leaves a valuation-gap recommendation onscreen.
10. Keep the displayed P/E tied to its raw/harmonized series even when the trimmed IV model is selected. Losses in one series do not redefine another series' P/E.
11. Only offer the negative-trajectory linear-view shortcut when a negative IV value actually exists; a missing median cannot produce a negative valuation curve.

#### Chart lifecycle and controls

12. Added chart-bound `$syncFundHud` callbacks. The previous scale/reset controls referenced a function nested inside the renderer, swallowed the resulting reference error, and left hover/reset state inconsistent.
13. Scale changes now resynchronize the HUD to the restored visible endpoint. Resetting an active zoom retains the selected timeframe instead of falling through to MAX. The pre-existing unzoomed Reset-to-MAX behavior remains.
14. X-axis tick labels resolve `fDates[val]`, not `fDates[index]`, so zoomed labels use the actual categories.
15. Clear old chart/decomposition output for empty stock data and non-overlapping index data. Remove stale canvas mouse handlers, window mouseup handler, panel callback, and source note on clear.
16. Trimmed-series visibility is index-only in both initial rendering and checkbox updates. Hidden stock datasets no longer keep an empty primary axis visible.
17. Clip heatmap/loss shading to the plot area and restrict background drawing to the visible category range so pan/zoom does not paint over axes/margins.
18. Refresh the index dropdown when option identities change, not only when the option count changes.
19. Fixed the search input's focus handler so US-stock mode retains US ticker suggestions instead of replacing them with Indian symbols.

#### Input validation and presentation

20. Added `parseFundObservation` to validate live price/EPS observations: real ISO dates (including leap-day checks), complete finite numbers rather than numeric prefixes such as `12bad`, and rejection of blank/null/boolean values.
21. Validate upstream `datasets`/`values` arrays and ignore malformed dataset records before processing. Malformed responses produce explicit errors through the already-safe status path.
22. Escape dynamic asset identifiers inserted into Fundamentals HUD markup. Source/basis notes use `textContent`.
23. Added `fundDataNote`: identifies index harmonization or stock EPS basis, last available price month, full-history-median valuation limitations, missing-observation behavior, and the latest-date basis of the decomposition table.
24. Renamed the index green series/label from “Raw” to **Harmonized** to match `getHarmonizedPeSeries`; stocks retain their stock-specific IV label. Renamed “Real EPS CAGR” to **EPS CAGR (nominal)** because no inflation deflation is performed.
25. Replaced “Value Safe” / “Hype Driven” driver assertions with descriptive earnings-led/multiple-led growth language. Explained the multiplicative identity, dividends exclusion, nominal EPS, expanding-history percentile versus full-history IV, and the shared trimmed baseline.
26. Added Tab-9-scoped grid containment and wrapping. At 390px the page no longer expands to a wide intrinsic chart/table size. On narrow screens Fundamentals appears before the shared sidebar, without removing the sidebar or changing other tabs' order. HUD/table content remains locally scrollable where appropriate.
27. `switchTab` now records the active tab on the existing layout element so the responsive Fundamentals rules apply only while Tab 9 is selected.

### Tests and automation added/updated

- **`tests/fundamentals-browser.cjs`**: dedicated offline Chromium suite, reusing the real HTML and vendor scripts; 24 checks in the final run. Includes a catalog sweep over all 132 supported embedded Fundamentals assets.
- **`tests/fundamentals.test.cjs`**: four unit checks against the actual HTML helper functions, covering normalization/identity, invalid monthly prices, date/numeric parsing, and markup escaping.
- **`package.json`**: added `npm run test:fundamentals`; no new dependency or application build step.
- **`.github/workflows/test.yml`**: added the focused Fundamentals suite after the existing general browser checks.
- **`README.md`**: documented the focused test command, asset sweep, and runtime Fundamentals methodology/limits.
- **`VERSION_LOG.md`**: appended this signed/timestamped entry without replacing the previous audit record.
- Development dependencies and the Python virtual environment were restored in the sandbox for testing. Browser screenshots were generated only under ignored `artifacts/` and visually inspected.

### Final verification

| Check | Outcome |
| --- | --- |
| `npm run test:fundamentals` | **24 focused browser checks passed; 0 failed** |
| Embedded asset rendering | **56 indices + 67 Indian stocks + 9 US stocks**; finite/null chart datasets with matching label lengths, no NaN/Infinity/undefined HUD/table text |
| Analytical fixture | 20.0% price CAGR; 10.0% EPS CAGR; 9.1% displayed multiple CAGR for 3Y, 5Y, and 10Y |
| IV/timeframe fixture | Price/IV relationship preserved when switching MAX to 3Y; median uses full history |
| Negative/zero EPS fixture | P/E unavailable; negative/zero IV retained in linear mode when a valid median exists; gaps in log mode |
| Percentile fixture | 100th, 50th, 100th percentile across a known three-observation chronology; no future observations used |
| Interaction checks | All series toggles in all 3 modes; correct axis visibility; zoom/HUD/scale/reset consistency; **real mouse wheel zoom and mouse drag pan** |
| Mobile check | 390px viewport containment and Fundamentals-before-sidebar order passed; screenshot visually inspected |
| `npm test` | **28 unit tests passed** (24 existing + 4 added) |
| `.venv/bin/python -m unittest discover -s tests -v` | **11 tests passed** |
| `npm run test:browser` | General all-ten-tabs and cashflow/stock regressions passed; no uncaught page exceptions |
| Inline-script parsing and `git diff --check` | Passed |

All 58 embedded RAW blocks and the auxiliary financial constants were compared with the start-of-pass HTML and remained unchanged. This pass changed runtime interpretation/validation and UI behavior, not the stored financial history.

### Important remaining limits

- The pointwise stock `Price / EPS / P/E` cache audit found **no discrepancies greater than 2%** where all three positive values were present. This checks internal consistency only: it does not validate source filings, split adjustments, historical accuracy, or survivorship bias.
- Live Screener/Worker/SEC responses are still inaccessible under the sandbox network restrictions. Fetch-path behavior was tested with fixtures, not a production API call.
- Existing provider EPS cleanup, consolidated/standalone splicing, forward-filled EPS updates, and the supplied constituent-trimmed dataset remain source-methodology risks. No underlying corporate-action/EPS-history rewrite was attempted without independently verified data.
- The IV feature intentionally retains a full-history median and can therefore use future observations relative to an old chart date. That is now disclosed prominently; the feature is not a point-in-time valuation backtest or a fair-value guarantee.
- Exact endpoint requirements deliberately return unavailable results when the requested start month is missing, even if a longer nearby observation exists. This is a correctness change, not a loss of stored history.
- Screenshot/mobile checks and mouse tests do not replace real-device pinch testing, Safari/Firefox coverage, or a comprehensive accessibility audit.
- All changes remain in the current repository working branch. **No commit, push, merge, release, or deployment was performed.**

---

## Publication 2026-11-12.3 — GitHub Pages release authorized

**By Arena.ai Agent**<br>
**Date/time:** 2026-11-12 18:54 UTC<br>
**Working branch:** `arena/81718381-nse-rolling-returns-monthly`

- The user explicitly approved publishing the reviewed application to `https://q840248-byte.github.io/nse-rolling-returns-monthly/rolling_returns.html`.
- Confirmed through the GitHub Pages API that the site publishes from **`main`, repository root**. Pages settings are not being changed.
- Fetched `origin/main` and confirmed that it still points to review base `a307a9f90cd696218c005584f31cf4ec6a013d9c`; there is no newer main-branch history to reconcile at this checkpoint.
- Re-ran the publication preflight: **28 JavaScript unit tests passed; 11 Python tests passed; general all-tab browser checks passed; 24 focused Fundamentals browser checks passed**.
- Publication scope is the complete reviewed working-tree changes described in entries .1 and .2, including the version log, regression tests, documentation, and workflow updates. No financial datasets were refreshed for this release.
- Publication procedure: commit and push only the working branch, open a pull request to `main`, require successful GitHub regression checks before merging, then verify the Pages build/deployment associated with the merge.
- This timestamp records authorization and the pre-publication checkpoint, not a claim that Pages has already deployed. The pull-request and deployment records on GitHub provide the subsequent merge and build status.
- **Cloudflare Worker deployment is not included.** Its reviewed source file is published in the repository, but the separately hosted live Worker remains unchanged.

- Publication housekeeping: replaced Markdown trailing-space line breaks in this log with explicit `<br>` so the fully staged patch passes whitespace checks. No runtime behavior changed.

---

## Audit 2026-11-12.4 — Orange trimmed-EPS financial methodology and provenance

**By Arena.ai Agent**<br>
**Date:** 2026-11-12<br>
**Audit work:** approximately 19:05–19:12 UTC<br>
**Working branch:** `arena/47716a45-nse-rolling-returns-monthly`<br>
**Base commit:** `7fe1e9796d164da635dee749a67b36f5dda3c89e`

### User request and verdict

The user asked whether their custom orange trimmed EPS was calculated correctly for every index, independently of whether the chart renders correctly. This pass audits the source table, calculation path, update coverage, and available provenance. **Constituent-level correctness remains UNVERIFIED for all 56 indices:** no identifiable generator, complete historical constituent/weight/earnings inputs, or exclusion ledger was found in the current repository or targeted historical revisions. This is not a finding that all supplied values are wrong. Earlier chart tests did not certify the financial methodology.

### Work and findings

1. Traced `ALL_INDICES_TRIMMED_EPS`, its aliases, lookup helper, intrinsic-value scaling, median-multiple selection, and EPS/multiple decomposition. The current app reads precomputed values; it does not perform constituent trimming at runtime.
2. Audited **56 histories / 5,889 observations**. No duplicate JSON keys, invalid month keys, non-finite/non-numeric EPS values, internal calendar gaps, or missing corresponding positive prices were found. All supplied EPS values are positive; all histories end at `2026-11`. Positivity/continuity are not proof of correctness, and November is still incomplete on the audit date.
3. Found **626 supplied trimmed observations across 15 indices without a matching positive stored P/E**. That makes same-month comparison with inferred EPS unavailable; an independent constituent calculation might nevertheless be valid.
4. Identified **7 observations across 2 indices above 100× inferred harmonized EPS**, and **10 consecutive-month moves above 50% across 7 indices**. Saved every flagged date/value in the report. These are screening leads, not automatic data errors: near-zero aggregate earnings, reconstitutions, weight changes, and upstream source issues must be distinguished using constituents.
5. Established that green index EPS is **price / harmonized P/E**, not a separately imported NSE EPS dataset. Pre-March-2021 P/E is multiplied by fixed per-index factors and rounded. Documented Nifty 50 examples before/after the cutoff.
6. Established that orange is **trimmed EPS × median multiple, rebased to visible starting price**, not raw EPS units on the chart axis. The normal orange valuation uses the same full-history raw/harmonized median as green. This is a shared valuation assumption; neither a financial validation nor a point-in-time valuation backtest.
7. Reviewed `update_data.py`, commodity/stock builders, and scheduled/full-history workflows. No trimmed-EPS rebuilding step exists in those update paths. A current month label does not establish synchronized source timestamps or earnings freshness.
8. Used GitHub commit/file/tree APIs because local history is shallow. Inspected the relevant trimming changes from `71e3a9d465`, `d61abc3b91`, `3fcdfc45e7`, `679c4acd0f`, `e1b84d4f34`, `5462cdc30e`, `5ee58f50e2`, and `0bc7e9b2bb`.
9. Recovered the old `d61abc3b91` implementation: non-Nifty-50 orange EPS was `price / clipped historical P/E`, using full-history 5th/95th percentiles. That was **P/E winsorization, not constituent EPS trimming**. It is no longer the current implementation. Later commit messages claim point-in-time constituents, index weighting, and methodology changes, but the inspected files/trees did not supply the generator or underlying input snapshots necessary to reproduce those claims. The report links the relevant revisions and does not treat commit messages as proof.
10. Documented the missing specification: trimming metric/tails, count versus weight, rounding/ties for small baskets, historical membership, accounting basis, report availability, corporate actions, loss handling, retained-weight normalization, and index/divisor scaling. Included a possible earnings-yield aggregation definition only as an explanatory example—not a replacement for the user's unknown method.

### Repository deliverables

- **`TRIMMED_EPS_AUDIT.md`**: signed/timestamped report with HTML SHA-256, source locations, all-56-index coverage table, numerical flags, Nifty 50 comparisons, historical implementation findings, and a source-data request.
- **`audit_trimmed_eps.py`**: standard-library-only, offline diagnostic/report generator. It does not update the webpage or financial histories. The report includes manually investigated methodology/history notes that require re-review if implementation changes.
- **`tests/test_trimmed_eps_audit.py`**: six regression tests covering duplicate keys, malformed/non-finite values, calendar gaps, missing/invalid comparators, harmonization cutoff/signed changes, and current-table price coverage. Negative earnings and large moves are intentionally not treated as invalid financial data.
- **`README.md`**: linked the audit, added regeneration/test instructions, and explicitly distinguished chart testing from constituent-methodology validation.
- **`VERSION_LOG.md`**: this detailed signed audit record and the prior-publication confirmation below.

### Verification and unchanged scope

- **28 JavaScript unit tests passed** (`npm test`).
- **17 Python tests passed** (11 existing + 6 audit tests) with `.venv/bin/python -B -m unittest discover -s tests -v`.
- The first full Python run lacked `pandas` in the fresh sandbox. Restored dependencies from existing `requirements.txt` in ignored `.venv`, then reran successfully. No dependency manifests changed.
- Independently executed the actual HTML JavaScript harmonization helpers in Node: **5,263 comparable observations and the same 7 >100× ratio flags** as the Python diagnostic.
- Regenerated and reviewed the report; whitespace check passed. Confirmed **`rolling_returns.html` and financial datasets/pipelines are unchanged** against HEAD. No new browser run was needed for this documentation/offline-audit-only pass; prior browser tests are not represented as newly rerun.
- No live NSE/Screener/Yahoo/SEC constituent or financial source validation was performed. No data refresh, formula substitution, UI rewrite, or guessed correction was made.
- No commit, push, PR, merge, or deployment was performed for this audit. Files remain on the active working branch.

### Prior publication confirmation (separate from this audit)

Rechecked GitHub Pages API: the earlier authorized release was built from `7fe1e9796d164da635dee749a67b36f5dda3c89e`, updated **2026-11-12 18:57:24 UTC**, with no reported build error. GitHub `main`'s HTML blob `749ccbbff3c79b4cb98c5df069f9f25e89d97225` matches the audited local HTML. This verifies deployment/source identity via GitHub; it is not a claim of directly fetching or visually inspecting the public URL during this audit.

### Required next input

The original trimming script/notebook/spreadsheet or exact written formula, plus constituent-level inputs for at least one example month. Without that evidence, do not certify the orange histories as correctly computed, and do not silently replace them with a different definition.

---

## Pull-request preparation — owner-supplied orange-line methodology

**By Arena.ai Agent**<br>
**Date/time:** 2026-11-13 03:25:37 UTC<br>
**Working branch:** `arena/47716a45-nse-rolling-returns-monthly`

- The user requested a pull request for the audit changes and supplied the intended earnings-yield formula plus local Windows paths for the generating script and datasets.
- Added `TRIMMED_EPS_METHOD.md` to record the supplied method and filenames without claiming to access those local files. Clarified separate loss-tail removal and upper-tail capping, retained-weight renormalization, and index-price/median-multiple scaling.
- Reviewed the stated design: earnings-yield aggregation is mathematically coherent under compatible inputs, but this is a custom asymmetric loss-trim/windfall-cap model, not a conventional symmetric 5% trim or proof of true earnings. Documented unresolved fractional boundaries, cap transformation, median timing, historical weight/factor reconstruction, reporting availability, and missing-data behavior.
- Corrected two interpretation points: only price necessarily starts at 100 on the rebased chart, and the shared frontend median is calculated from harmonized historical P/E rather than untouched official NSE P/E. Neither correction changes application formulas or stored values.
- Updated `audit_trimmed_eps.py` and regenerated `TRIMMED_EPS_AUDIT.md`: the intended formula is now documented, while the actual generator and historical inputs remain unavailable. Updated the README to link the supplement. Preserved the earlier audit log as a dated record of evidence available at that time.
- Re-ran validation: **28 JavaScript tests and 17 Python tests passed**, including all six new audit tests. Restored the existing Python dependencies in ignored `.venv`; no dependency manifests changed. The report remains a structural diagnostic, not certification of historical constituent calculations.
- Publication scope is audit tooling, tests, methodology/report documentation, README, and this version log only. The application HTML, financial datasets, updater scripts, and live site remain unchanged.
- The requested operation is to commit/push this working branch and open a PR to `main`; **no merge or deployment is authorized or performed here**. This is the pre-PR checkpoint; the GitHub PR record will provide the resulting URL/status.

---

## PR #10 — merge authorization and pre-merge verification

**By Arena.ai Agent**<br>
**Date/time:** 2026-11-13 03:27:42 UTC<br>
**Working branch:** `arena/47716a45-nse-rolling-returns-monthly`

- The user explicitly authorized merging [PR #10](https://github.com/q840248-byte/nse-rolling-returns-monthly/pull/10) into `main`.
- Confirmed that the PR is open, non-draft, mergeable, and targets `main` from the current working branch. Both existing GitHub regression checks passed (runs `43358917263` and `43358887658`).
- Added this authorization record only; no application code, financial data, or methodology conclusions changed. Final-head checks will be verified before executing the merge.
- This entry records the pre-merge checkpoint, not a completed merge. The PR's merge event records the actual outcome and merge commit. Audit publication does not certify the constituent calculations or alter the orange-line data.

---

## Complete supplied trimming-function review — boundary behavior

**By Arena.ai Agent**<br>
**Date/time:** 2026-11-13 03:37:08 UTC<br>
**Working branch:** `arena/be81f877-nse-rolling-returns-monthly`<br>
**Base commit:** `b2f0877a7a92a6329bcbd28b721c0863c87c6f7b`

- Reviewed the complete `weighted_trimmed_ey` function pasted by the owner. This resolves the missing windfall-cap implementation in the earlier abbreviated explanation. The full original script, caller, and historical input files remain unavailable; no local Windows file was accessed.
- Preserved the supplied function unchanged as a labelled chat-source fixture in `tests/test_supplied_trim_function.py`, separate from production. Added 11 behavior tests. Verified partial loss trimming, stopping below the loss budget, partial-weight windfall capping with retained denominator weight, original-total-weight budgets, empty/zero-weight input, and possible negative all-loss output.
- Confirmed continuity across the upper threshold with fixed weights/median, but disproved a global “continuous without cliffs” claim. A 5%-weight constituent moving from an arbitrarily small loss to a small profit changes the denominator from 0.95 to 1.00: with remaining yield 5%, adjusted output drops from 5% to approximately 4.75%. A second fixture demonstrates a weighted-median switch that changes the cap threshold from 0.55 to 0.80 and output from 0.09749995 to 0.11000005 after a tiny weight shift. These characterize the supplied design, not identified historical occurrences.
- Verified that the function relies on pre-sorted inputs and does not itself validate finiteness, nonnegative weights, or trim-fraction range. Documented these as caller preconditions rather than assuming the unseen caller is defective.
- Rechecked the real frontend: `getHarmonizedPeSeries` applies pre-March-2021 multipliers and rounding inside this application. The owner's attribution of this specific transformation to NSE back-adjusting the history is not established. Also recorded the 53-index handoff versus 56-index embedded-data coverage discrepancy.
- Updated `TRIMMED_EPS_METHOD.md`, the README, and the reproducible audit/report wording to distinguish resolved code questions from remaining caller/data validation. Regenerated `TRIMMED_EPS_AUDIT.md`; no historical values were modified.
- Validation: **17 targeted Python audit tests passed** (11 new supplied-function tests + 6 structural audit tests), and **28 JavaScript unit tests passed**. This is not a rerun of the full Python pipeline/browser suites. Whitespace checks passed; application HTML, datasets, and updater scripts remain unchanged.
- No formula redesign, production integration of the fixture, data refresh, commit, push, PR, merge, or deployment was performed. Any continuity-oriented redesign requires an explicit methodology decision, not a silent alteration of the user's custom rule.

---

## Full-project review — all ten tabs, shared engine, pipelines, and mobile layout

**By Arena.ai Agent**<br>
**Completed:** 2026-11-13 03:58:37 UTC<br>
**Working branch:** `arena/be81f877-nse-rolling-returns-monthly`<br>
**Baseline:** `b2f0877a7a92a6329bcbd28b721c0863c87c6f7b`

### Scope and baseline

The user set aside the orange methodology discussion and requested a thorough review of the entire integrated application. Preserved earlier uncommitted audit documentation and the supplied-function fixture; no custom orange calculation, financial history, or dataset was rebuilt. Retained one HTML application/shared engine rather than introducing a separate frontend. Restored existing development dependencies in ignored `node_modules`/`.venv`; no new dependencies were added.

Re-ran the baseline: 28 JavaScript tests, 28 Python tests, existing ten-tab browser smoke scenarios, and all 24 focused Fundamentals checks passed. Then added adversarial fixtures and broader cross-tab checks rather than treating that initial green result as a complete audit. All eight initial new unit checks failed against the old implementation; two additional exact-horizon/date fixtures also failed before their fixes. The first extended browser run exposed P/E clipping, premature dynamic bands, stale charts/selectors, and page-width overflow; one separate harness issue (no selected Growth asset) was corrected in the test itself.

### Detailed changes

1. **Allocation controls:** fully locked valid weights no longer reset to equal allocations. Selection-driven all-locked normalization is proportional, removing the negative rounded-last-weight bug with large catalogs. Invalid/negative edits cannot distort locked weights; locked or unselected targets are ignored.
2. **Latest Stats drawdown timing:** sparse histories now count actual calendar months rather than observation count. Portfolio NAV carries dates and excludes zero-weight assets from required overlap. Existing drawdown return conventions are otherwise retained.
3. **Latest Stats decomposition:** introduced `computeIndexDecomposition` for exact shared price/EPS/P/E endpoint months, including half-year horizons. Removed earliest-date/nearby-date substitutions and mismatched price-versus-earnings end dates. Missing horizon endpoints display unavailable, not a differently labelled period. Updated drawer headings/fallback wording.
4. **Growth and valuation date axes:** six category tick callbacks now resolve labels from the category value, not the local tick ordinal. Tested a nonzero category index as used after zooming.
5. **Raw/Harmonized P/E:** removed fixed 8x log-axis floors so low positive observations are visible. Replaced the hardcoded 20x “Median” label with “Reference.” Corrected unsupported uniform/audited 18.5% harmonization claims to the actual pre-March-2021 fixed per-index factor approximation.
6. **Dynamic Bands:** added `computeDynamicPeBands` with 60 consecutive valid calendar months, population standard deviation, missing-window nulls, and no Z-score for zero dispersion. No more short warm-up samples or 60 sparse observations presented as five years. Reused the harmonized P/E helper for consistency. Updated explanatory copy to descriptive statistics rather than guaranteed investment signals.
7. **Empty valuation states:** Raw P/E, Harmonized P/E, Dynamic Bands, Yield Gap, and Smoothed P/E destroy old charts before early no-data returns. Yield Gap/Smoothed P/E selectors now compare option names as well as counts.
8. **Cashflow inputs:** active-mode inputs are validated against finite numeric values and declared bounds before calculation. Invalid values clear old results with an explanation. Rolling windows require whole years instead of silently truncating fractions.
9. **Cashflow date synchronization:** preserved month-accurate fractional-year dates instead of rounding to a full year. Single-journey badge shows actual simulated tenure; the years input is labelled as an end-date shortcut.
10. **Simple investment simulator:** deselecting all assets now clears its prior chart through `runSimulator`; nonpositive/non-finite capital is rejected instead of executing invalid or silently defaulted amounts.
11. **Excel export:** exceptions restore the disabled export control and display an error. Offline browser fixture verifies construction of five worksheet payloads, while a unit fixture verifies failure recovery. Actual Excel file compatibility remains untested.
12. **Responsive layout:** contained grid/flex intrinsic widths without clipping the page. All ten tabs pass 390px page-width checks. Visual inspection identified invalid `flex-wrap:gap` in Dynamic Bands HUD; corrected it and added a HUD-content containment assertion.
13. **Targeted accessibility:** added labels to valuation selectors and cashflow fields, active-tab pressed state on selection, and expanded state for keyboard-operated collapse controls. No claim of full accessibility compliance.
14. **Stock builder:** added validated observation parsing shared by EPS cleanup and prices. Rejects impossible dates, booleans, malformed observations, and non-finite numbers; invalid price rows no longer abort otherwise valid stock histories. Preserved the existing EPS cleaning/splicing policy.
15. **Worker source:** rejects impossible EPS dates, boolean/object values, and malformed observation collections. Preserves zero/negative EPS. No live Worker deployment performed.
16. **Test integration:** added `tests/project-review.test.cjs` (10 unit checks), `tests/project-browser.cjs` (15 scenario groups), one Worker test and two Python stock tests. Added `npm run test:project` and a corresponding CI step. Browser screenshots remain under ignored `artifacts/`.
17. **Documentation:** created `PROJECT_REVIEW.md` with a ten-tab matrix, fixes, exact validation scope, and remaining limitations; updated README commands/conventions and appended this signed version record. Earlier orange-audit files remain a separate dated review, not a newly certified historical dataset.

### Final validation

- **39 JavaScript unit tests passed**.
- **30 Python tests passed** (includes 11 retained tests for the earlier chat-supplied trimming-function excerpt, not 11 additional production pipeline checks).
- Existing all-tab Chromium smoke suite passed, including all six cashflow mode/view combinations and stock request/fallback scenarios.
- **24 focused Fundamentals browser checks passed**; catalog sweep covers 56 indices, 67 Indian stocks, and 9 US stocks.
- **15 new project browser scenario groups passed**, including all 56 embedded index keys across five valuation tabs, timeframe/scale/window controls, empty states, selectors, allocation/selection, offline export payloads, keyboard collapse, and all-ten-tab 390px layout. No uncaught page exceptions.
- All seven inline script blocks parse. `git diff --check` passed. npm's install audit reported zero known dependency vulnerabilities; that does not audit vendored/CDN code.
- Compared against HEAD: all **58 RAW blocks** and all six financial constants (`RAW_PE`, `TOP_STOCKS_DATA`, `READY_US_STOCKS`, `ALL_INDICES_TRIMMED_EPS`, `SUBSIDIARY_FACTOR_MAP`, `GSEC_10Y`) remain unchanged.

### Important limits and publication status

No live financial providers were contacted for validation or updates. Source history, corporate actions, full point-in-time availability, harmonization factors, valuation assumptions, and orange constituent methodology remain outside this verification. Portfolio models retain distinct buy-and-hold/available-asset versus monthly-rebalanced conventions; gaps do not reconstruct unobserved monthly trades. Recovery is the longest observed underwater span (possibly ongoing), not necessarily the recovery time for the deepest crash. No Safari/Firefox, real-device pinch, comprehensive accessibility/security/load testing, or actual spreadsheet-client compatibility is claimed.

Changes remain on the active working branch. **No commit, push, PR, merge, website deployment, or Cloudflare Worker deployment was performed in this review.**

---

## Publication — full-project review deployment authorized

**By Arena.ai Agent**<br>
**Date/time:** 2026-11-13 04:02:03 UTC<br>
**Working branch:** `arena/be81f877-nse-rolling-returns-monthly`

- User explicitly requested deployment of the reviewed changes. Publication includes the full-project fixes, tests, CI updates, review report, README/version log, and earlier preserved audit documentation/test fixture. No financial datasets are being refreshed.
- Confirmed GitHub Pages publishes from `main` at the repository root. The remote base remains `b2f0877a7a92a6329bcbd28b721c0863c87c6f7b`, matching this branch's review baseline. No Pages settings are changed.
- Fresh deployment preflight passed: **39 JavaScript tests, 30 Python tests, the existing all-tab browser suite, 24 focused Fundamentals checks, and 15 cross-project browser scenarios**. Whitespace checks passed.
- Publication procedure: commit/push only the current branch, open a PR to `main`, verify GitHub regression checks, merge the explicit PR, and verify the Pages deployment for that merge. This is the pre-deployment checkpoint; the PR/deployment record provides the final outcome and commit.
- The separately hosted **Cloudflare Worker is not deployed** by this GitHub Pages release. Its improved source is included in the repository, but deploying that service requires its separate deployment environment.
- Existing source-data/methodology limitations remain documented in `PROJECT_REVIEW.md`; deployment does not certify original financial histories or the orange constituent calculation.

---

## Fundamentals — four-series controls and selected-only legend

**By Arena.ai Agent**<br>
**Date:** 2026-11-12 (session date)<br>
**Validation timestamp:** 2026-11-13 04:48 UTC (sandbox clock)<br>
**Working branch:** `arena/bb6f4605-nse-rolling-returns-monthly`

- Set P/E unchecked on first load, with both its dataset and right-hand axis hidden. User selections survive timeframe, scale and asset-mode rerenders.
- Standardized control, dataset and legend names to **Price**, **EPS Value**, **P/E**, and **Trim. EPS Value**; removed dynamic median-dependent long labels.
- Removed the Fundamentals rolling-horizon toolbar, rolling-CAGR calculation/state/dataset/axis/legend, and its exported setter. Other tabs' rolling-return functionality and Fundamentals timeframe/decomposition horizons remain intact.
- Removed the P/E percentile checkbox, expanding percentile calculation, heatmap plugin and its shading, and percentile legend/help text.
- Replaced the diagnostic HUD with selected-series entries plus date/asset context. Price and EPS-based valuation amounts display currency to one decimal followed by their plotted rebased values, e.g. `₹1226.9 (126)`. P/E displays only a multiple, e.g. `20.6x`. US stocks use dollars. EPS Value currency amounts represent the existing EPS × median P/E curves, not raw EPS; the earlier implementation's raw-EPS legend interpretation was corrected before completion.
- Removed valuation-gap and loss badges from the simplified legend. Missing values remain unavailable; zero/negative valuation values remain readable, and logarithmic charts continue to omit nonpositive points. Trimmed entries remain index-only.
- Preserved curve calculations: full-history median P/E, shared raw/trimmed baseline where available, trimmed-only fallback, visible-window price rebasing, and no fabricated missing trimmed observations. Updated dataset indexing and primary-axis visibility/bounds after deleting the rolling dataset.
- Updated README and added formatter coverage. Replaced obsolete rolling/heatmap browser checks with removal/default/format coverage and all 16 checkbox combinations in each of the three asset modes, including hover. Retained catalog sweep, negative/missing-data, decomposition, zoom/pan/reset, and mobile tests.
- Validation: **40 JavaScript unit tests**, **27 focused Fundamentals browser checks**, existing **all-tab browser smoke suite**, and **15 project browser scenarios** passed. The focused suite was rerun after correcting the legend currency interpretation. Inline scripts parsed; whitespace checks passed. Python code was untouched and Python tests were not rerun for this UI-only change.
- Compared embedded data against HEAD: all **58 RAW blocks**, `RAW_PE`, `TOP_STOCKS_DATA`, `READY_US_STOCKS`, `ALL_INDICES_TRIMMED_EPS`, `SUBSIDIARY_FACTOR_MAP`, and `GSEC_10Y` unchanged. No orange-data recalculation or provider refresh. Screenshots/test artifacts remain ignored.
- Changes are saved on the active working branch only. No commit, push, PR, merge, website deployment or Worker deployment performed for this request.

### Publication checkpoint — Fundamentals simplification

**By Arena.ai Agent**<br>
**Date:** 2026-11-12 (session date)<br>
**Preflight timestamp:** 2026-11-13 04:51:09 UTC (sandbox clock)

- User explicitly authorized deployment of this branch's Fundamentals changes.
- Restored ephemeral test dependencies with `npm ci` after the first browser preflight reported a missing Playwright module. Installation completed with zero reported vulnerabilities.
- Fresh deployment preflight passed: 40 JavaScript unit tests, 27 focused Fundamentals browser checks, all-tab browser smoke tests, and 15 cross-project browser scenarios. `git diff --check` passed. GitHub CI also runs the unchanged Python pipeline tests before merge.
- Confirmed GitHub Pages still publishes `main` at repository root. Publication will commit/push only `arena/bb6f4605-nse-rolling-returns-monthly`, open its PR, verify CI, merge that explicit PR and verify the Pages build. The PR records the final merge and deployment outcome.
- No financial dataset refresh or trimmed-EPS recalculation is included. No separate Cloudflare Worker deployment is required or performed.

---

## Fundamentals — plain gap percentage without badges

**By Arena.ai Agent**<br>
**Date:** 2026-11-12 (session date)<br>
**Validation timestamp:** 2026-11-13 05:08:55 UTC (sandbox clock)<br>
**Working branch:** `arena/869cd2d3-nse-rolling-returns-monthly`

- User requested a simple gap percentage, explicitly without restoring the badge. Added neutral inline `Gap: +20.0%` text to the Fundamentals legend. No background, border, verdict colors, overvalued/undervalued/fair-value labels, or loss badges.
- Formula: `(Price / EPS-based valuation − 1) × 100`, using actual unrounded currency values, displayed to one decimal with a positive sign where appropriate. Zero displays `0.0%`, not negative zero.
- Preserved the previous valuation-selection rule: selected green EPS Value takes precedence; selected Trim. EPS Value is used if green is unchecked or missing. A hover title identifies the denominator. The price remains the comparison reference even when its chart line is hidden.
- Hide the gap when neither applicable valuation series is selected. Nonpositive or missing valuations and invalid ratios show `Gap: —`, not a misleading financial percentage. Existing hover/zoom/pan/reset and checkbox refresh paths update the readout.
- Negative-EPS chart shading remains removed as requested. Rolling overlay, percentile heatmap and all badges remain removed; P/E still defaults off. No changes to chart formulas, embedded financial data, trimmed-EPS methodology, or other tabs.
- Updated README and added three focused browser scenarios for signed/zero gaps, neutral styling, hover and scale/timeframe consistency, green precedence/trimmed fallback, hidden selections, and missing/zero/negative valuation. Strengthened the existing hidden-valuation check.
- Validation passed: **40 JavaScript unit tests**, **30 focused Fundamentals checks** (including the 132-asset sweep and mobile layout), and the **all-tab browser smoke suite**. Whitespace checks passed. Python and the separate project-browser suite were not rerun for this small legend change.
- Saved on this working branch; no commit, push, PR, merge, website deployment, or Worker deployment performed for this request.

### Fundamentals — light green shading at gap ≤ −39%

**By Arena.ai Agent**<br>
**Date:** 2026-11-12 (session date)<br>
**Validation timestamp:** 2026-11-13 05:18:56 UTC (sandbox clock)<br>
**Working branch:** `arena/869cd2d3-nse-rolling-returns-monthly`

- Added light green background bands at 10% opacity for monthly observations with gap **≤ −39%**, including exactly −39%. Bands extend vertically within the chart plot and horizontally to midpoints between adjacent monthly observations; no interpolation of missing valuations is introduced.
- Extracted one shared gap calculation/valuation-selection helper for both the existing plain-text readout and shading. Green-first and selected trimmed fallback behavior is unchanged. Hiding both valuation series hides the shading; hiding Price alone does not change the comparison reference.
- Threshold uses the full-precision gap, not the rounded legend: −38.99% does not shade even though its readout rounds to −39.0%. Missing, zero, negative, and nonfinite valuations do not shade.
- Implemented a Fundamentals-only Chart.js background plugin, drawn behind grid/curves and clipped to plot bounds. It recalculates on visibility updates and supports zoom, pan, reset, timeframe changes, and both logarithmic/linear scales.
- Kept the gap readout plain: no valuation badges, verdicts, or loss warnings restored. This single-threshold shading does not restore the removed P/E percentile heatmap or negative-EPS shading. Embedded data, valuation curves, decomposition and all other tabs remain unchanged.
- Updated README and added two browser checks covering the inclusive boundary, rounded near-miss, invalid observations, exact monthly band boundaries, opacity, plot clipping, zoom, scale changes, hidden series, green precedence, and trimmed fallback.
- Validation passed: **40 JavaScript unit tests**, **32 Fundamentals browser checks**, **all-tab browser smoke tests**, **15 project browser scenarios**, and whitespace checks. No Python changes; Python tests not rerun.
- Includes the earlier plain-gap change already saved on this branch. No commit, push, PR, merge, or deployment performed for this request.

### Publication checkpoint — plain gap and −39% shading

**By Arena.ai Agent**<br>
**Date:** 2026-11-12 (session date)<br>
**Preflight timestamp:** 2026-11-13 05:35:39 UTC (sandbox clock)<br>
**Working branch:** `arena/869cd2d3-nse-rolling-returns-monthly`

- User explicitly authorized deployment of both the plain gap percentage and light green chart shading for gap ≤ −39%. No badges, percentile heatmap, or negative-EPS warnings are restored.
- Fresh local publication preflight passed after `npm ci`: 40 JavaScript tests, 32 focused Fundamentals checks, all-tab browser smoke suite, and 15 project browser scenarios. Whitespace checks passed.
- Confirmed GitHub Pages publishes from `main` at the repository root. Publication procedure: commit/push this branch only, open its PR, wait for full GitHub regression CI (including Python), merge the explicit PR, and verify the Pages deployment and post-merge CI. Final outcome will be recorded on the PR.
- No data refresh, valuation-methodology change, or Cloudflare Worker deployment is included.

---

## Fundamentals — error-only stock fetch status

**By Arena.ai Agent**<br>
**Date:** 2026-11-12 (session date)<br>
**Validation timestamp:** 2026-11-13 05:50:10 UTC (sandbox clock)<br>
**Working branch:** `arena/06e5ad6c-nse-rolling-returns-monthly`

- Removed the visible “Fetching … live”, live-success “Loaded … months …”, Indian cached-load, and US offline-cache success messages from the stock controls.
- Converted the status helper to error-only handling. The status span starts hidden and is removed from layout whenever empty, so normal loading/success cannot add a flex item or disturb toolbar spacing. Added `role="alert"` for errors; error content remains safely assigned via `textContent`.
- Preserved visible errors for failed fetches and unavailable US tickers, including the existing explicit cached-data warning when live refresh fails. New valid requests, stock-chip selection and asset-mode changes clear/hide stale errors. Older request failures cannot overwrite a newer selection.
- Kept the Fetch button disabled during an active live request and restored afterward; did not add replacement progress labels. Chart/data loading, caching, request-race protection, EPS reporting-basis notes, calculations, gap readout and shading are unchanged.
- Extended the offline browser smoke suite to verify no status text or layout box during pending requests, live success, Indian cache hits or US cache hits; preserved visible errors, reset behavior, button state and late-failure safety.
- Validation passed: **40 JavaScript tests**, **32 Fundamentals browser checks**, **15 project browser scenarios**, extended **all-tab browser smoke suite**, and whitespace checks. No financial data or Python changes; Python tests not rerun.
- Saved on the working branch only. No commit, push, pull request, merge, website deployment or Worker deployment performed for this request.

### Publication checkpoint — error-only stock status

**By Arena.ai Agent**<br>
**Date:** 2026-11-12 (session date)<br>
**Preflight timestamp:** 2026-11-13 05:52:49 UTC (sandbox clock)<br>
**Working branch:** `arena/06e5ad6c-nse-rolling-returns-monthly`

- User explicitly authorized deployment of the error-only Fundamentals stock-status change. Normal loading and success remain silent; genuine errors and cached-fallback warnings remain visible.
- Fresh local preflight passed after `npm ci`: 40 JavaScript tests, extended all-tab browser smoke tests including error-only status coverage, 32 Fundamentals checks and 15 project browser scenarios. Whitespace checks passed.
- Confirmed GitHub Pages publishes from `main` at repository root. Publication procedure: commit/push this branch only, open its PR, verify full GitHub CI (including Python), merge the explicit PR and verify Pages plus post-merge CI. Final deployment outcome will be recorded on the PR.
- No financial-data refresh, calculation change, or Cloudflare Worker deployment is included.
