"""Real Chromium workflow coverage, executed by CI after Playwright installation."""
import os
import socket
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="set RUN_E2E=1 after installing a Playwright browser to run browser coverage",
)

CSV = b"Order_ID,Order_Date,Customer_Name,City,Product_Category,Product_Name,Sales,Profit\nA,2025-01-01,Alice,Delhi,Office,Pen,100,20\nB,2025-01-02,Bob,Pune,Tech,Phone,200,50\nC,2025-01-03,Alice,Delhi,Office,Pad,150,30\n"

@pytest.fixture(scope="module")
def dashboard_url():
    port = 8765
    env = os.environ | {"RETAIL_DASHBOARD_DEFAULT_SOURCE": "Upload CSV or Excel"}
    process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard.py", "--server.port", str(port), "--server.headless", "true"], env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25): break
        except OSError: time.sleep(0.25)
    else:
        process.terminate()
        raise RuntimeError("Streamlit did not become reachable")
    yield url
    process.terminate()
    process.wait(timeout=10)

@pytest.mark.e2e
def test_upload_filters_reset_kpis_and_downloads(page, dashboard_url):
    page.goto(dashboard_url)
    page.locator('input[type="file"]').set_input_files({"name": "retail.csv", "mimeType": "text/csv", "buffer": CSV})
    page.get_by_text("Overview").wait_for()
    baseline = page.get_by_text("Total sales").locator("..").inner_text()
    page.get_by_text("City").click()
    page.get_by_text("Delhi", exact=True).last.click()
    page.get_by_text("Total sales").locator("..").wait_for()
    assert page.get_by_text("Total sales").locator("..").inner_text() != baseline
    page.get_by_role("button", name="Reset filters").click()
    assert page.get_by_text("Total sales").locator("..").inner_text() == baseline
    with page.expect_download():
        page.get_by_role("button", name="Download cleaned CSV").click()
    with page.expect_download():
        page.get_by_role("button", name="Download cleaned Excel").click()
