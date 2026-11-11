"""Unit tests for RetailMind AI smart alerts and notifications."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from retailmind.alerts import (
    Alert,
    Notification,
    NotificationPreferences,
    acknowledge,
    alerts_csv_bytes,
    build_notifications,
    detect_alerts,
    dismiss,
    filter_alerts,
    alert_digest_html,
    merge_alerts,
    send_alert_digest,
    send_test_email,
    send_email_notification,
)
from retailmind.schema import infer_schema


@pytest.fixture
def sample_sales_df() -> pd.DataFrame:
    # 60 days of data with a decline in the latest 30-day window
    dates_prev = pd.date_range("2025-01-01", periods=30, freq="D")
    dates_curr = pd.date_range("2025-01-31", periods=30, freq="D")
    
    df_prev = pd.DataFrame({
        "order_date": dates_prev,
        "sales": [200.0] * 30,
        "profit": [40.0] * 30,
        "quantity": [20] * 30,
        "cost": [160.0] * 30,
        "product": ["Widget A"] * 15 + ["Widget B"] * 15,
        "region": ["North"] * 30,
        "customer": [f"Cust_{i}" for i in range(30)],
        "order_id": [f"ORD_{i}" for i in range(30)],
    })
    
    # In current window, sales dropped significantly (50% drop)
    df_curr = pd.DataFrame({
        "order_date": dates_curr,
        "sales": [100.0] * 30,
        "profit": [10.0] * 30,
        "quantity": [10] * 30,
        "cost": [90.0] * 30,
        "product": ["Widget A"] * 15 + ["Widget B"] * 15,
        "region": ["North"] * 30,
        "customer": [f"Cust_{i+30}" for i in range(30)],
        "order_id": [f"ORD_{i+30}" for i in range(30)],
    })
    return pd.concat([df_prev, df_curr], ignore_index=True)


def test_empty_dataframe_returns_empty_alerts():
    df = pd.DataFrame()
    schema = infer_schema(df)
    alerts = detect_alerts(df, schema)
    assert alerts == []


def test_missing_date_column_returns_explanatory_alert():
    df = pd.DataFrame({"sales": [100, 200], "product": ["A", "B"]})
    schema = infer_schema(df)
    alerts = detect_alerts(df, schema)
    assert len(alerts) >= 1
    assert any("Time-based alerts unavailable" in alert.title for alert in alerts)
    assert alerts[0].severity == "info"


def test_detect_alerts_detects_decline_and_margin_drop(sample_sales_df: pd.DataFrame):
    schema = infer_schema(sample_sales_df)
    alerts = detect_alerts(sample_sales_df, schema)
    
    assert len(alerts) > 0
    titles = [a.title for a in alerts]
    
    # Revenue declined by 50% -> critical or warning
    assert any("Revenue declined" in t or "Sales declined" in t for t in titles)
    revenue_alert = next(a for a in alerts if "Revenue declined" in a.title or "Sales" in a.title)
    assert revenue_alert.severity in ("critical", "warning")
    assert revenue_alert.current_value is not None
    assert revenue_alert.previous_value is not None
    assert revenue_alert.pct_change is not None
    assert revenue_alert.comparison_period != ""
    assert revenue_alert.fingerprint != ""
    assert revenue_alert.status == "new"


def test_alert_fingerprint_and_deduplication(sample_sales_df: pd.DataFrame):
    schema = infer_schema(sample_sales_df)
    alerts1 = detect_alerts(sample_sales_df, schema)
    
    # Acknowledge the first alert
    first_alert = alerts1[0]
    acknowledge(first_alert)
    assert first_alert.status == "acknowledged"
    assert first_alert.acknowledged_at is not None
    
    # Re-detect and merge: acknowledgement must survive refresh
    alerts2 = detect_alerts(sample_sales_df, schema)
    merged = merge_alerts([first_alert], alerts2)
    
    matched = next((a for a in merged if a.fingerprint == first_alert.fingerprint), None)
    assert matched is not None
    assert matched.status == "acknowledged"


def test_dismiss_alert():
    alert = Alert(title="Test Alert", description="Desc", metric="sales", severity="warning")
    dismiss(alert)
    assert alert.status == "dismissed"
    assert alert.acknowledged_at is not None


def test_filter_alerts():
    a1 = Alert(title="A1", description="", metric="sales", severity="critical", status="new")
    a2 = Alert(title="A2", description="", metric="profit", severity="warning", status="acknowledged")
    a3 = Alert(title="A3", description="", metric="cost", severity="info", status="dismissed")
    
    alerts = [a1, a2, a3]
    assert len(filter_alerts(alerts, severity="critical")) == 1
    assert len(filter_alerts(alerts, status="new")) == 1
    assert len(filter_alerts(alerts, severity="warning", status="acknowledged")) == 1
    assert len(filter_alerts(alerts, severity="info", status="new")) == 0


def test_alerts_csv_bytes():
    a1 = Alert(
        title="Revenue dropped", description="Fell by 50%", metric="revenue",
        severity="critical", current_value=100.0, previous_value=200.0, pct_change=-0.5,
        comparison_period="Jan vs Dec", suggestion="Investigate prices",
    )
    csv_bytes = alerts_csv_bytes([a1])
    assert isinstance(csv_bytes, bytes)
    text = csv_bytes.decode("utf-8-sig")
    assert "Revenue dropped" in text
    assert "critical" in text
    assert "-0.5" in text


def test_notification_preferences_and_building():
    prefs = NotificationPreferences(min_severity="warning", email_enabled=False)
    
    a1 = Alert(title="Critical issue", description="Severe drop", metric="sales", severity="critical")
    a2 = Alert(title="Minor info", description="Normal update", metric="sales", severity="info")
    a3 = Alert(title="Dismissed alert", description="Ignored", metric="cost", severity="warning", status="dismissed")
    
    notifications = build_notifications([a1, a2, a3], prefs)
    # a2 is info (below warning threshold), a3 is dismissed -> only a1
    assert len(notifications) == 1
    assert notifications[0].title == "Critical issue"
    assert notifications[0].severity == "critical"


def test_alert_digest_escapes_values_and_lists_alerts():
    alert = Alert(title="Revenue <dropped>", description="Body", metric="sales", severity="critical", scope="product_name:Chair & Desk", pct_change=-0.5)
    html = alert_digest_html([alert], "https://example.com/smart-alerts")
    assert "Revenue &lt;dropped&gt;" in html
    assert "Chair &amp; Desk" in html
    assert "-50.0%" in html


def test_send_alert_digest_respects_disabled_preferences():
    prefs = NotificationPreferences(email_enabled=False)
    assert send_alert_digest([], prefs, "https://example.com") == "disabled"


def test_notification_preferences_smtp_ready_is_independent_of_enabled():
    prefs = NotificationPreferences(
        email_enabled=False,
        recipients=("alerts@example.com",),
        smtp_host="smtp.example.com",
        sender="noreply@example.com",
    )
    assert prefs.configured() is False
    assert prefs.smtp_ready() is True


@patch("smtplib.SMTP")
def test_send_test_email_reports_smtp_acceptance(mock_smtp):
    mock_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_instance
    prefs = NotificationPreferences(
        email_enabled=False,
        recipients=(),
        smtp_host="smtp.example.com",
        sender="noreply@example.com",
    )
    assert send_test_email(prefs, "owner@example.com") == "accepted_by_smtp"
    sent = mock_instance.send_message.call_args.args[0]
    assert sent["To"] == "owner@example.com"
    assert "SMTP test" in sent["Subject"]


def test_send_test_email_requires_transport():
    prefs = NotificationPreferences(email_enabled=True, smtp_host=None, sender=None)
    assert send_test_email(prefs, "owner@example.com") == "not_configured"


def test_send_email_notification_when_disabled():
    prefs = NotificationPreferences(email_enabled=False)
    notif = Notification(alert_id="1", title="Test", message="Body", severity="warning", fingerprint="fp1")
    status = send_email_notification(notif, prefs)
    assert status == "disabled"


def test_send_email_notification_when_not_configured():
    prefs = NotificationPreferences(email_enabled=True, smtp_host=None)
    notif = Notification(alert_id="1", title="Test", message="Body", severity="warning", fingerprint="fp1")
    status = send_email_notification(notif, prefs)
    assert status == "not_configured"


@patch("smtplib.SMTP")
def test_send_email_notification_success(mock_smtp):
    mock_instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = mock_instance
    
    prefs = NotificationPreferences(
        email_enabled=True,
        recipients=("alerts@example.com",),
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="password",
        sender="noreply@example.com",
        use_tls=True,
    )
    notif = Notification(alert_id="1", title="Revenue Alert", message="Revenue dropped 20%", severity="critical", fingerprint="fp1")
    status = send_email_notification(notif, prefs)
    assert status == "accepted_by_smtp"
    mock_instance.send_message.assert_called_once()
