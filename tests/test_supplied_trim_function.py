"""Test the function pasted by the owner, NOT the unavailable original build script.

This audit fixture is not imported by the application or data-update pipeline.
Passing tests characterize the snippet; they do not validate historical datasets.
"""
import unittest


# Copied from the owner's complete chat excerpt; implementation left unchanged.
def weighted_trimmed_ey(data, trim_frac=0.05):
    """
    Loss-and-windfall-gated 5% weighted Earnings Yield trim:
    - Trims worst loss-making tail (ey <= 0) up to `trim_frac` (5%) of total weight.
    - Smoothly caps extreme one-off windfall upper tail (ey > max(0.55, 8.0 * w_median_ey))
      down to windfall_thresh (up to 5% weight) so boundary crossings are continuous without cliffs.
    data: [(ey, w, sym)] sorted ascending by ey.
    """
    w_tot = sum(w for _, w, _ in data)
    if w_tot <= 0:
        return None

    # 1. Weighted median EY (walk sorted list until cumulative weight >= 50%)
    cum_m = 0.0
    w_med = data[len(data) // 2][0]
    for ey, w, _ in data:
        cum_m += w
        if cum_m >= 0.5 * w_tot:
            w_med = ey
            break
    windfall_thresh = max(0.55, 8.0 * max(0.01, w_med))  # e.g. if median EY = 0.05, thresh = 0.55

    lo_budget = w_tot * trim_frac  # 5% of total weight for loss tail
    hi_budget = w_tot * trim_frac  # 5% of total weight for windfall cap

    # 2. Consume lo_budget from ascending loss tail strictly where ey <= 0
    kept = []
    for ey, w, sym in data:
        w_keep = w
        if ey <= 0.0 and lo_budget > 0.0:
            cut = min(w_keep, lo_budget)
            w_keep -= cut
            lo_budget -= cut
        if w_keep > 1e-12:
            kept.append([ey, w_keep, sym])

    # 3. Cap extreme windfall upper tail (up to hi_budget = 5%) — iterate from top descending
    ey_w_sum = 0.0
    w_sum = 0.0
    for idx in range(len(kept) - 1, -1, -1):
        ey, w, _ = kept[idx]
        w_sum += w
        if ey > windfall_thresh and hi_budget > 0.0:
            cap_w = min(w, hi_budget)
            hi_budget -= cap_w
            # Capped portion contributes at windfall_thresh; remainder at actual ey
            ey_w_sum += cap_w * windfall_thresh + (w - cap_w) * ey
        else:
            ey_w_sum += ey * w

    return (ey_w_sum / w_sum) if w_sum > 0 else None


class SuppliedTrimFunctionTests(unittest.TestCase):
    def test_empty_or_zero_weight_returns_none(self):
        self.assertIsNone(weighted_trimmed_ey([]))
        self.assertIsNone(weighted_trimmed_ey([(.05, 0, 'A')]))

    def test_ordinary_positive_yields_unchanged(self):
        self.assertAlmostEqual(weighted_trimmed_ey([(.04, .4, 'A'), (.06, .6, 'B')]), .052)

    def test_partial_loss_trim_respects_original_five_percent_budget(self):
        value = weighted_trimmed_ey([(-.2, .08, 'LOSS'), (.05, .92, 'OTHER')])
        self.assertAlmostEqual(value, (-.2 * .03 + .05 * .92) / .95)

    def test_two_percent_loss_weight_does_not_remove_positive_weight(self):
        self.assertAlmostEqual(weighted_trimmed_ey([(-.2, .02, 'LOSS'), (.05, .98, 'OTHER')]), .05)

    def test_partial_windfall_cap_keeps_full_weight_in_denominator(self):
        value = weighted_trimmed_ey([(.05, .90, 'OTHER'), (1.0, .10, 'SPIKE')])
        self.assertAlmostEqual(value, .05 * .9 + .55 * .05 + 1.0 * .05)
        self.assertAlmostEqual(value, .1225)

    def test_both_budgets_based_on_original_weight(self):
        value = weighted_trimmed_ey([(-.2, .05, 'LOSS'), (.05, .85, 'OTHER'), (1., .10, 'SPIKE')])
        self.assertAlmostEqual(value, (.05 * .85 + .55 * .05 + 1. * .05) / .95)

    def test_all_losses_can_remain_negative(self):
        self.assertAlmostEqual(weighted_trimmed_ey([(-.2, .4, 'A'), (-.1, .6, 'B')]), (-.2 * .35 - .1 * .6) / .95)

    def test_windfall_threshold_crossing_continuous_with_fixed_median(self):
        eps = 1e-9
        before = weighted_trimmed_ey([(.05, .95, 'A'), (.55 - eps, .05, 'B')])
        after = weighted_trimmed_ey([(.05, .95, 'A'), (.55 + eps, .05, 'B')])
        self.assertLess(abs(after - before), eps)

    def test_loss_zero_crossing_has_real_discontinuity(self):
        eps = 1e-9
        before = weighted_trimmed_ey([(-eps, .05, 'BOUNDARY'), (.05, .95, 'OTHER')])
        at_zero = weighted_trimmed_ey([(0., .05, 'BOUNDARY'), (.05, .95, 'OTHER')])
        after = weighted_trimmed_ey([(eps, .05, 'BOUNDARY'), (.05, .95, 'OTHER')])
        self.assertAlmostEqual(before, .05)
        self.assertAlmostEqual(at_zero, .05)
        self.assertAlmostEqual(after, .0475 + .05 * eps)
        self.assertGreater(before - after, .00249)

    def test_weighted_median_switch_can_jump_windfall_threshold(self):
        eps = 1e-6
        before = weighted_trimmed_ey([(.05, .5 + eps, 'A'), (.1, .45 - eps, 'B'), (1., .05, 'C')])
        after = weighted_trimmed_ey([(.05, .5 - eps, 'A'), (.1, .45 + eps, 'B'), (1., .05, 'C')])
        self.assertAlmostEqual(before, .09749995)
        self.assertAlmostEqual(after, .11000005)
        self.assertGreater(after - before, .0125)

    def test_caller_must_sort_function_does_not_enforce_order(self):
        data = [(-.5, .04, 'WORST'), (-.1, .04, 'OTHER_LOSS'), (.05, .92, 'POSITIVE')]
        sorted_result = weighted_trimmed_ey(data)
        unsorted_result = weighted_trimmed_ey([data[1], data[0], data[2]])
        self.assertAlmostEqual(sorted_result, .043 / .95)
        self.assertAlmostEqual(unsorted_result, .031 / .95)
        self.assertNotAlmostEqual(sorted_result, unsorted_result)


if __name__ == '__main__':
    unittest.main()
