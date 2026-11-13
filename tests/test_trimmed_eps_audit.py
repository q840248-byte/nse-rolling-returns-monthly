"""Diagnostics regression tests; not certification of constituent methodology."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_trimmed_eps import audit, inspect_series, unique_object


class TrimmedEpsAuditTests(unittest.TestCase):
    def test_invalid_values_and_calendar_keys(self):
        result = inspect_series('Fixture', {
            '2020-13': 1, '2020-01': True, '2020-02': float('inf'),
            '2020-03': None, '2020-04': -5,
        }, {}, {})
        self.assertEqual(result['invalid_dates'], ['2020-13'])
        self.assertEqual(result['invalid_values'], ['2020-01', '2020-02', '2020-03'])
        self.assertEqual(result['nonpositive'], 1)

    def test_gaps_are_not_monthly_jumps(self):
        result = inspect_series('Fixture', {'2020-01': 10, '2020-03': 100}, {}, {})
        self.assertEqual(result['gaps'], [('2020-01', '2020-03')])
        self.assertEqual(result['jumps'], [])

    def test_zero_negative_absent_pe_are_unavailable_comparators(self):
        values = {f'2022-0{i}': 10 for i in range(1, 5)}
        result = inspect_series('Fixture', values, {d: 100 for d in values},
                                {'2022-01': 0, '2022-02': -5, '2022-03': None})
        self.assertEqual(len(result['missing_pe']), 4)
        self.assertEqual(result['missing_price'], [])
        self.assertEqual(result['ratios'], [])

    def test_harmonization_cutoff_and_signed_changes(self):
        values = {'2021-02': 10, '2021-03': 20, '2021-04': 5}
        result = inspect_series('Fixture', values, {d: 100 for d in values},
                                {d: 10 for d in values}, factor=.8)
        self.assertEqual([r[0] for r in result['ratios']], [.8, 2, .5])
        self.assertEqual([r[-1] for r in result['jumps']], [1, -.75])

    def test_duplicate_keys_are_not_silently_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            json.loads('{"2020-01": 5, "2020-01": 10}', object_pairs_hook=unique_object)

    def test_current_table_structure_and_price_coverage(self):
        html = (Path(__file__).resolve().parents[1] / 'rolling_returns.html').read_text()
        rows, prices, _, trimmed, _ = audit(html)
        self.assertTrue(rows)
        self.assertEqual(set(trimmed), set(prices) - {'Gold (INR)', 'Silver (INR)'})
        for row in rows:
            with self.subTest(index=row['name']):
                self.assertEqual(row['invalid_dates'], [])
                self.assertEqual(row['invalid_values'], [])
                self.assertEqual(row['missing_price'], [])
                self.assertEqual(row['gaps'], [])
        # No positivity or smoothness requirement: genuine loss-making baskets
        # and reconstitutions must not fail an audit just because they exist.


if __name__ == '__main__':
    unittest.main()
