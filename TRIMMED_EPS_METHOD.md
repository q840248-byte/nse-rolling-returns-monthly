# Orange-line methodology supplied by the owner

**Recorded by Arena.ai Agent**<br>
**Recorded at:** 2026-11-13 03:24 UTC<br>
**Status:** owner-described intended method; implementation and historical inputs not yet inspected.

This supplement updates the initial [audit](TRIMMED_EPS_AUDIT.md): the owner has now provided a written methodology and identified the external generating files. The formula is no longer wholly unknown. The Windows `file:///C:/...` links refer to files on the owner's machine, not uploaded or repository-accessible files. They were not opened or executed in this review.

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
4. **Upper-tail treatment:** use up to a 5% weight budget to cap extreme yields above `max(0.55, 8 × weighted_median_EY)`. The supplied description calls this a smooth windfall cap; its precise transformation is not specified.
5. **Aggregate and scale:** form the retained weighted-average yield, renormalizing retained weights, then multiply by the contemporaneous index level:

   ```text
   Y_trim = sum(adjusted_EY_i * retained_weight_i) / sum(retained_weight_i)
   trimmed_EPS_m = index_price_m * Y_trim_m
   orange_t = 100 * trimmed_EPS_t * median_PE / index_price_at_visible_start
   ```

   `adjusted_EY_i` makes the upper-tail cap explicit in this notation. If the actual script instead reduces weights without changing yields, that is a different implementation which must be documented and tested. The owner's original aggregate formula used `EY_i × w_i*`; the implementation is needed to resolve how the cap enters that formula.

The method is a **custom asymmetric weighted loss trim plus windfall cap**, not a conventional symmetric 5%-from-each-tail trimmed mean. It may affect less than 5% of weight on either side. Calling it simply “5% trimmed” hides these distinctions.

## Assessment of the stated design

### Mathematically reasonable components

- Aggregating earnings yields with appropriate portfolio weights avoids averaging company P/E ratios and can retain the sign of losses.
- Scaling a properly defined portfolio yield by an index level creates a synthetic index-scale earnings measure.
- Renormalizing after removing weight is coherent for a surviving/reweighted portfolio. It is not the earnings of the original, unchanged basket.
- The supplied final plotting formula agrees with the current frontend. The starting **price** is rebased to 100; orange and green need not themselves start at 100.

### Important qualifications and unresolved implementation details

1. **This is a model choice, not a proof of “true” earnings.** Losses are real economic outcomes; excluding them generally raises the estimated yield relative to the same untrimmed basket. An extreme earnings yield alone does not establish that a loss is temporary or a profit is one-off. The 0.55 and 8× thresholds need justification and sensitivity testing.
2. **Boundary handling matters.** If the worst-loss stock has 8% weight, removing the whole stock violates a 5% weight budget. Verify fractional removal, ties, whether both budgets use original total weight, and handling when all/most constituents have losses. `EY <= 0` includes zero earners as well as losses.
3. **The upper cap remains underspecified.** Need the exact cap value or smooth function; whether the median is computed before loss removal; treatment of nonpositive medians; how partial boundary weights are capped; and whether capped weight remains in the denominator. Winsorization changes values; trimming removes weight. They are not interchangeable.
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
