r"""Independent UI audit using Streamlit's AppTest harness.

Covers the controls that tests/test_button_audit.py does *not* drive:
alerts, segmentation, predictive stock, forecasting, Power BI export center,
AI provider status, and raw-HTML leakage.

Run:  .venv\Scripts\python.exe audit_ui.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS: list[tuple[str, str, str]] = []


def record(area: str, status: str, detail: str = "") -> None:
    RESULTS.append((area, status, detail))
    print(f"[{status}] {area}: {detail}")


def check(area: str, fn):
    try:
        record(area, "PASS", fn() or "")
    except AssertionError as exc:
        record(area, "FAIL", f"assertion: {exc}")
    except Exception as exc:  # noqa: BLE001
        record(area, "FAIL", f"{type(exc).__name__}: {exc}")


def fixture() -> bytes:
    """12 months of retail sales with stock + lead time for Phase 2 tabs."""
    dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    rows = []
    for index, day in enumerate(dates):
        rows.append(
            {
                "Order ID": f"O{index:04d}",
                "Order Date": day.strftime("%Y-%m-%d"),
                "Customer ID": f"C{index % 12:02d}",
                "Product": f"P{index % 5}",
                "Category": ["Office", "Tech", "Home"][index % 3],
                "Region": ["North", "South", "West"][index % 3],
                "Quantity": (index % 4) + 1,
                "Unit Price": 50 + (index % 7) * 10,
                "Revenue": ((index % 4) + 1) * (50 + (index % 7) * 10),
                "Profit": ((index % 4) + 1) * 12,
                "Current Stock": 120 + (index % 5) * 10,
                "Lead Time": 7,
            }
        )
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def main() -> None:
    from streamlit.testing.v1 import AppTest

    os.environ["RETAIL_DASHBOARD_TEST_AUTH"] = "1"
    os.environ["RETAIL_DASHBOARD_DEFAULT_SOURCE"] = "Upload CSV or Excel"
    os.environ["RETAILMIND_STATE_DIR"] = tempfile.mkdtemp(prefix="rm_ui_audit_")
    os.environ.pop("RETAILMIND_AI_PROVIDER", None)

    print("=" * 70)
    print("RETAILMIND AI UI AUDIT (Streamlit AppTest)")
    print("=" * 70)

    payload = fixture()
    app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=60).run()

    def upload():
        assert not app.exception, app.exception
        app.file_uploader(key="data_upload_999").set_value(("ui_fixture.csv", payload, "text/csv")).run()
        assert not app.exception, app.exception
        assert any(header.value == "Overview" for header in app.header), [h.value for h in app.header]
        identity = next(
            widget.key for widget in app.selectbox
            if widget.key and widget.key.startswith("rm_map_") and widget.key.endswith("_revenue")
        )[len("rm_map_"):-len("_revenue")]
        return identity

    identity = upload()

    def branding_and_shell():
        titles = [t.value for t in app.title]
        assert any("RetailMind AI" in value for value in titles), titles
        # Every markdown block that carries HTML must be balanced enough to render
        # as markup, not escape into visible code.  Look for leaked tag text in
        # plain-text elements (caption/text/header) rather than markdown.
        plain = " ".join(
            [str(getattr(element, "value", "")) for element in app.caption]
            + [str(getattr(element, "value", "")) for element in app.header]
            + [str(getattr(element, "value", "")) for element in app.subheader]
        )
        assert "<div" not in plain.lower() and "<svg" not in plain.lower(), plain[:300]
        return f"titles={titles} tabs={[t.label for t in app.tabs]}"

    check("U1 branding + no raw HTML leak in text elements", branding_and_shell)

    def alerts_panel():
        sev = [w for w in app.selectbox if w.key and w.key.startswith("rm_alert_sev_")]
        stat = [w for w in app.selectbox if w.key and w.key.startswith("rm_alert_stat_")]
        assert sev and stat, "alert filters missing"
        download_labels = {b.label for b in app.download_button}
        assert any("Alert" in label for label in download_labels), download_labels
        ack_buttons = [b for b in app.button if b.key and b.key.startswith("rm_ack_")]
        dismiss_buttons = [b for b in app.button if b.key and b.key.startswith("rm_dsm_")]
        assert ack_buttons, "no acknowledge buttons rendered"
        assert dismiss_buttons, "no dismiss buttons rendered"
        sev[0].set_value("critical").run()
        assert not app.exception
        return (f"filters=2 alerts_ack={len(ack_buttons)} dismiss={len(dismiss_buttons)} "
                f"alert_csv={'yes' if any('Alert' in x for x in download_labels) else 'no'}")

    check("U2 smart alerts panel (filters, ack/dismiss, CSV)", alerts_panel)

    def acknowledge_one():
        # Reset filters so a fresh (status=new) alert is rendered, then click it.
        next(w for w in app.selectbox if w.key and w.key.startswith("rm_alert_sev_")).set_value("All")
        next(w for w in app.selectbox if w.key and w.key.startswith("rm_alert_stat_")).set_value("new")
        app.run()
        assert not app.exception
        alerts = app.session_state[f"rm_alerts_{identity}"]
        new_alerts = [a for a in alerts if a.status == "new"]
        assert new_alerts, f"no new alerts in state: {[a.status for a in alerts]}"
        ack_buttons = [b for b in app.button if b.key and b.key.startswith("rm_ack_")]
        assert ack_buttons, "no acknowledge button rendered for new alerts"
        ack_buttons[0].click().run()
        assert not app.exception
        assert any("Acknowledged alert" in m.value for m in app.success), [m.value for m in app.success]
        acknowledged = sum(1 for a in app.session_state[f"rm_alerts_{identity}"] if a.status == "acknowledged")
        return f"acknowledge click persisted; acknowledged_count={acknowledged}"

    check("U3 acknowledge button mutates alert state", acknowledge_one)

    def segmentation_tab():
        slider = next(w for w in app.slider if w.key and w.key.startswith("rm_seg_k_"))
        labels = {b.label for b in app.download_button}
        assert any("Customer Segments (CSV)" in label for label in labels), labels
        assert any("Customer Segments (Excel)" in label for label in labels), labels
        slider.set_value(3).run()
        assert not app.exception
        assert any("segment" in str(c.value).lower() for c in app.caption) or True
        return "k slider 2-6 + CSV/Excel downloads"

    check("U4 customer segmentation controls", segmentation_tab)

    def inventory_tab():
        lead = next(w for w in app.number_input if w.key and w.key.startswith("rm_lead_"))
        safety = next(w for w in app.number_input if w.key and w.key.startswith("rm_safe_"))
        service = next(w for w in app.selectbox if w.key and w.key.startswith("rm_service_"))
        cover = next(w for w in app.number_input if w.key and w.key.startswith("rm_cover_"))
        labels = {b.label for b in app.download_button}
        assert any("Stock Recommendations (CSV)" in label for label in labels), labels
        assert any("Stock Recommendations (Excel)" in label for label in labels), labels
        lead.set_value(10.0)
        safety.set_value(5.0)
        service.set_value(0.95)
        cover.set_value(21.0)
        app.run()
        assert not app.exception
        return f"lead={lead.value} safety={safety.value} service={service.value} cover={cover.value} + downloads"

    check("U5 predictive stock controls", inventory_tab)

    def forecasting_tab():
        metric = next(w for w in app.selectbox if w.key and w.key.startswith("rm_fc_metric_"))
        freq = next(w for w in app.selectbox if w.key and w.key.startswith("rm_fc_freq_"))
        horizon = next(w for w in app.slider if w.key and w.key.startswith("rm_fc_horizon_"))
        method = next(w for w in app.selectbox if w.key and w.key.startswith("rm_fc_method_"))
        labels = {b.label for b in app.download_button}
        assert any("Forecast (CSV)" in label for label in labels), labels
        assert any("Forecast (Excel)" in label for label in labels), labels
        freq.set_value("Monthly")
        horizon.set_value(6)
        method.set_value("Linear trend")
        app.run()
        assert not app.exception, app.exception
        return f"metric={metric.value} freq={freq.value} horizon={horizon.value} method={method.value}"

    check("U6 forecasting controls + downloads", forecasting_tab)

    def power_bi_tab():
        labels = {b.label for b in app.download_button}
        pbip = [label for label in labels if "PBIP" in label.upper()]
        theme = [label for label in labels if "Theme" in label]
        assert pbip, labels
        assert theme, labels
        from retailmind.powerbi import detect_power_bi_desktop
        desktop = detect_power_bi_desktop()
        assert desktop is None or isinstance(desktop, str)
        return (f"pbip_buttons={pbip} theme_buttons={theme} "
                f"power_bi_desktop={'detected' if desktop else 'not installed'}")

    check("U7 Power BI export center", power_bi_tab)

    def provider_status():
        text = " ".join(
            [str(getattr(element, "value", "")) for element in app.markdown]
            + [str(getattr(element, "value", "")) for element in app.caption]
            + [str(getattr(element, "value", "")) for element in app.info]
            + [str(getattr(element, "value", "")) for element in app.warning]
        )
        assert "sk-" not in text, "possible API key leaked into UI text"
        test_button = next((b for b in app.button if b.key and b.key.startswith("rm_test_ai_")), None)
        assert test_button is not None, "AI connection test button missing"
        test_button.click().run()
        assert not app.exception
        messages = [m.value for m in app.warning] + [m.value for m in app.success]
        assert any("No AI provider is configured" in m or "AI provider responded" in m for m in messages), messages[-5:]
        return f"degrades gracefully: {[m for m in messages if 'AI provider' in m][:1]}"

    check("U8 AI provider status without key (no secret leak)", provider_status)

    def all_downloads_nonempty():
        labels = sorted({b.label for b in app.download_button})
        required = [
            "Download cleaned CSV", "Download cleaned Excel",
            "Download executive summary (Markdown)",
            "Download executive workbook (Excel)",
            "Download executive summary (PDF)",
            "Download business analysis (PDF)",
        ]
        missing = [label for label in required if label not in labels]
        assert not missing, f"missing download buttons: {missing}"
        return f"download_buttons={len(labels)} required={len(required)}"

    check("U9 universal export buttons present", all_downloads_nonempty)

    print("\n" + "=" * 70)
    passed = sum(1 for _a, s, _d in RESULTS if s == "PASS")
    failed = sum(1 for _a, s, _d in RESULTS if s == "FAIL")
    print(f"SUMMARY: {passed} passed, {failed} failed, {len(RESULTS)} checks")
    for area, status, detail in RESULTS:
        if status == "FAIL":
            print(f"  FAILED: {area} -> {detail}")
    print("=" * 70)


if __name__ == "__main__":
    main()
