import http.server
import socketserver
import threading
import urllib.request
import json
import asyncio
import websockets
import subprocess
import time
import os
import sys

PORT = 8895

class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_server():
    try:
        server = socketserver.TCPServer(("", PORT), SilentHandler)
        server.serve_forever()
    except Exception as e:
        pass

t = threading.Thread(target=start_server, daemon=True)
t.start()

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
URL = f"http://127.0.0.1:{PORT}/rolling_returns.html"

async def run_tests():
    print("Launching headless Edge on port 9245...")
    p = subprocess.Popen([
        EDGE_PATH, 
        "--headless=new", 
        "--remote-debugging-port=9245", 
        "--disable-gpu",
        URL
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        await asyncio.sleep(2.0)
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9245/json").read().decode())
        page_tab = next((tab for tab in tabs if tab.get("type") == "page"), None)
        assert page_tab is not None, "Edge CDP page tab not found"
        ws_url = page_tab["webSocketDebuggerUrl"]
        
        console_errors = []
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            await ws.recv()
            await ws.send(json.dumps({"id": 2, "method": "Log.enable"}))
            await ws.recv()

            msg_id = 10
            async def eval_js(expr):
                nonlocal msg_id
                msg_id += 1
                req = {"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}
                await ws.send(json.dumps(req))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("method") == "Runtime.exceptionThrown":
                        console_errors.append(m["params"])
                    if m.get("method") == "Log.entryAdded":
                        entry = m.get("params", {}).get("entry", {})
                        if entry.get("level") == "error" and entry.get("source") != "network":
                            console_errors.append(entry)
                    if m.get("id") == msg_id:
                        if "exceptionDetails" in m.get("result", {}):
                            console_errors.append(m["result"]["exceptionDetails"])
                        return m.get("result", {}).get("result", {}).get("value")

            # Wait for page & scripts to be fully parsed and ready
            print("Waiting for page and main script to be ready...")
            for attempt in range(40):
                ready = await eval_js("document.readyState === 'complete' && typeof switchTab === 'function'")
                if ready:
                    print(f"✓ Application ready after {(attempt + 1) * 0.3:.1f}s")
                    break
                await asyncio.sleep(0.3)
            else:
                raise RuntimeError("Timeout waiting for application to initialize")

            print("\n=======================================================")
            print("TEST 1: TAB 9 INITIALIZATION (DEFAULT INDICES MODE)")
            print("=======================================================")
            await eval_js("switchTab(9)")
            await asyncio.sleep(0.5)

            is_visible = await eval_js("document.getElementById('tabContent9').style.display !== 'none'")
            print("✓ Tab 9 is visible:", is_visible)
            assert is_visible, "Tab 9 failed to open"

            fund_mode = await eval_js("fundAssetMode")
            print("✓ Default asset mode:", fund_mode)
            assert fund_mode == 'index', f"Expected 'index', got {fund_mode}"

            idx_container_disp = await eval_js("document.getElementById('fundIndexSelectContainer').style.display")
            stk_container_disp = await eval_js("document.getElementById('fundStockControlsContainer').style.display")
            chips_row_disp = await eval_js("document.getElementById('fundStockChipsRow').style.display")
            print(f"✓ Indices container: '{idx_container_disp}', Stocks container: '{stk_container_disp}', Chips row: '{chips_row_disp}'")
            assert idx_container_disp != 'none', "Index container should be displayed"
            assert stk_container_disp == 'none', "Stock container should be hidden"
            assert chips_row_disp == 'none', "Chips row should be hidden"

            idx_count = await eval_js("document.getElementById('fundIndexSelect').options.length")
            print("✓ Indices dropdown options count:", idx_count)
            assert idx_count >= 50, f"Expected >= 50 indices, got {idx_count}"

            print("\n=======================================================")
            print("TEST 2: ASSET MODE SWITCHER -> STOCKS MODE ⚡")
            print("=======================================================")
            await eval_js("switchFundAssetMode('stock')")
            await asyncio.sleep(0.3)

            fund_mode = await eval_js("fundAssetMode")
            print("✓ Active fundAssetMode:", fund_mode)
            assert fund_mode == 'stock', f"Expected 'stock', got {fund_mode}"

            idx_container_disp = await eval_js("document.getElementById('fundIndexSelectContainer').style.display")
            stk_container_disp = await eval_js("document.getElementById('fundStockControlsContainer').style.display")
            chips_row_disp = await eval_js("document.getElementById('fundStockChipsRow').style.display")
            print(f"✓ Indices container: '{idx_container_disp}', Stocks container: '{stk_container_disp}', Chips row: '{chips_row_disp}'")
            assert idx_container_disp == 'none', "Index container should now be hidden"
            assert stk_container_disp == 'flex', "Stock container should now be flex"
            assert chips_row_disp == 'flex', "Chips row should now be flex"

            chips_count = await eval_js("document.querySelectorAll('.stock-chip').length")
            print("✓ Quick Stock Chips count:", chips_count)
            assert chips_count >= 10, f"Expected >= 10 quick stock chips, got {chips_count}"

            chips_text = await eval_js("Array.from(document.querySelectorAll('.stock-chip')).map(c => c.innerText)")
            print("✓ Quick Stock Chips:", chips_text)
            for req_chip in ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'ITC', 'LT', 'BHARTIARTL', 'TATA MOTORS', 'STATE BANK']:
                assert req_chip in chips_text, f"Missing required chip: {req_chip}"

            print("\n=======================================================")
            print("TEST 3: STOCK FUNDAMENTALS RENDERING (RELIANCE)")
            print("=======================================================")
            sel_stock = await eval_js("fundSelectedStock")
            print("✓ Currently selected stock:", sel_stock)
            assert sel_stock == 'RELIANCE', f"Expected 'RELIANCE', got {sel_stock}"

            has_chart = await eval_js("!!window.fundamentalsChartInstance")
            assert has_chart, "Chart instance not found"

            ds_labels = await eval_js("window.fundamentalsChartInstance.data.datasets.map(d => d.label)")
            print("✓ Chart datasets:", ds_labels)
            assert len(ds_labels) == 4, f"Expected 4 datasets, got {len(ds_labels)}"

            labels_len = await eval_js("window.fundamentalsChartInstance.data.labels.length")
            print("✓ Chart date points count:", labels_len)
            assert labels_len > 150, f"Expected > 150 months of history for RELIANCE, got {labels_len}"

            first_date = await eval_js("window.fundamentalsChartInstance.data.labels[0]")
            last_date = await eval_js("window.fundamentalsChartInstance.data.labels[window.fundamentalsChartInstance.data.labels.length - 1]")
            print(f"✓ History range: {first_date} to {last_date}")

            price_reb_first = await eval_js("window.fundamentalsChartInstance.data.datasets[0].data[0]")
            price_reb_last = await eval_js("window.fundamentalsChartInstance.data.datasets[0].data[window.fundamentalsChartInstance.data.datasets[0].data.length - 1]")
            print(f"✓ Price Rebased: Start = {price_reb_first}, Latest = {price_reb_last}")
            assert price_reb_first == 100.0, f"Rebased price start must be 100, got {price_reb_first}"
            assert price_reb_last > 400.0, f"Expected rebased price > 400, got {price_reb_last}"

            eps_reb_first = await eval_js("window.fundamentalsChartInstance.data.datasets[1].data[0]")
            eps_reb_last = await eval_js("window.fundamentalsChartInstance.data.datasets[1].data[window.fundamentalsChartInstance.data.datasets[1].data.length - 1]")
            print(f"✓ Intrinsic Value Rebased: Start = {eps_reb_first}, Latest = {eps_reb_last}")
            assert eps_reb_first > 50.0, f"Expected Intrinsic Value start > 50, got {eps_reb_first}"
            assert eps_reb_last > 250.0, f"Expected Intrinsic Value latest > 250, got {eps_reb_last}"

            pe_latest = await eval_js("window.fundamentalsChartInstance.data.datasets[2].data[window.fundamentalsChartInstance.data.datasets[2].data.length - 1]")
            print(f"✓ Latest P/E Ratio: {pe_latest}x")
            assert 15 < pe_latest < 40, f"Expected P/E between 15x and 40x, got {pe_latest}"

            cagr_latest = await eval_js("window.fundamentalsChartInstance.data.datasets[3].data[window.fundamentalsChartInstance.data.datasets[3].data.length - 1]")
            print(f"✓ Latest 5Y Rolling CAGR: {cagr_latest}%")
            assert cagr_latest is not None, "Rolling CAGR should not be null"

            # Check dynamic Y-scale bounds on RELIANCE (anchored at 80, no dead space 1-80)
            rel_y_min = await eval_js("window.fundamentalsChartInstance.scales.y.min")
            rel_y_max = await eval_js("window.fundamentalsChartInstance.scales.y.max")
            print(f"✓ RELIANCE dynamic Y-axis bounds: min={rel_y_min}, max={rel_y_max}")
            assert rel_y_min == 80, f"Expected RELIANCE scale min=80, got {rel_y_min}"
            assert rel_y_max >= 1000, f"Expected RELIANCE scale max >= 1000, got {rel_y_max}"

            # Diagnostic HUD
            hud_text = await eval_js("document.getElementById('fundHoverHud').innerText")
            print("✓ Diagnostic HUD:", hud_text)
            assert "[RELIANCE]" in hud_text, "HUD missing [RELIANCE] asset tag"
            assert "Price:" in hud_text and ("Intrinsic:" in hud_text or "Real EPS:" in hud_text) and "P/E:" in hud_text, "HUD missing metrics"
            assert "Fair Value" in hud_text or "Overvalued" in hud_text or "Undervalued" in hud_text or "Valuation" in hud_text or "Froth" in hud_text or "Aligned" in hud_text or "Bargain" in hud_text, "HUD missing valuation gap tag"

            # 3-Engine Return Decomposition Table
            table_rows = await eval_js("document.querySelectorAll('#fundDecompTbody tr').length")
            print("✓ Decomposition table rows count:", table_rows)
            assert table_rows == 3, f"Expected 3 rows (3Y, 5Y, 10Y), got {table_rows}"

            first_row_text = await eval_js("document.querySelectorAll('#fundDecompTbody tr')[0].innerText")
            second_row_text = await eval_js("document.querySelectorAll('#fundDecompTbody tr')[1].innerText")
            third_row_text = await eval_js("document.querySelectorAll('#fundDecompTbody tr')[2].innerText")
            print("✓ 3Y Horizon:", first_row_text)
            print("✓ 5Y Horizon:", second_row_text)
            print("✓ 10Y Horizon:", third_row_text)
            assert "3-Year Horizon" in first_row_text, "3Y horizon missing"
            assert "5-Year Horizon" in second_row_text, "5Y horizon missing"
            assert "10-Year Horizon" in third_row_text, "10Y horizon missing"
            assert "%/yr" in first_row_text and "%/yr" in second_row_text, "CAGR percentages missing in table"

            print("\n=======================================================")
            print("TEST 4: QUICK CHIP SWITCHING -> TCS, TATAMOTORS, SBIN")
            print("=======================================================")
            # Switch to TCS
            await eval_js("selectStockChip('TCS')")
            await asyncio.sleep(0.3)
            hud_text_tcs = await eval_js("document.getElementById('fundHoverHud').innerText")
            print("✓ TCS HUD:", hud_text_tcs)
            assert "[TCS]" in hud_text_tcs, "HUD failed to update to [TCS]"
            tcs_pe = await eval_js("window.fundamentalsChartInstance.data.datasets[2].data[window.fundamentalsChartInstance.data.datasets[2].data.length - 1]")
            print(f"✓ TCS Latest P/E: {tcs_pe}x")
            assert 10 < tcs_pe < 45, f"TCS P/E out of expected range: {tcs_pe}"

            # Switch to TATA MOTORS
            await eval_js("selectStockChip('TATAMOTORS', 'TATA MOTORS')")
            await asyncio.sleep(0.3)
            hud_text_tm = await eval_js("document.getElementById('fundHoverHud').innerText")
            print("✓ TATA MOTORS HUD:", hud_text_tm)
            assert "[TATAMOTORS]" in hud_text_tm, "HUD failed to update to [TATAMOTORS]"
            tm_y_min = await eval_js("window.fundamentalsChartInstance.scales.y.min")
            print(f"✓ TATA MOTORS dynamic Y-scale min: {tm_y_min}")
            assert 2 <= tm_y_min <= 5, f"Expected TATAMOTORS min between 2 and 5, got {tm_y_min}"

            # Switch to HDFCBANK
            await eval_js("selectStockChip('HDFCBANK')")
            await asyncio.sleep(0.3)
            hdfc_y_min = await eval_js("window.fundamentalsChartInstance.scales.y.min")
            print(f"✓ HDFCBANK dynamic Y-scale min: {hdfc_y_min}")
            assert hdfc_y_min == 80, f"Expected HDFCBANK min=80, got {hdfc_y_min}"

            # Switch to STATE BANK
            await eval_js("selectStockChip('SBIN', 'STATE BANK')")
            await asyncio.sleep(0.3)
            hud_text_sbin = await eval_js("document.getElementById('fundHoverHud').innerText")
            print("✓ STATE BANK HUD:", hud_text_sbin)
            assert "[SBIN]" in hud_text_sbin, "HUD failed to update to [SBIN]"

            print("\n=======================================================")
            print("TEST 5: TIMEFRAME & ROLLING HORIZON TOGGLES ON STOCKS")
            print("=======================================================")
            # Test 3Y Rolling Horizon
            await eval_js("setFundHorizon(3)")
            await asyncio.sleep(0.2)
            lbl_text = await eval_js("document.getElementById('chkFundRollingLabel').innerText")
            print("✓ Rolling Horizon Label:", lbl_text)
            assert "3Y Rolling CAGR %" in lbl_text, "Label failed to update to 3Y"

            # Test 5Y Timeframe Zoom
            await eval_js("setFundTimeframe('5Y')")
            await asyncio.sleep(0.2)
            pts_5y = await eval_js("window.fundamentalsChartInstance.data.labels.length")
            print("✓ 5Y Timeframe points count:", pts_5y)
            assert 55 <= pts_5y <= 65, f"Expected ~60 months for 5Y timeframe, got {pts_5y}"

            # Reset Zoom
            await eval_js("resetFundZoom()")
            await asyncio.sleep(0.2)
            pts_max = await eval_js("window.fundamentalsChartInstance.data.labels.length")
            print("✓ MAX Timeframe points count after reset:", pts_max)
            assert pts_max > 100, f"Expected > 100 months for MAX, got {pts_max}"

            print("\n=======================================================")
            print("TEST 6: CLOUDFLARE WORKER PROXY SETTINGS MODAL")
            print("=======================================================")
            await eval_js("toggleProxySettingsModal(true)")
            await asyncio.sleep(0.2)
            modal_disp = await eval_js("document.getElementById('fundProxyModal').style.display")
            print("✓ Modal display when opened:", modal_disp)
            assert modal_disp == 'flex', "Modal failed to display flex"

            proxy_val = await eval_js("document.getElementById('fundProxyUrlInput').value")
            print("✓ Default proxy URL:", proxy_val)
            assert "workers.dev" in proxy_val or "http" in proxy_val, "Proxy input empty"

            # Save custom URL
            custom_url = "https://custom-worker.sample.workers.dev"
            await eval_js(f"document.getElementById('fundProxyUrlInput').value = '{custom_url}'; saveProxySettings();")
            await asyncio.sleep(0.2)
            saved_url = await eval_js("localStorage.getItem('fund_stock_proxy_url')")
            print("✓ Saved proxy URL in localStorage:", saved_url)
            assert saved_url == custom_url, f"Expected {custom_url}, got {saved_url}"

            # Reset default
            await eval_js("resetDefaultProxyUrl(); saveProxySettings();")
            await asyncio.sleep(0.2)
            reset_url = await eval_js("localStorage.getItem('fund_stock_proxy_url')")
            print("✓ Reset default proxy URL:", reset_url)
            assert "workers.dev" in reset_url, "Default proxy URL reset failed"

            print("\n=======================================================")
            print("TEST 7: SWITCH BACK TO INDICES MODE SEAMLESSLY")
            print("=======================================================")
            await eval_js("switchFundAssetMode('index')")
            await asyncio.sleep(0.3)
            fund_mode = await eval_js("fundAssetMode")
            print("✓ Switched back asset mode:", fund_mode)
            assert fund_mode == 'index', f"Expected 'index', got {fund_mode}"

            idx_container_disp = await eval_js("document.getElementById('fundIndexSelectContainer').style.display")
            stk_container_disp = await eval_js("document.getElementById('fundStockControlsContainer').style.display")
            print(f"✓ Indices container: '{idx_container_disp}', Stocks container: '{stk_container_disp}'")
            assert idx_container_disp == 'flex', "Index container should be visible again"
            assert stk_container_disp == 'none', "Stock container should be hidden"

            hud_idx = await eval_js("document.getElementById('fundHoverHud').innerText")
            print("✓ Indices HUD:", hud_idx)
            assert "[RELIANCE]" not in hud_idx, "HUD should no longer have stock tag"
            assert "Price:" in hud_idx and ("Intrinsic:" in hud_idx or "Real EPS:" in hud_idx), "Indices HUD rendered correctly"

            nifty_y_min = await eval_js("window.fundamentalsChartInstance.scales.y.min")
            print(f"✓ Indices Nifty 50 dynamic Y-scale min: {nifty_y_min}")
            assert nifty_y_min == 50, f"Expected Nifty 50 min=50, got {nifty_y_min}"

            print("\n=======================================================")
            print("TEST 8: CONSOLE ERRORS AUDIT")
            print("=======================================================")
            print(f"Total console errors logged: {len(console_errors)}")
            if console_errors:
                for err in console_errors:
                    print("  ❌ Console Error:", err)
            assert len(console_errors) == 0, f"Found {len(console_errors)} console errors!"
            print("✓ 0 console errors logged across all interactions!")

            print("\n=======================================================")
            print("🎉 ALL CDP TESTS PASSED FLAWLESSLY!")
            print("=======================================================")

    finally:
        p.terminate()
        try:
            p.wait(timeout=3)
        except:
            p.kill()

if __name__ == "__main__":
    asyncio.run(run_tests())
