"""Regression tests for alert email delivery state (retry + digest)."""

from __future__ import annotations

import json
import tempfile
from unittest.mock import patch

import api
from retailmind.alerts import Alert, NotificationPreferences


def _preferences(**overrides):
    values = dict(
        email_enabled=True,
        recipients=("owner@example.com",),
        smtp_host="smtp.example.com",
        sender="noreply@example.com",
    )
    values.update(overrides)
    return NotificationPreferences(**values)


def _alert():
    return Alert(title="Revenue dropped", description="Fell", metric="sales", severity="critical")


def _rows(alert):
    return [{"id": alert.id, "severity": alert.severity, "status": "new", "title": alert.title}]


def test_failed_email_attempts_stay_retryable_then_stop_after_three(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILMIND_STATE_DIR", str(tmp_path))
    alert = _alert()
    rows = _rows(alert)
    user_id = 987001
    dataset_id = "dataset-retry"

    with patch.object(api, "send_alert_email", return_value="failed: SMTPAuthenticationError") as sender:
        for expected in (1, 2, 3):
            result = api.dispatch_alert_emails(user_id, dataset_id, [alert], rows, _preferences())
            assert result["status"] == "failed"
            state = json.loads((tmp_path / "alerts" / f"user-{user_id}.json").read_text(encoding="utf-8"))
            entry = state["datasets"][dataset_id][alert.id]
            assert entry["delivery_attempts"] == expected
            assert "notified_at" not in entry
            assert entry["last_delivery_error"] == "failed: SMTPAuthenticationError"

        assert sender.call_count == 3
        exhausted = api.dispatch_alert_emails(user_id, dataset_id, [alert], rows, _preferences())
        assert exhausted["status"] == "no_new_alerts"
        assert sender.call_count == 3


def test_accepted_email_is_marked_notified_once(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILMIND_STATE_DIR", str(tmp_path))
    alert = _alert()
    rows = _rows(alert)
    user_id = 987002
    dataset_id = "dataset-accepted"

    with patch.object(api, "send_alert_email", return_value="accepted_by_smtp") as sender:
        first = api.dispatch_alert_emails(user_id, dataset_id, [alert], rows, _preferences())
        assert first["status"] == "sent"
        assert first["sent"][0]["alert_id"] == alert.id
        second = api.dispatch_alert_emails(user_id, dataset_id, [alert], rows, _preferences())
        assert second["status"] == "no_new_alerts"
        assert sender.call_count == 1


def test_daily_frequency_sends_one_digest_per_day(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILMIND_STATE_DIR", str(tmp_path))
    alert = _alert()
    rows = _rows(alert)
    user_id = 987003
    dataset_id = "dataset-digest"
    preferences = _preferences(frequency="daily")

    with patch.object(api, "send_alert_digest", return_value="accepted_by_smtp") as digest:
        first = api.dispatch_alert_emails(user_id, dataset_id, [alert], rows, preferences)
        assert first["status"] == "digest_sent"
        assert digest.call_count == 1
        second = api.dispatch_alert_emails(user_id, dataset_id, [alert], rows, preferences)
        assert second["status"] == "no_new_alerts"
        assert digest.call_count == 1

        fresh = _alert()
        fresh.title = "Cost increased"
        fresh.fingerprint = "fresh-fingerprint"
        fresh.id = "fresh-alert"
        third = api.dispatch_alert_emails(user_id, dataset_id, [fresh], _rows(fresh), preferences)
        assert third["status"] == "digest_already_sent"
        assert digest.call_count == 1
