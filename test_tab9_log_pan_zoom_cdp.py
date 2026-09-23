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

PORT = 8899

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
    print("Launching headless Edge on port 9248...")
    p = subprocess.Popen([
        EDGE_PATH, 
        "--headless=new", 
        "--remote-debugging-port=9248", 
        "--disable-gpu",
        "--window-size=1400,900",
        URL
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        await asyncio.sleep(2.0)
        tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9248/json").read().decode())
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

            # Wait for page readiness
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
            print("TEST 1: TAB 9 INITIALIZATION & DEFAULT LOG SCALE")
            print("=======================================================")
            await eval_js("switchTab(9)")
            await asyncio.sleep(0.5)

            is_visible = await eval_js("document.getElementById('tabContent9').style.display !== 'none'")
            assert is_visible, "Tab 9 failed to open"
            print("✓ Tab 9 is visible")

            # Check default scale
            def_scale = await eval_js("fundScaleType")
            print(f"✓ Default fundScaleType: '{def_scale}'")
            assert def_scale == "logarithmic", f"Expected 'logarithmic', got '{def_scale}'"

            # Check scale buttons in DOM
            log_active = await eval_js("document.getElementById('fundScaleLogBtn').classList.contains('active')")
            lin_active = await eval_js("document.getElementById('fundScaleLinBtn').classList.contains('active')")
            print(f"✓ Button states: Log active={log_active}, Lin active={lin_active}")
            assert log_active and not lin_active, "Log button should be active by default"

            # Check chart instance
            has_chart = await eval_js("typeof window.fundChart !== 'undefined' && window.fundChart !== null")
            assert has_chart, "fundChart instance not found on window"
            print("✓ Chart instance and window.fundChart verified")

            # Verify Y scale type on chart
            y_scale = await eval_js("window.fundChart.options.scales.y.type")
            print(f"✓ Primary Y-axis scale type: '{y_scale}'")
            assert y_scale == "logarithmic", f"Expected 'logarithmic', got '{y_scale}'"

            # Verify Dynamic Logarithmic Anchoring on Nifty 50 (dead space below 50 eliminated)
            nifty_y_min = await eval_js("window.fundChart.scales.y.min")
            nifty_y_max = await eval_js("window.fundChart.scales.y.max")
            nifty_sug_min = await eval_js("window.fundChart.options.scales.y.suggestedMin")
            print(f"✓ Nifty 50 dynamic Y-axis bounds: min={nifty_y_min}, max={nifty_y_max}, suggestedMin={nifty_sug_min}")
            assert nifty_y_min == 50, f"Expected Nifty 50 scale min=50, got {nifty_y_min}"
            assert nifty_y_min > 1, f"Nifty 50 scale must not anchor at hardcoded 1 (got {nifty_y_min})"

            # Verify Tooltip is strictly disabled
            tooltip_enabled = await eval_js("window.fundChart.options.plugins.tooltip.enabled")
            print(f"✓ Tooltip enabled: {tooltip_enabled}")
            assert tooltip_enabled is False, f"Expected tooltip.enabled to be False, got {tooltip_enabled}"

            # Verify TradingView cursor style
            canvas_cursor = await eval_js("document.getElementById('fundamentalsChart').style.cursor")
            print(f"✓ Canvas cursor style: '{canvas_cursor}'")
            assert canvas_cursor == "grab", f"Expected 'grab', got '{canvas_cursor}'"

            print("\n=======================================================")
            print("TEST 2: SCALE TOGGLING (LOG <-> LIN)")
            print("=======================================================")
            # Switch to linear
            await eval_js("setFundScaleType('linear')")
            await asyncio.sleep(0.2)
            cur_scale = await eval_js("fundScaleType")
            y_scale = await eval_js("window.fundChart.options.scales.y.type")
            lin_sug_min = await eval_js("window.fundChart.options.scales.y.suggestedMin")
            log_active = await eval_js("document.getElementById('fundScaleLogBtn').classList.contains('active')")
            lin_active = await eval_js("document.getElementById('fundScaleLinBtn').classList.contains('active')")
            assert cur_scale == "linear" and y_scale == "linear", "Failed to switch to linear scale"
            assert lin_active and not log_active, "Lin button should be active"
            assert lin_sug_min is None, f"Expected undefined suggestedMin in linear mode, got {lin_sug_min}"
            print(f"✓ Linear mode: fundScaleType={cur_scale}, y.type={y_scale}, Log active={log_active}, Lin active={lin_active}, suggestedMin={lin_sug_min}")

            # Switch back to log
            await eval_js("setFundScaleType('logarithmic')")
            await asyncio.sleep(0.2)
            cur_scale = await eval_js("fundScaleType")
            y_scale = await eval_js("window.fundChart.options.scales.y.type")
            log_sug_min = await eval_js("window.fundChart.options.scales.y.suggestedMin")
            log_active = await eval_js("document.getElementById('fundScaleLogBtn').classList.contains('active')")
            lin_active = await eval_js("document.getElementById('fundScaleLinBtn').classList.contains('active')")
            assert cur_scale == "logarithmic" and y_scale == "logarithmic", "Failed to switch back to log scale"
            assert log_active and not lin_active, "Log button should be active"
            assert log_sug_min is not None and log_sug_min > 1, f"Expected dynamic suggestedMin > 1, got {log_sug_min}"
            print(f"✓ Log mode: fundScaleType={cur_scale}, y.type={y_scale}, Log active={log_active}, Lin active={lin_active}, suggestedMin={log_sug_min}")

            # Test toggleFundScale()
            await eval_js("toggleFundScale()")
            assert await eval_js("fundScaleType") == "linear", "toggleFundScale to linear failed"
            await eval_js("toggleFundScale()")
            assert await eval_js("fundScaleType") == "logarithmic", "toggleFundScale back to log failed"
            print("✓ toggleFundScale() works smoothly back and forth")

            print("\n=======================================================")
            print("TEST 2B: FLOATING TOOLTIP DISABLED & FIXED HUD ACTIVE")
            print("=======================================================")
            t_enabled = await eval_js("window.fundChart.options.plugins.tooltip.enabled")
            assert t_enabled is False, f"Expected tooltip.enabled to be False, got {t_enabled}"
            print("✓ window.fundChart.options.plugins.tooltip.enabled is False")

            # Dispatch mousemove over canvas
            await eval_js("document.getElementById('fundamentalsChart').scrollIntoView({block: 'center'})")
            await asyncio.sleep(0.1)
            c_pos = await eval_js("""
                (function() {
                    var r = document.getElementById('fundamentalsChart').getBoundingClientRect();
                    return { x: r.left + r.width * 0.4, y: r.top + r.height * 0.5 };
                })()
            """)
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": "Input.dispatchMouseEvent", "params": {"type": "mouseMoved", "x": c_pos['x'], "y": c_pos['y']}}))
            await asyncio.sleep(0.15)

            # Verify Chart.js internal tooltip has enabled: false (not drawn to canvas)
            t_chart_enabled = await eval_js("(window.fundChart.tooltip && window.fundChart.tooltip.options ? window.fundChart.tooltip.options.enabled : false)")
            print(f"✓ Chart.js internal tooltip options.enabled: {t_chart_enabled}")
            assert t_chart_enabled is False, f"Expected tooltip options.enabled to be False, got {t_chart_enabled}"

            # Verify HUD is populated and active
            hud_text = await eval_js("document.getElementById('fundHoverHud').innerText")
            print(f"✓ Fixed diagnostic HUD text: {hud_text}")
            assert len(hud_text) > 15, "HUD should have updated with date and fundamental metrics"
            assert "Price:" in hud_text and "Intrinsic:" in hud_text, "HUD missing fundamental metrics"

            print("\n=======================================================")
            print("TEST 3: NEGATIVE EPS STOCKS ON LOG SCALE (TATA MOTORS & OTHERS)")
            print("=======================================================")
            await eval_js("switchFundAssetMode('stock')")
            await asyncio.sleep(0.3)

            test_stocks = ["TATAMOTORS", "BHARTIARTL", "SBIN", "TATASTEEL", "JSWSTEEL", "ADANIENT", "RELIANCE", "TCS"]
            for sym in test_stocks:
                await eval_js(f"selectStockChip('{sym}')")
                await asyncio.sleep(0.2)
                
                # Check log mode
                log_y_type = await eval_js("window.fundChart.options.scales.y.type")
                assert log_y_type == "logarithmic", f"{sym}: Expected log scale"
                
                # Check that dataset 0 and 1 have spanGaps: true and no values <= 0
                has_non_pos_eps = await eval_js("""
                    window.fundChart.data.datasets[1].data.some(v => v !== null && v <= 0)
                """)
                assert not has_non_pos_eps, f"{sym}: dataset 1 contained <= 0 on log scale!"

                has_non_pos_price = await eval_js("""
                    window.fundChart.data.datasets[0].data.some(v => v !== null && v <= 0)
                """)
                assert not has_non_pos_price, f"{sym}: dataset 0 contained <= 0 on log scale!"

                span_gaps = await eval_js("window.fundChart.data.datasets[1].spanGaps")
                assert span_gaps is True, f"{sym}: spanGaps should be true"

                # Check HUD
                hud_text = await eval_js("document.getElementById('fundHoverHud').innerText")
                assert sym in hud_text or len(hud_text) > 10, f"{sym}: HUD is empty"

                # Toggle to linear mode and check
                await eval_js("setFundScaleType('linear')")
                await asyncio.sleep(0.1)
                lin_y_type = await eval_js("window.fundChart.options.scales.y.type")
                assert lin_y_type == "linear", f"{sym}: Expected linear scale"

                # Toggle back to log
                await eval_js("setFundScaleType('logarithmic')")
                await asyncio.sleep(0.1)

                print(f"✓ {sym:12} verified on Log and Linear scales (0 errors)")

            # Check specific Tata Motors negative EPS hover point
            await eval_js("selectStockChip('TATAMOTORS')")
            await asyncio.sleep(0.2)
            neg_idx = await eval_js("""
                (function() {
                    var ds = window.fundChart.data.labels;
                    return ds.indexOf('2019-07');
                })()
            """)
            if neg_idx != -1:
                await eval_js(f"window.fundChart.options.plugins.tooltip.external({{tooltip: {{dataPoints: [{{dataIndex: {neg_idx}}}]}}}})")
                hud_content = await eval_js("document.getElementById('fundHoverHud').innerHTML")
                print("✓ Tata Motors 2019-07 Loss HUD:", hud_content[:150], "...")
                assert "Net Losses" in hud_content or "Loss" in hud_content, "Expected loss warning badge in HUD"

            # Edge Case: Stock with negative EPS and Price checkbox hidden (Real EPS only on log scale)
            print("\n--- Edge Case: Real EPS only (Price hidden) on Log Scale ---")
            await eval_js("""
                document.getElementById('chkFundPrice').checked = false;
                document.getElementById('chkFundEps').checked = true;
                updateFundSeriesVisibility();
            """)
            await asyncio.sleep(0.2)
            y_exists = await eval_js("!!window.fundChart.scales.y")
            assert y_exists, "Y-scale should exist even when Price is hidden"
            print("✓ Real EPS only on Log Scale verified without errors")
            # Restore Price checkbox
            await eval_js("""
                document.getElementById('chkFundPrice').checked = true;
                updateFundSeriesVisibility();
            """)

            # Verify Dynamic Scale Anchoring on Key Stocks (RELIANCE, HDFCBANK, TATAMOTORS)
            print("\n--- Testing Dynamic Logarithmic Anchoring on Key Stocks ---")
            await eval_js("selectStockChip('RELIANCE')")
            await asyncio.sleep(0.3)
            rel_min = await eval_js("window.fundChart.scales.y.min")
            print(f"✓ RELIANCE dynamic Y-scale min: {rel_min}")
            assert rel_min == 80, f"Expected RELIANCE min=80, got {rel_min}"

            await eval_js("selectStockChip('HDFCBANK')")
            await asyncio.sleep(0.3)
            hdfc_min = await eval_js("window.fundChart.scales.y.min")
            print(f"✓ HDFCBANK dynamic Y-scale min: {hdfc_min}")
            assert hdfc_min == 80, f"Expected HDFCBANK min=80, got {hdfc_min}"

            await eval_js("selectStockChip('TATAMOTORS')")
            await asyncio.sleep(0.3)
            tm_min = await eval_js("window.fundChart.scales.y.min")
            print(f"✓ TATAMOTORS dynamic Y-scale min (both series): {tm_min}")
            assert 2 <= tm_min <= 5, f"Expected TATAMOTORS min between 2 and 5, got {tm_min}"

            # Toggle EPS off on TATAMOTORS: dynamic bounds should adjust to Price-only (min=30)
            await eval_js("""
                document.getElementById('chkFundEps').checked = false;
                updateFundSeriesVisibility();
            """)
            await asyncio.sleep(0.2)
            tm_price_only_min = await eval_js("window.fundChart.scales.y.min")
            print(f"✓ TATAMOTORS Price-only dynamic Y-scale min: {tm_price_only_min}")
            assert tm_price_only_min == 30, f"Expected TATAMOTORS Price-only min=30, got {tm_price_only_min}"

            # Restore EPS checkbox
            await eval_js("""
                document.getElementById('chkFundEps').checked = true;
                updateFundSeriesVisibility();
            """)
            await asyncio.sleep(0.2)

            # Direct Unit Tests on computeFundDynamicYBounds
            print("\n--- Unit Testing computeFundDynamicYBounds Edge Cases ---")
            edge_null = await eval_js("window.computeFundDynamicYBounds([null, null], [null], true, true, 'logarithmic')")
            assert edge_null == {'suggestedMin': 80, 'suggestedMax': 120}, f"Failed on all-null: {edge_null}"
            edge_empty = await eval_js("window.computeFundDynamicYBounds([], [], true, true, 'logarithmic')")
            assert edge_empty == {'suggestedMin': 80, 'suggestedMax': 120}, f"Failed on empty: {edge_empty}"
            edge_single = await eval_js("window.computeFundDynamicYBounds([100], [], true, false, 'logarithmic')")
            assert edge_single == {'suggestedMin': 85, 'suggestedMax': 115}, f"Failed on single point: {edge_single}"
            edge_neg = await eval_js("window.computeFundDynamicYBounds([-10, -5], [0], true, true, 'logarithmic')")
            assert edge_neg == {'suggestedMin': 80, 'suggestedMax': 120}, f"Failed on all-negative: {edge_neg}"
            edge_sub_tenth = await eval_js("window.computeFundDynamicYBounds([0.05], [], true, false, 'logarithmic')")
            assert edge_sub_tenth['suggestedMin'] < 0.05, f"Expected suggestedMin < 0.05, got {edge_sub_tenth['suggestedMin']}"
            assert edge_sub_tenth['suggestedMin'] == 0.0425, f"Expected 0.0425, got {edge_sub_tenth['suggestedMin']}"
            edge_obj = await eval_js("window.computeFundDynamicYBounds([{y: 100}], [{y: 200}], true, true, 'logarithmic')")
            assert edge_obj == {'suggestedMin': 85, 'suggestedMax': 230}, f"Failed on object points: {edge_obj}"
            edge_inf = await eval_js("window.computeFundDynamicYBounds([Infinity, 100], [], true, false, 'logarithmic')")
            assert edge_inf == {'suggestedMin': 85, 'suggestedMax': 115}, f"Failed on Infinity handling: {edge_inf}"
            print("✓ computeFundDynamicYBounds edge cases (all-null, empty, single point, negative, sub-0.1, objects, infinity) verified!")

            print("\n=======================================================")
            print("TEST 4: MOVABLE / PAN & ZOOM LIKE TRADINGVIEW")
            print("=======================================================")
            # Check zoom plugin config including limits
            zoom_config = await eval_js("""
                ({
                    panEnabled: window.fundChart.options.plugins.zoom.pan.enabled,
                    panMode: window.fundChart.options.plugins.zoom.pan.mode,
                    wheelEnabled: window.fundChart.options.plugins.zoom.zoom.wheel.enabled,
                    pinchEnabled: window.fundChart.options.plugins.zoom.zoom.pinch.enabled,
                    zoomMode: window.fundChart.options.plugins.zoom.zoom.mode,
                    minRange: window.fundChart.options.plugins.zoom.limits.x.minRange
                })
            """)
            print("✓ Zoom plugin options:", zoom_config)
            assert zoom_config["panEnabled"] is True, "Pan should be enabled"
            assert zoom_config["panMode"] == "x", "Pan mode should be 'x'"
            assert zoom_config["wheelEnabled"] is True, "Wheel zoom should be enabled"
            assert zoom_config["pinchEnabled"] is True, "Pinch zoom should be enabled"
            assert zoom_config["zoomMode"] == "x", "Zoom mode should be 'x'"
            assert zoom_config["minRange"] == 3, f"Expected minRange=3, got {zoom_config['minRange']}"

            # Record initial bounds
            init_max = await eval_js("window.fundChart.scales.x.max")
            init_min = await eval_js("window.fundChart.scales.x.min")
            print(f"✓ Initial X bounds: min={init_min}, max={init_max}")

            # Zoom in by 1.5x (narrowing category scale window)
            await eval_js("window.fundChart.zoom(1.5)")
            await asyncio.sleep(0.2)
            zoomed_min = await eval_js("window.fundChart.scales.x.min")
            zoomed_max = await eval_js("window.fundChart.scales.x.max")
            print(f"✓ Zoomed in X bounds: min={zoomed_min}, max={zoomed_max}")
            assert (zoomed_max - zoomed_min) < (init_max - init_min), "Zooming in should narrow bounds range"
            assert await eval_js("window.fundChart.isZoomedOrPanned()"), "Chart should report isZoomedOrPanned"

            # Extreme Zoom Test: Zooming in excessively (100x) respects minRange: 3
            await eval_js("window.fundChart.zoom(100)")
            await asyncio.sleep(0.2)
            extreme_min = await eval_js("window.fundChart.scales.x.min")
            extreme_max = await eval_js("window.fundChart.scales.x.max")
            extreme_span = extreme_max - extreme_min
            print(f"✓ Extreme zoom in span: {extreme_span} (min={extreme_min}, max={extreme_max})")
            assert extreme_span >= 3, f"Zoom limits violated: span was {extreme_span}, expected >= 3"

            # Test Zoom Preservation across Log <-> Linear Toggle
            print("\n--- Testing Zoom Preservation on Scale Switch ---")
            await eval_js("window.fundChart.zoomScale('x', {min: 30, max: 80})")
            await asyncio.sleep(0.1)
            z_before = await eval_js("[window.fundChart.scales.x.min, window.fundChart.scales.x.max]")
            assert z_before == [30, 80], f"Expected [30, 80], got {z_before}"
            await eval_js("setFundScaleType('linear')")
            await asyncio.sleep(0.1)
            z_lin = await eval_js("[window.fundChart.scales.x.min, window.fundChart.scales.x.max]")
            assert z_lin == [30, 80], f"Zoom lost on switch to linear: got {z_lin}"
            await eval_js("setFundScaleType('logarithmic')")
            await asyncio.sleep(0.1)
            z_log = await eval_js("[window.fundChart.scales.x.min, window.fundChart.scales.x.max]")
            assert z_log == [30, 80], f"Zoom lost on switch to logarithmic: got {z_log}"
            print("✓ Zoom/pan range [30, 80] strictly preserved across scale toggles")

            # Reset zoom before drag test
            await eval_js("resetFundZoom()")
            await asyncio.sleep(0.2)
            # Zoom to middle window [50, 100] for mouse drag test
            await eval_js("window.fundChart.zoomScale('x', {min: 50, max: 100})")
            await asyncio.sleep(0.1)

            # Scroll canvas into view so CDP mouse coordinates hit canvas directly
            await eval_js("document.getElementById('fundamentalsChart').scrollIntoView({block: 'center'})")
            await asyncio.sleep(0.2)

            canvas_box = await eval_js("""
                (function() {
                    var r = document.getElementById('fundamentalsChart').getBoundingClientRect();
                    return { x: r.left + r.width/2, y: r.top + r.height/2, width: r.width, height: r.height };
                })()
            """)
            cx, cy = canvas_box['x'], canvas_box['y']
            
            drag_start_min = await eval_js("window.fundChart.scales.x.min")
            drag_start_max = await eval_js("window.fundChart.scales.x.max")
            print(f"Bounds before mouse drag: min={drag_start_min}, max={drag_start_max}")

            # Send CDP mouse drag (drag left from cx to cx - 200 to pan chart rightward)
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": "Input.dispatchMouseEvent", "params": {"type": "mousePressed", "x": cx, "y": cy, "button": "left", "buttons": 1, "clickCount": 1}}))
            await asyncio.sleep(0.05)
            for step in range(1, 12):
                msg_id += 1
                await ws.send(json.dumps({"id": msg_id, "method": "Input.dispatchMouseEvent", "params": {"type": "mouseMoved", "x": cx - step * 20, "y": cy, "button": "left", "buttons": 1}}))
                await asyncio.sleep(0.02)
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": "Input.dispatchMouseEvent", "params": {"type": "mouseReleased", "x": cx - 240, "y": cy, "button": "left", "clickCount": 1}}))
            await asyncio.sleep(0.3)

            drag_end_min = await eval_js("window.fundChart.scales.x.min")
            drag_end_max = await eval_js("window.fundChart.scales.x.max")
            print(f"Bounds after mouse drag: min={drag_end_min}, max={drag_end_max}")
            assert (drag_end_min != drag_start_min or drag_end_max != drag_start_max), "Mouse drag MUST pan chart bounds!"
            assert drag_end_min > drag_start_min, f"Mouse drag left should pan view right: {drag_end_min} > {drag_start_min}"
            print("✓ Real CDP mouse drag on canvas successfully updated chart bounds!")

            # Test cursor simulation
            await eval_js("document.getElementById('fundamentalsChart').dispatchEvent(new MouseEvent('mousedown'))")
            cursor_during_drag = await eval_js("document.getElementById('fundamentalsChart').style.cursor")
            print(f"✓ Cursor on mousedown: '{cursor_during_drag}'")
            assert cursor_during_drag == "grabbing", f"Expected 'grabbing', got '{cursor_during_drag}'"

            await eval_js("window.dispatchEvent(new MouseEvent('mouseup'))")
            cursor_after_release = await eval_js("document.getElementById('fundamentalsChart').style.cursor")
            print(f"✓ Cursor on mouseup: '{cursor_after_release}'")
            assert cursor_after_release == "grab", f"Expected 'grab', got '{cursor_after_release}'"

            # Test Reset button
            print("\n=======================================================")
            print("TEST 5: RESET BUTTON RESTORES DEFAULT ZOOM & PAN")
            print("=======================================================")
            await eval_js("resetFundZoom()")
            await asyncio.sleep(0.3)
            reset_min = await eval_js("window.fundChart.scales.x.min")
            reset_max = await eval_js("window.fundChart.scales.x.max")
            print(f"✓ Reset X bounds: min={reset_min}, max={reset_max}")
            assert reset_min == init_min and reset_max == init_max, "Reset button should restore original bounds"

            # Test direct fundChart.resetZoom()
            await eval_js("window.fundChart.zoom(1.5)")
            await asyncio.sleep(0.1)
            z_max = await eval_js("window.fundChart.scales.x.max")
            assert z_max != init_max, "Chart should be zoomed"
            await eval_js("window.fundChart.resetZoom()")
            await asyncio.sleep(0.1)
            rz_max = await eval_js("window.fundChart.scales.x.max")
            print(f"✓ After fundChart.resetZoom(): max={rz_max}")
            assert rz_max == init_max, "fundChart.resetZoom() should reset zoom"

            print("\n=======================================================")
            print("TEST 6: CONSOLE ERROR CHECK")
            print("=======================================================")
            print(f"Total console errors captured: {len(console_errors)}")
            if console_errors:
                for err in console_errors:
                    print("ERROR:", err)
            assert len(console_errors) == 0, f"Found {len(console_errors)} console errors!"
            print("✓ ALL TESTS PASSED WITH 0 CONSOLE ERRORS! 🎉")

    finally:
        p.terminate()
        try:
            p.wait(timeout=2)
        except Exception:
            p.kill()

if __name__ == "__main__":
    asyncio.run(run_tests())
