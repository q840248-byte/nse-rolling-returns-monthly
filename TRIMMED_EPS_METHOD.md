# Orange-line methodology supplied by the owner

**Recorded by Arena.ai Agent**<br>
**Recorded at:** 2026-11-13 03:24 UTC<br>
**Status:** owner-supplied complete trimming-function excerpt now inspected and tested; full generator, caller, and historical inputs remain unavailable.

This supplement updates the initial [audit](TRIMMED_EPS_AUDIT.md): the owner has now provided a written methodology and identified the external generating files. The formula is no longer wholly unknown. The Windows `file:///C:/...` links refer to files on the owner's machine, not uploaded or repository-accessible files. They were not opened or executed in this review. In a subsequent message the owner pasted the complete trimming function; the excerpt has now been tested independently as described below.

## Identified external artifacts

- `compute_pit_trimmed_eps.py`: owner identifies lines 174–222 as the core `weighted_trimmed_ey(data, trim_frac=0.05)` function and lines 790–850 as the aggregation loop.
- `all_indices_trimmed_eps_pit.json`: claimed source of the embedded `ALL_INDICES_TRIMMED_EPS` table.
- `hist_pit_work/pdf_weights_2013_2022.json`: claimed historical weights extracted from NSE monthly PDFs. The description mentions coverage through 2022/2026; actual coverage needs inspection.
- Supporting historical memberships, stock earnings/prices, free-float shares, and factor inputs are also needed to reproduce results.

These filenames and line references are owner-supplied provenance leads, not independently verified file contents.

## Intended calculation, as supplied

1. **Constituent earnings yield:** `EY_i = TTM consolidated EPS_i / stock price_i`. This is equivalent to `1 / P/E_i` only where that numerical P/E is defined and nonzero; calculating directly from earnings and positive prices also handles zero and negative earnings.
2. **Point-in-time weights:** use official monthly PDF weights where available; otherwise the described index-specific reconstruction uses free-float capitalization, or normalized 6-/12-month momentum with daily-volatility adjustment and iterative capping. Exact definitions, eligible index families, rebalance dates, and input dates await code inspection.
3. **Loss-tail removal:** sort ascending by earnings yield and remove up to **5% of total index weight**, restricted to observations with `EY_i <= 0`. If qualifying weight is only 2%, remove only 2%; do not continue trimming healthy positive earners.
4. **Upper-tail treatment:** use up to a 5% weight budget to cap extreme yields above `max(0.55, 8 × weighted_median_EY)`. The subsequent complete excerpt specifies partial-weight winsorization: capped weight contributes at the threshold, uncapped weight at its original yield; all that weight stays in the denominator. Continuity is qualified below.
5. **Aggregate and scale:** form the retained weighted-average yield, renormalizing retained weights, then multiply by the contemporaneous index level:

   ```text
   Y_trim = sum(adjusted_EY_i * retained_weight_i) / sum(retained_weight_i)
   trimmed_EPS_m = index_price_m * Y_trim_m
   orange_t = 100 * trimmed_EPS_t * median_PE / index_price_at_visible_start
   ```

   `adjusted_EY_i` makes the upper-tail cap explicit in this notation. The supplied complete function splits a boundary constituent into capped and uncapped portions; it does not remove capped weight. The full script and its caller still need inspection.

The method is a **custom asymmetric weighted loss trim plus windfall cap**, not a conventional symmetric 5%-from-each-tail trimmed mean. It may affect less than 5% of weight on either side. Calling it simply “5% trimmed” hides these distinctions.

## Assessment of the stated design

### Mathematically reasonable components

- Aggregating earnings yields with appropriate portfolio weights avoids averaging company P/E ratios and can retain the sign of losses.
- Scaling a properly defined portfolio yield by an index level creates a synthetic index-scale earnings measure.
- Renormalizing after removing weight is coherent for a surviving/reweighted portfolio. It is not the earnings of the original, unchanged basket.
- The supplied final plotting formula agrees with the current frontend. The starting **price** is rebased to 100; orange and green need not themselves start at 100.

### Important qualifications and unresolved implementation details

1. **This is a model choice, not a proof of “true” earnings.** Losses are real economic outcomes; excluding them generally raises the estimated yield relative to the same untrimmed basket. An extreme earnings yield alone does not establish that a loss is temporary or a profit is one-off. The 0.55 and 8× thresholds need justification and sensitivity testing.
2. **Boundary handling is now explicit in the supplied function.** An 8%-weight worst-loss constituent loses 5 percentage points of weight, not its whole weight. Both budgets use original total input weight. All-loss baskets can remain negative. `EY <= 0` includes zero earners; its hard cutoff creates the discontinuity demonstrated below.
3. **The upper cap is now implemented in the supplied excerpt.** It uses the original basket’s weighted median before loss removal, caps only the affected weight fraction, and retains capped weight in the denominator. The threshold is `max(0.55, 8 * max(0.01, median))`; the inner 0.01 floor is redundant with the outer 0.55 floor. This resolves the missing-code question, but not the broader continuity claim or provenance of stored outputs.
4. **“Exact historical weights” is not yet established.** Official PDF snapshots and reconstructed weights are different evidence types. Verify date alignment, coverage, historical free-float shares, rebalance schedules, caps, and methodology changes for each index. A single momentum formula or universal 5% cap cannot be assumed correct for every factor index. A 5% cap requires at least 20 eligible names for weights to sum to one, so the solver also needs an explicit infeasibility check.
5. **Historical membership alone does not eliminate look-ahead.** Earnings must have been published by the observation date, with compatible price/share adjustments. Reconstructed factor scores and free-float inputs must also be available at that date. Missing constituent earnings must not silently turn into an undocumented additional trim.
6. **Reconcile before trimming.** For representative dates, compare `sum(weight_i × EY_i)` with the index's reported earnings yield under compatible accounting, weighting, and loss conventions. Explain material differences before attributing the orange/green gap to the custom trim.
7. **The frontend median is not untouched official NSE data.** The current app takes a median of its harmonized historical P/E series, adjusting pre-March-2021 observations. Sharing that multiple makes the scaling consistent, but does not establish fair value or remove accounting-basis differences. The owner's example multiples are not certified constants; they depend on the actual history. A full-history median also uses later information when valuing earlier dates.
8. **The refresh gap remains.** Identifying a local generator does not add it to the repository's scheduled update pipeline. No reproducible automated trimmed-EPS update has yet been verified.

## Evidence needed next

Upload or add the actual generator and its relevant input schema/sample data, rather than local file links. First reproduce an ordinary Nifty 50 month and a flagged stress month with a ledger containing:

- membership and input/reporting dates;
- original weights and their sum;
- raw earnings yields and the weighted median;
- removed fractions and capped yields, with separate tail budgets;
- retained-weight sum and untrimmed/adjusted weighted sums;
- final index-scale EPS and agreement with the embedded value to the stated rounding tolerance.

Then extend to equal-weight, capped, momentum, and other supported index families. The supplied written method narrows the audit substantially, but does **not yet validate the 5,889 stored results**. No replacement generator or financial values were invented for this pull request.


## Complete-function follow-up: executable boundary review

**By Arena.ai Agent**<br>
**Reviewed:** 2026-11-13 (UTC; detailed timestamp in VERSION_LOG.md)

The owner supplied a complete function attributed to `compute_pit_trimmed_eps.py` lines 176–224. Its body is preserved unchanged as an explicitly labelled **chat-supplied audit fixture** in `tests/test_supplied_trim_function.py`. This is not the original file and is not connected to the financial pipeline.

### Verified behavior of the excerpt

Eleven executable tests cover empty/zero-weight input, unchanged ordinary positive yields, partial loss removal, stopping below the loss budget, partial windfall capping, simultaneous tail budgets, all-loss output, continuity at a fixed upper threshold, two actual discontinuities, and dependence on input sorting.

- A 10%-weight stock with EY = 1.0, with all other stocks at EY = 0.05, has only 5 percentage points capped to 0.55. The other 5 percentage points still contribute at EY = 1.0. Aggregate output is **0.1225**, not the result of capping the entire stock.
- With a fixed median/threshold and fixed weights, the upper cap is continuous as a stock's yield crosses the threshold. It has a slope change rather than a jump. That limited continuity claim is supported.
- Loss removal and the upper cap each have their own budget based on **total input weight**, not 5% of the already reduced basket. If the caller drops missing constituents first, that input total need not represent the full official index; coverage remains a caller-level question.

### Confirmed counterexample 1: loss-to-profit crossing

Hold 95% of weight at a 5% yield and the remaining 5% at a tiny yield near zero:

| Yield of the 5%-weight constituent | Function output |
|---|---:|
| `-0.000000001` | 5.000000% |
| `0` | 5.000000% |
| `+0.000000001` | approximately 4.750000% |

The negative/zero observation is removed, leaving a 0.95 denominator; the barely positive observation is kept, restoring a 1.00 denominator. Output **drops by approximately 0.25 percentage points (5% relative)** when the constituent improves from a tiny loss to a tiny profit. With fixed index price, starting-price divisor, and valuation multiple, the modeled orange IV drops proportionally.

This is a direct consequence of the specified hard loss gate plus renormalization, not a floating-point artifact or a claim about a particular historical month. If intentional, document it; if continuity through zero is required, the method needs a separately agreed redesign rather than a silent patch.

### Confirmed counterexample 2: discrete weighted median

Use sorted yields `[0.05, 0.10, 1.0]`. Changing weights from `[0.500001, 0.449999, 0.05]` to `[0.499999, 0.450001, 0.05]` switches the median from 0.05 to 0.10 and the threshold from 0.55 to 0.80. Output jumps from **0.09749995 to 0.11000005**. Thus even the upper-tail mechanism is not globally continuous when its weighted median changes discretely.

### Preconditions and attribution corrections

- The function **does not sort** its input. Its docstring requires ascending EY; the unseen caller must enforce this. A deliberately unsorted fixture changes which losses are removed and changes the result.
- The excerpt does not validate finite yields, finite nonnegative weights, or the allowed `trim_frac` range. Such validation may exist in the caller; its absence from this excerpt is not proof that production accepts bad inputs.
- A fixed reporting lag is only an approximation to point-in-time availability, as acknowledged in the owner's follow-up. Historical memberships and source snapshots remain unverified.
- `getHarmonizedPeSeries()` in this repository itself multiplies pre-March-2021 P/E by `getSubsidiaryFactor(key)` and rounds to two decimals. The available evidence does **not** support attributing this particular transformation to NSE having back-adjusted the supplied history.
- The current embedded dataset has 56 indices, while the supplied handoff describes 53. Reconcile coverage/output versions before claiming the supplied generator produced every current series.

**Updated verdict:** the supplied function implements the stated gated loss trim and partial-weight windfall cap under its input preconditions. The broad “continuous without cliffs” description is false. These tests do not reproduce or certify the embedded historical orange-line dataset.
