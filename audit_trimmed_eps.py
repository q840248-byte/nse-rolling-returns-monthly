#!/usr/bin/env python3
"""Audit embedded trimmed-EPS data; never refresh or modify financial history.

This is a structural/diagnostic audit, NOT a constituent-level validation of
5% trimming. Run: python -B audit_trimmed_eps.py --output TRIMMED_EPS_AUDIT.md
Python standard library only; no provider/network access.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def constant(html, name):
    match = re.search(r'const ' + re.escape(name) + r'\s*=\s*(\{.*?\});', html, re.S)
    if not match:
        raise ValueError(f"Missing constant: {name}")
    return json.loads(match[1], object_pairs_hook=unique_object)


def month_number(month):
    return int(month[:4]) * 12 + int(month[5:])


def inspect_series(name, values, prices, pes, factor=1.0):
    dates = sorted(d for d in values if MONTH.fullmatch(d))
    invalid_dates = sorted(set(values) - set(dates))
    invalid_values = [d for d, value in values.items() if not finite(value)]
    missing_price, missing_pe, ratios, jumps, gaps = [], [], [], [], []
    for d in dates:
        value, price, pe = values[d], prices.get(d), pes.get(d)
        if not finite(price) or price <= 0:
            missing_price.append(d)
        if not finite(pe) or pe <= 0:
            missing_pe.append(d)
        elif finite(value) and finite(price) and price > 0:
            # Mirrors the displayed 2-decimal harmonization for diagnostics.
            # Halfway floating-point ties can differ between Python and JS;
            # flags use large thresholds, not exact financial reconciliations.
            harmonized = float(f'{pe * factor:.2f}') if d < '2021-03' else pe
            if harmonized > 0:
                inferred = price / harmonized
                ratios.append((value / inferred, name, d, price, pe, harmonized, inferred, value))
    for previous, current in zip(dates, dates[1:]):
        if month_number(current) - month_number(previous) != 1:
            gaps.append((previous, current))
            continue
        before, after = values[previous], values[current]
        if finite(before) and finite(after) and before != 0:
            change = (after - before) / abs(before)
            jumps.append((abs(change), name, previous, current, before, after, change))
    return {
        'name': name, 'count': len(values), 'first': dates[0] if dates else '—',
        'last': dates[-1] if dates else '—', 'invalid_dates': invalid_dates,
        'invalid_values': invalid_values, 'gaps': gaps,
        'nonpositive': sum(finite(v) and v <= 0 for v in values.values()),
        'missing_price': missing_price, 'missing_pe': missing_pe,
        'ratios': ratios, 'jumps': jumps,
    }


def audit(html):
    trimmed = constant(html, 'ALL_INDICES_TRIMMED_EPS')
    pes = constant(html, 'RAW_PE')
    factors = constant(html, 'SUBSIDIARY_FACTOR_MAP')
    prices = {}
    for name, raw in re.findall(r'RAW\["([^"]+)"\]\s*=\s*(\{[^;]+\})\s*;', html):
        if name in prices:
            raise ValueError(f'Duplicate RAW assignment: {name}')
        prices[name] = json.loads(raw, object_pairs_hook=unique_object)
    rows = [inspect_series(name, data, prices.get(name, {}), pes.get(name, {}), factors.get(name, 1))
            for name, data in sorted(trimmed.items())]
    return rows, prices, pes, trimmed, factors


def report(html):
    rows, prices, pes, trimmed, factors = audit(html)
    total = sum(r['count'] for r in rows)
    ratio_flags = sorted((point for r in rows for point in r['ratios'] if point[0] > 100), reverse=True)
    jump_flags = sorted((point for r in rows for point in r['jumps'] if point[0] > .5), reverse=True)
    missing = sum(len(r['missing_pe']) for r in rows)
    absent = sorted(set(prices) - set(trimmed) - {'Gold (INR)', 'Silver (INR)'})
    lines = [
        '# Trimmed EPS audit — all embedded index series', '',
        '**By Arena.ai Agent**', '',
        '**Generated (UTC):** ' + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), '',
        '**Audited file:** `rolling_returns.html`', '',
        '**HTML SHA-256:** `' + hashlib.sha256(html.encode()).hexdigest() + '`', '',
        '## Verdict', '',
        '**The project does not provide enough evidence to certify the trimmed-EPS calculation for any of these indices.** '
        'It contains precomputed output values but no accessible constituent-trimming generator, input snapshots, or exclusion ledger. '
        'This is an **unverified** result, not proof that every value is wrong.', '',
        '**Follow-up:** the owner has now supplied the intended weighted earnings-yield methodology and external generator filenames. '
        'See [TRIMMED_EPS_METHOD.md](TRIMMED_EPS_METHOD.md) for the supplied rule, its assessment, and remaining implementation questions. '
        'Local Windows file links do not provide the actual script or inputs to this workspace.', '',
        'Earlier chart tests established rendering and arithmetic behavior, not the financial validity of the supplied trimmed data. '
        'This audit does not modify that data or replace the user’s method with a guessed formula.', '',
        '## What the webpage actually computes', '',
        '- The ordinary index EPS is inferred as index price / harmonized P/E, not loaded from a separate EPS series. '
        'For months before March 2021, P/E is multiplied by an index-specific fixed factor and rounded to two decimals.',
        '- The orange input is read from `ALL_INDICES_TRIMMED_EPS`. The webpage does not select constituents, rank them, discard 5%, or aggregate retained earnings. '
        'Existing tooltip/comment claims about constituent-level 5% trimming are not substantiated by a reproducible calculation in this repository.',
        '- The orange plotted ordinate is `100 × supplied trimmed EPS × median multiple / first visible index price`. '
        'It is rebased **trimmed intrinsic value**, not an unscaled EPS value. Hover text shows the supplied EPS separately.',
        '- For all currently covered indices with a positive raw/harmonized P/E history, orange and green share the raw/harmonized full-history median P/E. '
        'Although the renderer collects Price / trimmed-EPS multiples, it does not normally use their own median. '
        'This is a shared valuation assumption, not evidence of a correctly computed trim.',
        '- The scheduled and full-history workflows invoke `update_data.py`, which updates prices, commodities, and P/E. '
        'No trimmed-EPS rebuild is present in that path. Raw updates and this static table can therefore become unsynchronized.', '',
        '### Source locations', '',
    ]
    for token, description in [
        ('const ALL_INDICES_TRIMMED_EPS =', 'Stored trimmed-EPS table'),
        ('function getHarmonizedPeSeries(key)', 'Historical P/E harmonization'),
        ("epsMap[d] = priceMap[d] / peData.values[d]", 'Index EPS inference'),
        ('var medianTrimmedPe = rawMedianDirect', 'Shared median-multiple selection'),
        ('var tIvReb =', 'Orange plotted-value formula'),
    ]:
        position = html.find(token)
        if position >= 0:
            lines.append(f'- `{ROOT.name}/rolling_returns.html:{html[:position].count(chr(10)) + 1}` — {description}.')
    lines += [
        '- `update_data.py`, `update_commodities.py`, `build_top_stocks.py`, and `.github/workflows/` were inspected for data-generation/update responsibilities. '
        '`build_top_stocks.py` processes individual-stock histories; it is not an index constituent-trimming generator.', '',
        '## Whole-table structural checks', '',
        f'- **{len(rows)} index series; {total:,} supplied observations.**',
        f'- Invalid month keys: **{sum(len(r["invalid_dates"]) for r in rows)}**; non-finite/non-numeric EPS values: **{sum(len(r["invalid_values"]) for r in rows)}**.',
        f'- Non-positive supplied EPS values: **{sum(r["nonpositive"] for r in rows)}**; internal calendar gaps: **{sum(len(r["gaps"]) for r in rows)}**.',
        f'- Missing matching positive price observations: **{sum(len(r["missing_price"]) for r in rows)}**.',
        f'- Supplied EPS months without a matching positive stored P/E: **{missing}**, across **{sum(bool(r["missing_pe"]) for r in rows)}** indices. '
        'This prevents same-month comparison with inferred EPS; it does not, by itself, disprove an independent constituent calculation.',
        '- Latest trimmed month distribution: ' + ', '.join(f'`{d}`: {n} indices' for d, n in sorted(Counter(r['last'] for r in rows).items())) + '.',
        '- Price-series indices with no trimmed table: ' + (', '.join(absent) if absent else 'none (excluding gold and silver)') + '.',
        '- Positivity, continuity, coverage, or a smooth curve cannot establish that historical members, earnings, and weights were correct.', '',
        '## Specific observations requiring reconciliation', '',
        '### Large differences from the inferred EPS comparator', '',
        'Screening rule: supplied trimmed EPS >100× price/harmonized-P/E EPS. This arbitrary diagnostic threshold is **not a correctness test**. '
        'Near-zero aggregate earnings can legitimately create very large ratios; the stored P/E itself also needs source verification. '
        'These values must not be automatically clipped or “repaired.”', '',
        '| Index | Month | Index price | Stored P/E | Inferred harmonized EPS | Supplied trimmed EPS | Ratio |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    for ratio, name, month, price, pe, harmonized, inferred, value in ratio_flags:
        lines.append(f'| {name} | {month} | {price:,.2f} | {pe:,.2f} | {inferred:.4f} | {value:,.2f} | {ratio:,.1f}× |')
    lines += ['', '### Large consecutive-month changes', '',
              'Screening rule: absolute change >50% between adjacent calendar months. Reconstitution, weighting changes, financial results, or a source error can all cause jumps. '
              'The aggregate curve alone cannot identify the cause; index EPS growth can include composition effects, not just underlying company earnings growth.', '',
              '| Index | Interval | Before | After | Change |', '|---|---|---:|---:|---:|']
    for _, name, previous, current, before, after, change in jump_flags:
        lines.append(f'| {name} | {previous} → {current} | {before:,.2f} | {after:,.2f} | {change:+.1%} |')
    lines += ['', '## Per-index findings', '',
              '**Financial calculation status for every row: UNVERIFIED — supplied method is documented, but generator and historical source inputs remain unavailable.** '
              '“No P/E” counts trimmed observations lacking a positive stored P/E; “largest move” is a diagnostic, not a failure.', '',
              '| Index | Trimmed history | Months | No P/E | Largest monthly move |', '|---|---|---:|---:|---:|']
    for r in rows:
        largest = max((point[0] for point in r['jumps']), default=0)
        lines.append(f'| {r["name"]} | {r["first"]} → {r["last"]} | {r["count"]} | {len(r["missing_pe"])} | {largest:.1%} |')
    lines += ['', '## Nifty 50: why the two EPS baselines need care', '',
              '| Month | Stored price | Stored P/E | Price / stored P/E | Price / harmonized P/E (green EPS) | Supplied trimmed EPS |',
              '|---|---:|---:|---:|---:|---:|']
    for d in ['2009-01', '2020-09', '2021-02', '2021-03', '2026-11']:
        name = 'Nifty 50'
        if not all(d in source.get(name, {}) for source in [prices, pes, trimmed]):
            continue
        price, pe, value = prices[name][d], pes[name][d], trimmed[name][d]
        harmonized = float(f'{pe * factors.get(name, 1):.2f}') if d < '2021-03' else pe
        lines.append(f'| {d} | {price:,.2f} | {pe:.2f} | {price/pe:.2f} | {price/harmonized:.2f} | {value:,.2f} |')
    lines += ['',
        'The harmonization factor is an assumption applied to old observations, not a reconstruction of each historical constituent’s consolidated financial statements. '
        'The orange generator must use a compatible earnings/accounting/index scale before these lines can be interpreted as a clean raw-versus-trimmed comparison.', '',
        '## What is needed to validate your method', '',
        '1. The actual `compute_pit_trimmed_eps.py` generator identified by the owner, plus its inputs and configuration. The written methodology is now recorded in the supplement.',
        '2. Resolve the remaining cap-function, fractional boundary, tie, median-timing, and missing-data details. The owner specifies earnings-yield ranking and separate up-to-5%-of-weight loss/cap budgets.',
        '3. For each historical date: constituent identifiers, effective memberships, index weights/free-float or cap adjustments, and prices.',
        '4. Matching TTM earnings with declared standalone/consolidated and basic/diluted basis, share/split adjustments, loss/exceptional-item treatment, and reporting availability dates.',
        '5. Verify the described retained-weight renormalization and index-price scaling in the script; reconcile the untrimmed aggregate against the official baseline.',
        '6. A reproducible ledger: removed names, their metric values/weights, retained weight total, intermediate earnings aggregate, and final EPS.', '',
        'A simple average of company EPS is generally not a comparable index EPS: per-share units, splits, and index weighting matter. '
        'That is a methodological caution, not a claim that your unavailable generator actually uses that shortcut.', '',
        '### Aggregation identity — not an implementation of the custom cap', '',
        'With portfolio-consistent weights `w_i` and earnings yields `y_i = TTM EPS_i / share price_i`, an aggregate yield is `Y = Σ(w_i × y_i)`. '
        'If your rule removes a set of names and reweights the survivors, `Y_trim = Σ_retained(w_i × y_i) / Σ_retained(w_i)`, '
        'and `index_level × Y_trim` is one synthetic index-scale earnings measure. '
        'Leaving the retained weights unnormalized defines a different measure. '
        'The supplied method uses renormalization and also adds an upper-tail cap; this identity alone does not implement it or establish equivalence to NSE’s convention.', '',
        '## Recommended next step', '',
        'Supply the actual generator identified in the methodology supplement and at least one constituent-level input snapshot. '
        'Reproduce Nifty 50 on an ordinary month, then a flagged stress month, then equal-weight/capped/momentum indices before certifying all 56. '
        'Until that is done, treat orange as an unverified custom earnings/valuation estimate—not a validated 5% trimmed-earnings benchmark.', '',
        '## Repository-history provenance check', '',
        'The checkout is shallow, so GitHub commit/file/tree APIs were also inspected. '
        'This was targeted investigation of the relevant implementation revisions, not an exhaustive search of every branch or external workspace.', '',
        '- [`71e3a9d465`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/71e3a9d465aa8bebdf423aae15a2716bd3c20f02) introduced an embedded Nifty 50 trimmed-EPS table.',
        '- [`d61abc3b91`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/d61abc3b9140a41d7481de4a15402a476918ef8f) used the Nifty 50 table but derived other indices’ orange EPS as '
        '`price / clamp(current P/E, full-history 5th percentile P/E, full-history 95th percentile P/E)`. '
        'That old algorithm was historical P/E winsorization, **not** cross-sectional constituent EPS trimming. '
        'It is not the current table-lookup implementation.',
        '- [`3fcdfc45e7`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/3fcdfc45e77d0836ecfa64e337271d4fca862f05), '
        '[`679c4acd0f`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/679c4acd0fb27362291912e037d5bd2cb646a6fc), '
        '[`e1b84d4f34`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/e1b84d4f34b5f1ed44aa6d4bee3dc741e76a4e7b), and '
        '[`5462cdc30e`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/5462cdc30e9a81127ec37d413dba7dd17253a17b) '
        'have messages describing company-level trimming, point-in-time constituents, weighting, and momentum/equal-cap rules. '
        'Their changed-file lists contain only `rolling_returns.html`; they do not supply a separate reproducible generator or input snapshots.',
        '- [`0bc7e9b2bb`](https://github.com/q840248-byte/nse-rolling-returns-monthly/commit/0bc7e9b2bb7ea8104848cbccc2d7a1dcbd88cc0d) describes restricting history starts and sharing a median multiple. '
        'Its tree, and the inspected trees at `d61abc3b91`, `3fcdfc45e7`, and `679c4acd0f`, contain no identifiable constituent-trimming pipeline or constituent source dataset.',
        '- Commit messages describe intended work; they do not prove historical membership, weights, earnings, or rounding were correct. '
        'The external script/notebook or prior working files may still exist outside this repository.', '',
        '## Scope and limits', '',
        '- Audit inputs are the checked-out HTML and repository scripts, not independently downloaded NSE constituent/financial histories.',
        '- No live NSE, Screener, SEC, or Yahoo verification was performed. GitHub deployment/source identity can be checked separately through its API.',
        '- On the audit date November 2026 is incomplete; a `2026-11` key alone does not establish final month-end availability or matching as-of timestamps.',
        '- This script checks stored output and generates this report only. It never writes the webpage, adjusts a financial value, or runs a data update.', '',
    ]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, default=ROOT / 'rolling_returns.html')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = report(args.html.read_text(encoding='utf-8'))
    if args.output:
        args.output.write_text(text, encoding='utf-8')
        print(f'Audit report written to {args.output}; financial data was not changed.')
    else:
        print(text)


if __name__ == '__main__':
    main()
