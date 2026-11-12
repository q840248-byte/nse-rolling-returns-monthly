"""Offline regression tests. No financial providers are contacted."""
import json
import math
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch, Mock
from datetime import date

import pandas as pd
import update_commodities as commodities
import update_data as indices
import build_top_stocks as stocks

ROOT = Path(__file__).resolve().parents[1]


class CommodityTests(unittest.TestCase):
    def test_conversion_preserves_alignment(self):
        raw = pd.DataFrame({"Gold_USD": [2000., 2100.], "Silver_USD": [25., 26.],
                            "USD_INR": [83., 84.]}, index=pd.to_datetime(["2024-01-30", "2024-01-31"]))
        result = commodities.calculate_pure_inr_prices(raw)
        self.assertEqual(result.index.tolist(), ["2024-01-30", "2024-01-31"])
        self.assertFalse(result.isna().any().any())
        self.assertAlmostEqual(result.iloc[-1, 0], round(2100 * 84 / 31.1034768 * 10, 2))

    def test_patch_updates_real_raw_blocks_in_weight_units(self):
        source = 'const RAW = {};\nRAW["Gold (INR)"] = {"2023-12":60000};\nRAW["Silver (INR)"] = {"2023-12":70000};\nRAW["Nifty 50"] = {"2024-01":22000};\n'
        daily = pd.DataFrame({"gold_inr_per_10g": [62000., 61000.], "silver_inr_per_1kg": [72000., 71000.]},
                             index=pd.Index(["2024-01-31", "2024-01-30"], name="Date"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.html"
            path.write_text(source)
            with patch.object(commodities, "HTML_PATH", path):
                commodities.update_html_app(daily)
                first = path.read_text()
                commodities.update_html_app(daily)
                self.assertEqual(first, path.read_text())
            data = {name: json.loads(raw) for name, raw in re.findall(r'RAW\["([^"]+)"\]\s*=\s*(\{[^;]+\});', first)}
            self.assertEqual(data['Gold (INR)'], {'2023-12': 60000, '2024-01': 62000})
            self.assertEqual(data['Silver (INR)']['2024-01'], 72000)
            self.assertIn('RAW["Nifty 50"] = {"2024-01":22000};', first)
            self.assertIn('const RAW = {};', first)


class IndexTests(unittest.TestCase):
    def test_month_end_and_nonfinite_prices(self):
        rows = [{'HistoricalDate': dt, 'CLOSE': value} for dt, value in [
            ('31-Jan-2024', '1,100'), ('01-Jan-2024', '1000'), ('29-Feb-2024', 'NaN'),
            ('01-Mar-2024', 'Infinity'), ('01-Apr-2024', '-2')]]
        self.assertEqual(indices.rows_to_month_ohlc(rows), {'2024-01': 1100})

    def test_full_pe_response_does_not_erase_unreturned_history(self):
        html = 'const RAW_PE = {"Nifty 50":{"2020-01":20,"2024-01":25}};\n'
        response = Mock()
        response.json.return_value = [{'DATE': '31-Jan-2024', 'pe': '26'}, {'DATE': '29-Feb-2024', 'pe': 'NaN'}]
        with patch.object(indices, 'FULL_MODE', True), patch.object(indices.requests, 'post', return_value=response):
            result = indices.update_pe_data(html, date(2024, 2, 29))
        pe = json.loads(re.search(r'const RAW_PE = (.*);', result)[1])
        self.assertEqual(pe['Nifty 50'], {'2020-01': 20, '2024-01': 26})

    def test_anomaly_repair_is_saved_without_recent_changes(self):
        source = 'const RAW = {};\nRAW["Nifty 50"] = {"2020-01":100,"2020-02":1000,"2020-03":110,"2024-01":120};\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'app.html'
            path.write_text(source)
            responses = [
                [{'HistoricalDate': '28-Feb-2020', 'CLOSE': 105}],
                [{'HistoricalDate': '31-Jan-2024', 'CLOSE': 120}],
            ]
            with patch.object(indices, 'HTML_FILE', str(path)), patch.object(indices, 'FULL_MODE', False), \
                 patch.object(indices, 'fetch_data', side_effect=responses), \
                 patch.object(indices, 'update_pe_data', side_effect=lambda html, today: html), \
                 patch.object(indices.time, 'sleep'):
                indices.main()
            data = json.loads(re.search(r'RAW\["Nifty 50"\] = (.*);', path.read_text())[1])
            self.assertEqual(data['2020-02'], 105)
            self.assertEqual(data['2020-03'], 110, 'Partial repairs must not delete history')


class StockTests(unittest.TestCase):
    def test_consolidated_only_single_eps_is_not_discarded(self):
        raw = {'datasets': [{'metric': 'EPS', 'values': [['2024-01-01', 10]]}]}
        merged, basis = stocks.choose_and_merge_charts(raw, None)
        self.assertEqual(basis, 'consolidated')
        self.assertEqual(merged['datasets'][0]['values'], [('2024-01-01', 10.0)])

    def test_invalid_eps_points_are_skipped(self):
        points = [['2024-01-01', 10], ['2024-02-01', 'bad'], ['2024-03-01', 'NaN'],
                  ['2024-04-01', 'Infinity'], ['not-a-date', 5], None]
        self.assertEqual(stocks.sanitize_eps_points(points), [('2024-01-01', 10.0)])

    def test_embedded_stock_cache_matches_generated_files(self):
        html = (ROOT / 'rolling_returns.html').read_text()
        embedded = json.loads(re.search(r'const TOP_STOCKS_DATA = (\{.*?\});', html)[1])
        cache = json.loads((ROOT / 'top_stocks_cache.json').read_text())
        js = json.loads(re.search(r'const TOP_STOCKS_DATA = (\{.*?\});', (ROOT / 'top_stocks_data.js').read_text())[1])
        self.assertEqual(cache, embedded)
        self.assertEqual(cache, js)

class CacheBuildTests(unittest.TestCase):
    def test_partial_build_preserves_failed_stocks_and_updates_embedded_cache(self):
        stock = {'symbol': 'GOOD', 'name': 'Good Ltd', 'id': 1}
        failed = {'symbol': 'FAILED', 'name': 'Failed Ltd', 'id': 2}
        with tempfile.TemporaryDirectory() as tmp:
            import os
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                Path('top_stocks_cache.json').write_text(json.dumps({'FAILED': {'symbol': 'FAILED', 'old': True}}))
                Path('rolling_returns.html').write_text('const TOP_STOCKS_DATA = {};\n// rest of app')
                Path('raw_screener_cache.json').write_text(json.dumps({'GOOD': {'cons': {'datasets': []}, 'sa': None}}))
                processed = {**stock, 'dates': ['2024-01'], 'eps': {'2024-01': 10}}
                with patch.object(stocks, 'STOCKS_CATALOG', [stock, failed]), \
                     patch.object(stocks, 'fetch_stock_chart', side_effect=RuntimeError('offline fixture')), \
                     patch.object(stocks, 'process_chart_data', return_value=processed):
                    stocks.main()
                data = json.loads(Path('top_stocks_cache.json').read_text())
                self.assertTrue(data['FAILED']['old'])
                self.assertEqual(data['GOOD'], processed)
                embedded = json.loads(re.search(r'const TOP_STOCKS_DATA = (.*);', Path('rolling_returns.html').read_text())[1])
                self.assertEqual(embedded, data)
            finally:
                os.chdir(old_cwd)

    def test_total_failure_preserves_output_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                original = '{"OLD":{"symbol":"OLD"}}'
                Path('top_stocks_cache.json').write_text(original)
                Path('top_stocks_data.js').write_text('// keep me')
                with patch.object(stocks, 'STOCKS_CATALOG', [{'symbol': 'FAILED', 'id': 2}]), \
                     patch.object(stocks, 'fetch_stock_chart', side_effect=RuntimeError('offline fixture')):
                    with self.assertRaisesRegex(RuntimeError, 'No stocks refreshed'):
                        stocks.main()
                self.assertEqual(Path('top_stocks_cache.json').read_text(), original)
                self.assertEqual(Path('top_stocks_data.js').read_text(), '// keep me')
            finally:
                os.chdir(old_cwd)


class EmbeddedDataTests(unittest.TestCase):
    def test_raw_series_have_valid_positive_values_and_updater_coverage(self):
        html = (ROOT / 'rolling_returns.html').read_text()
        blocks = re.findall(r'RAW\["([^"]+)"\]\s*=\s*(\{[^;]+\})\s*;', html)
        self.assertGreater(len(blocks), 50)
        self.assertEqual(len(blocks), len({key for key, _ in blocks}))
        for name, raw in blocks:
            self.assertTrue(name in indices.INDEX_CONFIG or name in ('Gold (INR)', 'Silver (INR)'), name)
            values = json.loads(raw)
            self.assertTrue(values, name)
            for month, value in values.items():
                self.assertRegex(month, r'^\d{4}-(0[1-9]|1[0-2])$')
                self.assertTrue(isinstance(value, (int, float)) and math.isfinite(value) and value > 0, (name, month, value))


if __name__ == '__main__':
    unittest.main()
