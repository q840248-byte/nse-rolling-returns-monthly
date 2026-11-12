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
```

The browser suite uses Playwright Core with an npm-packaged Chromium binary on Linux. It serves the real app on an ephemeral loopback port, blocks external providers, and closes its server/browser on completion. You can provide `BROWSER_PATH` for an installed compatible Chromium browser. A screenshot is written under ignored `artifacts/`; no browser binaries, generated screenshots, or virtual environments should be committed.

The two original `test_tab9_*_cdp.py` scripts are retained. They hard-code Windows Edge paths and are not part of the portable suite.

GitHub Actions runs the offline suite on pushes and pull requests. The scheduled and manual data-update workflows share a per-branch concurrency group to avoid simultaneous automated writes.

## Fundamentals verification

`npm run test:fundamentals` runs focused Chromium checks using controlled return/valuation fixtures, then renders every embedded Fundamentals asset (56 indices, 67 Indian stocks, 9 US stocks). It checks exact horizons, price/EPS/multiple decomposition, median-based IV rebasing, loss/zero-EPS behavior, missing data, hover/zoom/reset consistency, series visibility, US suggestions, and the 390px layout.

The tab uses a full-history median P/E as a **valuation estimate**, not a point-in-time backtest. The index green series uses harmonized P/E/EPS; the orange supplied trimmed series intentionally shares that median baseline when available. No missing trimmed observations are extrapolated. Stock P/E is derived at render time from valid price/EPS for a consistent decomposition; the persisted caches are not rewritten. Historical EPS preprocessing and corporate-action adjustments still need source-level validation.

## Change history

See [VERSION_LOG.md](VERSION_LOG.md) for signed, UTC-timestamped changes, regression evidence, and remaining risks. Repository changes do not automatically imply that the Cloudflare Worker has been deployed or that live financial sources have been verified.
