# NSE Rolling Returns — single-page application

`rolling_returns.html` is the application: one webpage with shared asset selection, allocation controls, and calculation helpers. No frontend build step is required.

## Run locally

From the repository root:

```sh
python -m http.server 8000 --bind 0.0.0.0
```

Open `/rolling_returns.html` on the server. Chart.js, Hammer, and the zoom plugin have bundled fallbacks under `vendor/`. Web fonts and Excel-export dependencies may still require internet access.

## Data and supporting services

| File | Role |
| --- | --- |
| `rolling_returns.html` | UI, calculations, and embedded price, valuation, and stock datasets |
| `update_data.py` | Incremental or `--full` NSE price/P/E and commodity updates |
| `update_commodities.py` | Commodity CSV generation; `--update-html` patches the asset-specific RAW blocks |
| `build_top_stocks.py` | Processes stock Price/EPS histories; synchronizes JSON, standalone JS, and the HTML's embedded stock cache |
| `stock-proxy-worker.js` | Cloudflare Worker for live Indian stock search and fundamentals |
| `pe_index_mapping.json` | Provider identifiers for P/E requests |

Run data scripts from the repository root. They contact external financial providers; **do not run them just to test code**. The offline test suite uses mocks and temporary files instead.

Commodity pipeline output uses **INR per 10 grams of gold** and **INR per kilogram of silver**. The Yahoo symbols `GC=F` and `SI=F` are futures proxies, not a guaranteed physical spot or retail quote. Currency conversion does not include taxes, duties, fees, or transaction costs.

The stock builder preserves previously cached symbols if their refresh fails and refuses to overwrite outputs if no stock can be processed. Its local `raw_screener_cache.json` is a reusable input cache; callers wanting a fresh network rebuild can invoke `build_top_stocks.main(force_refresh=True)`. The stock cache is not refreshed by the scheduled NSE workflow.

## Calculation conventions and limitations

- Dynamic P/E bands require 60 consecutive positive monthly observations; incomplete windows and undefined zero-dispersion Z-scores remain unavailable. Bands are descriptive statistics, not calibrated investment signals.
- Latest Stats decomposition uses exact, shared calendar endpoints for price/EPS/multiple growth; sparse-history drawdown durations use elapsed calendar months. The displayed recovery duration is the longest observed underwater span, including ongoing episodes.
- Cashflow input bounds are checked before simulation. Single-journey duration is derived from the actual dates (the years input is an end-date shortcut); rolling windows require whole years.

- Rolling asset CAGR uses actual calendar-month endpoints. Missing endpoints are not interpolated.
- Cashflow simulations use a **monthly-rebalanced positive-weight portfolio**. Missing monthly prices are represented as missing, not as 0% returns or a change of allocation. Single journeys require continuous history; rolling cohorts crossing gaps are excluded.
- The rolling-return portfolio endpoint calculation retains the pre-existing buy-and-hold/available-asset convention. It is **not the same portfolio model** as monthly-rebalanced cashflows. This distinction needs a future explicit UI/model decision; it was not silently changed in the review.
- SIP deposits occur initially and at each month end, including the terminal month. SWP withdrawals occur at month end; annual inflation begins with withdrawal 13.
- STP models twelve fixed principal transfers and continued liquid interest on the residual balance.
- XIRR uses month fractions of a year, not actual trading-day dates. It solves a bracketed root; non-conventional cashflows may have multiple or no roots.
- **Smoothed P/E** uses 3- or 5-year nominal inferred earnings and requires a complete monthly window. It is not inflation-adjusted ten-year Shiller CAPE.
- Yield Gap leaves missing bond yields blank rather than inventing a historical rate.
- Current-month observations can be provisional. Embedded values, EPS adjustments, consolidation splices, and valuation thresholds are not independently audited financial data.

## Offline regression tests

Python 3.11 and Node.js 22.17+ are recommended.

```sh
python -m venv .venv
# Linux/macOS; on Windows use .venv\Scripts\activate
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v

npm ci
npm test
npm run test:browser
npm run test:fundamentals
npm run test:project
```

The browser suite uses Playwright Core with an npm-packaged Chromium binary on Linux. It serves the real app on an ephemeral loopback port, blocks external providers, and closes its server/browser on completion. You can provide `BROWSER_PATH` for an installed compatible Chromium browser. A screenshot is written under ignored `artifacts/`; no browser binaries, generated screenshots, or virtual environments should be committed.

The two original `test_tab9_*_cdp.py` scripts are retained. They hard-code Windows Edge paths and are not part of the portable suite.

GitHub Actions runs the offline suite on pushes and pull requests. The scheduled and manual data-update workflows share a per-branch concurrency group to avoid simultaneous automated writes.

## Fundamentals verification

`npm run test:fundamentals` runs focused Chromium checks using controlled return/valuation fixtures, then renders every embedded Fundamentals asset (56 indices, 67 Indian stocks, 9 US stocks). It checks exact decomposition horizons, median-based curve rebasing, loss/zero-EPS behavior, missing data, hover/zoom/reset consistency, every combination of the four series toggles, default P/E visibility, US suggestions, and the 390px layout.

The four controls are **Price**, **EPS Value**, **P/E**, and **Trim. EPS Value**. P/E starts unchecked; only checked series appear in the legend. Currency values show actual price or EPS-based valuation, followed by the corresponding plotted rebased value, for example `₹1226.9 (126)`; US stocks use `$`. P/E displays only its multiple, such as `20.6x`. Missing values remain `—`; zero and negative valuation amounts are retained in the legend, although nonpositive points cannot be plotted on a logarithmic axis. Trimmed values apply only to indices.

The Fundamentals rolling-CAGR overlay, rolling-horizon controls, percentile calculation/heatmap, and auxiliary valuation badges have been removed. Chart timeframe buttons and the 3Y/5Y/10Y return-decomposition table remain. Rolling Returns and the other application tabs are unaffected.

The EPS curves retain their existing **EPS × full-history median P/E** valuation scaling—not a new raw-EPS rebasing algorithm. The index green curve uses harmonized P/E/EPS; orange intentionally shares that median baseline when available. No missing trimmed observations are extrapolated. Stock P/E is derived from valid price/EPS for consistent decomposition; persisted caches are not rewritten. The full-history median is a valuation estimate, not a point-in-time backtest. Historical source/EPS/corporate-action accuracy remains outside these UI checks.

## Trimmed-EPS methodology audit

See [TRIMMED_EPS_AUDIT.md](TRIMMED_EPS_AUDIT.md) for the all-56-index review, diagnostic dates, provenance findings, and the inputs needed to validate the custom calculation. **The orange data is not yet constituent-validated.** The page reads precomputed values; no reproducible trimming generator or complete historical constituent/weight/earnings dataset was found in the inspected repository revisions. The owner subsequently supplied the intended formula and external script filenames; see [TRIMMED_EPS_METHOD.md](TRIMMED_EPS_METHOD.md). A subsequently supplied complete trimming-function excerpt is preserved and tested in `tests/test_supplied_trim_function.py`; it implements the cap but exhibits loss-gate and weighted-median discontinuities documented in the supplement. The full generator, caller, and historical inputs have not been uploaded or inspected. The scheduled updater does not rebuild that table. Passing chart tests does not certify its financial methodology.

Regenerate the offline structural report without changing application data:

```sh
python -B audit_trimmed_eps.py --output TRIMMED_EPS_AUDIT.md
python -B -m unittest discover -s tests -p test_trimmed_eps_audit.py -v
python -B -m unittest discover -s tests -p test_supplied_trim_function.py -v
```

The report checks dates, coverage, duplicate keys, numerical validity, comparator availability, and large changes. Its flags are reconciliation leads, not evidence that an observation is necessarily wrong. The report also includes the manually investigated implementation/history findings; they should be re-reviewed when the application methodology changes.

## Full-project review

See [PROJECT_REVIEW.md](PROJECT_REVIEW.md) for the all-ten-tab review, reproducible fixes, verification counts, and remaining source/browser/methodology limits. `npm run test:project` adds cross-tab P/E/dynamic-band checks, the 56-index valuation sweep, empty-state and selector regressions, allocation/selection scenarios, an offline Excel writer fixture, keyboard collapse state, and all-tab 390px containment. This complements—not replaces—the existing general and Fundamentals suites.

## Change history

See [VERSION_LOG.md](VERSION_LOG.md) for signed, UTC-timestamped changes, regression evidence, and remaining risks. Repository changes do not automatically imply that the Cloudflare Worker has been deployed or that live financial sources have been verified.
