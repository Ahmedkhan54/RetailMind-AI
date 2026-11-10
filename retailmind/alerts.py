"""Smart alerts and notifications.

Alerts are statistical observations, not causal explanations.  Every alert
carries its comparison period and evidence so a user can audit it.  Duplicate
alerts are prevented with a stable fingerprint (metric + scope + comparison),
which also lets an acknowledgement survive a refresh.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Iterable

import numpy as np
import pandas as pd

from retailmind.schema import DatasetSchema


SEVERITIES = ("critical", "warning", "info")
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
STATUSES = ("new", "acknowledged", "dismissed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fingerprint(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class Alert:
    title: str
    description: str
    metric: str
    severity: str = "info"
    current_value: float | None = None
    previous_value: float | None = None
    pct_change: float | None = None
    comparison_period: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    suggestion: str = ""
    scope: str = "Overall"
    fingerprint: str = ""
    id: str = ""
    status: str = "new"
    detected_at: str = field(default_factory=_now)
    acknowledged_at: str | None = None

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = _fingerprint(self.title, self.metric, self.scope, self.comparison_period)
        if not self.id:
            self.id = self.fingerprint

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Alert":
        known = {field_.name for field_ in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{key: value for key, value in payload.items() if key in known})


def _pct(current: float, previous: float) -> float | None:
    if previous in (None, 0) or not np.isfinite(previous) or not np.isfinite(current):
        return None
    return (current - previous) / abs(previous)


def _severity_from_change(change: float, warning: float, critical: float) -> str:
    if change <= -critical:
        return "critical"
    if change <= -warning:
        return "warning"
    return "info"


def _window_bounds(dates: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp, str] | None:
    clean = pd.to_datetime(dates, format="mixed", errors="coerce").dropna()
    if clean.empty:
        return None
    start, end = clean.min(), clean.max()
    span_days = max(1, int((end - start).days) + 1)
    if span_days >= 60:
        window = 30
    elif span_days >= 14:
        window = 7
    else:
        window = max(1, span_days // 2)
    last_end = end
    last_start = last_end - pd.Timedelta(days=window - 1)
    prev_end = last_start - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=window - 1)
    period = (
        f"{last_start.date()} to {last_end.date()} vs {prev_start.date()} to {prev_end.date()}"
    )
    return last_start, last_end, prev_start, prev_end, period


def _metric_sum(frame: pd.DataFrame, column: str | None, start: pd.Timestamp, end: pd.Timestamp, date_column: str) -> float:
    if not column or column not in frame.columns:
        return 0.0
    dates = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
    mask = dates.between(start, end)
    values = pd.to_numeric(frame.loc[mask, column], errors="coerce")
    return float(values.sum())


def _metric_count(frame: pd.DataFrame, column: str | None, start: pd.Timestamp, end: pd.Timestamp, date_column: str) -> int:
    if not column or column not in frame.columns:
        return 0
    dates = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
    mask = dates.between(start, end)
    return int(frame.loc[mask, column].nunique(dropna=True))


def _add(
    alerts: list[Alert],
    *,
    title: str,
    description: str,
    metric: str,
    severity: str,
    current: float | None,
    previous: float | None,
    comparison: str,
    evidence: dict[str, Any],
    suggestion: str,
    scope: str = "Overall",
) -> None:
    alerts.append(
        Alert(
            title=title,
            description=description,
            metric=metric,
            severity=severity,
            current_value=current,
            previous_value=previous,
            pct_change=_pct(float(current), float(previous)) if current is not None and previous is not None else None,
            comparison_period=comparison,
            evidence=evidence,
            suggestion=suggestion,
            scope=scope,
        )
    )


def _group_changes(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    dimension_role: str,
    metric_role: str,
    bounds: tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp, str],
    min_previous: float,
    warning: float,
    critical: float,
    top_n: int = 10,
) -> list[Alert]:
    dimension = schema.role_column(dimension_role)
    metric = schema.role_column(metric_role)
    date = schema.role_column("date")
    if not dimension or not metric or not date:
        return []
    last_start, last_end, prev_start, prev_end, period = bounds
    dates = pd.to_datetime(frame[date], format="mixed", errors="coerce")
    working = pd.DataFrame(
        {
            "group": frame[dimension].astype("string"),
            "value": pd.to_numeric(frame[metric], errors="coerce"),
            "date": dates,
        }
    ).dropna(subset=["group", "value", "date"])
    current = working[working["date"].between(last_start, last_end)].groupby("group")["value"].sum()
    previous = working[working["date"].between(prev_start, prev_end)].groupby("group")["value"].sum()
    joined = pd.concat([current.rename("current"), previous.rename("previous")], axis=1).fillna(0.0)
    joined = joined[joined["previous"].abs() >= min_previous]
    alerts: list[Alert] = []
    for group, row in joined.iterrows():
        change = _pct(float(row["current"]), float(row["previous"]))
        if change is None:
            continue
        if change <= -warning:
            severity = _severity_from_change(change, warning, critical)
            alerts.append(
                Alert(
                    title=f"{group} {metric_role} declined",
                    description=(
                        f"{group} {metric_role} fell {abs(change):.1%} in the latest period "
                        f"({row['current']:,.2f}) compared with the previous comparable period "
                        f"({row['previous']:,.2f})."
                    ),
                    metric=metric_role,
                    severity=severity,
                    current_value=float(row["current"]),
                    previous_value=float(row["previous"]),
                    pct_change=change,
                    comparison_period=period,
                    evidence={"dimension": dimension_role, "value": str(group), "current": float(row["current"]), "previous": float(row["previous"])},
                    suggestion=f"Investigate {group}: review price, promotion, stock availability and demand before concluding a cause.",
                    scope=f"{dimension_role}:{group}",
                )
            )
        elif change >= 0.50 and row["current"] >= min_previous:
            alerts.append(
                Alert(
                    title=f"Unusual {metric_role} increase in {group}",
                    description=(
                        f"{group} {metric_role} rose {change:.1%} versus the previous comparable period. "
                        "This is a statistical observation, not proof of a cause."
                    ),
                    metric=metric_role,
                    severity="info",
                    current_value=float(row["current"]),
                    previous_value=float(row["previous"]),
                    pct_change=change,
                    comparison_period=period,
                    evidence={"dimension": dimension_role, "value": str(group), "current": float(row["current"]), "previous": float(row["previous"])},
                    suggestion=f"Check whether a promotion, one-off order or data change explains the increase in {group}.",
                    scope=f"{dimension_role}:{group}",
                )
            )
    return sorted(alerts, key=lambda alert: SEVERITY_ORDER.get(alert.severity, 9))[:top_n]


def detect_alerts(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    z_threshold: float = 3.0,
    decline_threshold: float = 0.15,
) -> list[Alert]:
    """Detect transparent, evidence-based alerts on the active dataset."""
    if frame is None or frame.empty:
        return []
    date_column = schema.role_column("date") or (schema.dates[0] if schema.dates else None)
    alerts: list[Alert] = []
    if not date_column:
        alerts.append(
            Alert(
                title="Time-based alerts unavailable",
                description="No date column is mapped, so period-over-period comparisons cannot be calculated.",
                metric="date",
                severity="info",
                comparison_period="Not available",
                suggestion="Map a date column in the column-mapping review to enable trend alerts.",
                scope="Data quality",
            )
        )
        return alerts
    bounds = _window_bounds(frame[date_column])
    if not bounds:
        return alerts
    last_start, last_end, prev_start, prev_end, period = bounds

    revenue = schema.role_column("revenue")
    profit = schema.role_column("profit")
    cost = schema.role_column("cost")
    quantity = schema.role_column("quantity")
    order = schema.role_column("order_id")
    customer = schema.role_column("customer")

    metrics = (
        ("revenue", revenue, 0.15, 0.30, "Review pricing, demand and data completeness before acting."),
        ("profit", profit, 0.20, 0.40, "Review margin drivers: price, discount, cost and product mix."),
        ("cost", cost, 0.20, 0.40, "Review the largest cost groups and compare them with budget."),
        ("quantity", quantity, 0.20, 0.40, "Check whether demand, stock availability or returns changed."),
    )
    for role, column, warning, critical, suggestion in metrics:
        if not column:
            continue
        current = _metric_sum(frame, column, last_start, last_end, date_column)
        previous = _metric_sum(frame, column, prev_start, prev_end, date_column)
        change = _pct(current, previous)
        if change is None:
            continue
        if change <= -warning:
            severity = _severity_from_change(change, warning, critical)
            _add(
                alerts,
                title=f"{role.title()} declined",
                description=(
                    f"Total {role} fell {abs(change):.1%} from {previous:,.2f} to {current:,.2f} "
                    "in the latest comparable period."
                ),
                metric=role,
                severity=severity,
                current=current,
                previous=previous,
                comparison=period,
                evidence={"current": current, "previous": previous, "change": change},
                suggestion=suggestion,
            )
        elif change >= 0.50:
            _add(
                alerts,
                title=f"Unusual {role} increase",
                description=(
                    f"Total {role} rose {change:.1%} from {previous:,.2f} to {current:,.2f}. "
                    "This is a statistical observation, not a causal explanation."
                ),
                metric=role,
                severity="info",
                current=current,
                previous=previous,
                comparison=period,
                evidence={"current": current, "previous": previous, "change": change},
                suggestion="Verify the increase against orders and check for one-off transactions or data changes.",
            )

    # Profit margin (percentage points, not percentage change).
    if revenue and profit:
        current_revenue = _metric_sum(frame, revenue, last_start, last_end, date_column)
        previous_revenue = _metric_sum(frame, revenue, prev_start, prev_end, date_column)
        current_profit = _metric_sum(frame, profit, last_start, last_end, date_column)
        previous_profit = _metric_sum(frame, profit, prev_start, prev_end, date_column)
        current_margin = current_profit / current_revenue if current_revenue else None
        previous_margin = previous_profit / previous_revenue if previous_revenue else None
        if current_margin is not None and previous_margin is not None:
            delta = current_margin - previous_margin
            if delta <= -0.10:
                severity = "critical"
            elif delta <= -0.05:
                severity = "warning"
            else:
                severity = None
            if severity:
                alerts.append(
                    Alert(
                        title="Profit margin dropped",
                        description=(
                            f"Profit margin moved from {previous_margin:.1%} to {current_margin:.1%} "
                            f"({delta * 100:+.1f} percentage points) in the latest comparable period."
                        ),
                        metric="profit_margin",
                        severity=severity,
                        current_value=current_margin,
                        previous_value=previous_margin,
                        pct_change=delta,
                        comparison_period=period,
                        evidence={"current_margin": current_margin, "previous_margin": previous_margin, "delta_points": delta * 100},
                        suggestion="Review discounting, product mix and cost changes; margin movement alone does not identify a cause.",
                    )
                )

    if order:
        current_orders = _metric_count(frame, order, last_start, last_end, date_column)
        previous_orders = _metric_count(frame, order, prev_start, prev_end, date_column)
        change = _pct(float(current_orders), float(previous_orders))
        if change is not None and change <= -decline_threshold:
            _add(
                alerts,
                title="Order volume declined",
                description=f"Orders fell {abs(change):.1%} from {previous_orders:,} to {current_orders:,}.",
                metric="orders",
                severity=_severity_from_change(change, decline_threshold, 0.30),
                current=float(current_orders),
                previous=float(previous_orders),
                comparison=period,
                evidence={"current": current_orders, "previous": previous_orders},
                suggestion="Check demand, stock availability and whether the comparison period contains one-off orders.",
            )
    if customer:
        current_customers = _metric_count(frame, customer, last_start, last_end, date_column)
        previous_customers = _metric_count(frame, customer, prev_start, prev_end, date_column)
        change = _pct(float(current_customers), float(previous_customers))
        if change is not None and change <= -0.20:
            _add(
                alerts,
                title="Active customers declined",
                description=f"Distinct active customers fell {abs(change):.1%} from {previous_customers:,} to {current_customers:,}.",
                metric="customers",
                severity=_severity_from_change(change, 0.20, 0.40),
                current=float(current_customers),
                previous=float(previous_customers),
                comparison=period,
                evidence={"current": current_customers, "previous": previous_customers},
                suggestion="Review acquisition, retention and the customer identifier's completeness.",
            )

    for role, warning, critical, minimum in (
        ("category", 0.20, 0.35, 1.0),
        ("product", 0.30, 0.45, 1.0),
        ("region", 0.20, 0.35, 1.0),
    ):
        alerts.extend(
            _group_changes(
                frame,
                schema,
                dimension_role=role,
                metric_role="revenue",
                bounds=bounds,
                min_previous=minimum,
                warning=warning,
                critical=critical,
            )
        )
    if not schema.role_column("region"):
        alerts.extend(
            _group_changes(
                frame,
                schema,
                dimension_role="city",
                metric_role="revenue",
                bounds=bounds,
                min_previous=1.0,
                warning=0.20,
                critical=0.35,
            )
        )

    # Statistical outliers (Z-score and IQR) on revenue and profit.
    for role in ("revenue", "profit"):
        column = schema.role_column(role)
        if not column:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if len(values) < 8:
            continue
        mean, std = float(values.mean()), float(values.std(ddof=1))
        if std > 0:
            z_scores = (values - mean) / std
            z_count = int((z_scores.abs() > z_threshold).sum())
            max_z = float(z_scores.abs().max())
            if z_count:
                alerts.append(
                    Alert(
                        title=f"{role.title()} outliers detected",
                        description=(
                            f"{z_count:,} row(s) have |z| > {z_threshold:g} for {role}; "
                            f"the largest absolute z-score is {max_z:.2f}."
                        ),
                        metric=f"{role}_outliers",
                        severity="info",
                        current_value=float(z_count),
                        previous_value=float(len(values)),
                        comparison_period="Whole active dataset",
                        evidence={"method": "z-score", "threshold": z_threshold, "count": z_count, "max_abs_z": max_z},
                        suggestion="Review the flagged rows for data-entry errors or one-off transactions before removing anything.",
                    )
                )
        q1, q3 = float(values.quantile(0.25)), float(values.quantile(0.75))
        iqr = q3 - q1
        if iqr > 0:
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            iqr_count = int(((values < lower) | (values > upper)).sum())
            if iqr_count:
                alerts.append(
                    Alert(
                        title=f"{role.title()} IQR outliers",
                        description=(
                            f"{iqr_count:,} row(s) fall outside the 1.5×IQR fence "
                            f"[{lower:,.2f}, {upper:,.2f}] for {role}."
                        ),
                        metric=f"{role}_iqr_outliers",
                        severity="info",
                        current_value=float(iqr_count),
                        previous_value=float(len(values)),
                        comparison_period="Whole active dataset",
                        evidence={"method": "IQR", "lower": lower, "upper": upper, "count": iqr_count},
                        suggestion="Inspect the outliers; IQR flags unusual values, not errors.",
                    )
                )

    # Rolling-average movement for revenue when enough daily observations exist.
    if revenue:
        dates = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
        daily = (
            pd.DataFrame({"date": dates, "value": pd.to_numeric(frame[revenue], errors="coerce")})
            .dropna()
            .groupby("date")["value"]
            .sum()
            .sort_index()
        )
        if len(daily) >= 14:
            recent = float(daily.tail(7).mean())
            prior = float(daily.tail(14).head(7).mean())
            change = _pct(recent, prior)
            if change is not None and abs(change) >= 0.20:
                _add(
                    alerts,
                    title="Revenue rolling average moved",
                    description=(
                        f"The latest 7-day average revenue is {recent:,.2f}, "
                        f"{change:+.1%} versus the preceding 7-day average ({prior:,.2f})."
                    ),
                    metric="revenue_rolling_average",
                    severity=_severity_from_change(change, 0.20, 0.35) if change < 0 else "info",
                    current=recent,
                    previous=prior,
                    comparison="Last 7 days vs preceding 7 days",
                    evidence={"recent_7d_avg": recent, "prior_7d_avg": prior},
                    suggestion="Compare the two weeks for promotions, holidays, stock-outs or data gaps.",
                )

    # Seasonal comparison when at least two years of monthly history exist.
    if revenue:
        dates = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
        monthly = (
            pd.DataFrame({"date": dates, "value": pd.to_numeric(frame[revenue], errors="coerce")})
            .dropna()
            .assign(month=lambda data: data["date"].dt.to_period("M"))
            .groupby("month")["value"]
            .sum()
            .sort_index()
        )
        if len(monthly) >= 24:
            latest_month = monthly.index[-1]
            same_month_last_year = latest_month - 12
            if same_month_last_year in monthly.index:
                current = float(monthly.loc[latest_month])
                previous = float(monthly.loc[same_month_last_year])
                change = _pct(current, previous)
                if change is not None and abs(change) >= 0.25:
                    _add(
                        alerts,
                        title="Seasonal revenue comparison",
                        description=(
                            f"Revenue in {latest_month} is {current:,.2f}, {change:+.1%} versus "
                            f"the same month last year ({previous:,.2f})."
                        ),
                        metric="revenue_seasonal",
                        severity=_severity_from_change(change, 0.25, 0.40) if change < 0 else "info",
                        current=current,
                        previous=previous,
                        comparison=f"{latest_month} vs {same_month_last_year}",
                        evidence={"latest_month": str(latest_month), "previous_year_month": str(same_month_last_year)},
                        suggestion="Compare seasonality, pricing and promotion calendars before drawing conclusions.",
                    )

    unique: dict[str, Alert] = {}
    for alert in alerts:
        unique.setdefault(alert.fingerprint, alert)
    return sorted(unique.values(), key=lambda alert: (SEVERITY_ORDER.get(alert.severity, 9), alert.title))


def merge_alerts(existing: Iterable[Alert], new_alerts: Iterable[Alert]) -> list[Alert]:
    """Merge a refresh into history without duplicating or losing acknowledgements."""
    merged: dict[str, Alert] = {alert.fingerprint: alert for alert in existing}
    for alert in new_alerts:
        previous = merged.get(alert.fingerprint)
        if previous is None:
            merged[alert.fingerprint] = alert
            continue
        # Keep the original identity/status/timestamp; refresh the measurements.
        previous.description = alert.description
        previous.current_value = alert.current_value
        previous.previous_value = alert.previous_value
        previous.pct_change = alert.pct_change
        previous.evidence = alert.evidence
        previous.severity = alert.severity
        previous.comparison_period = alert.comparison_period
    return sorted(merged.values(), key=lambda alert: (SEVERITY_ORDER.get(alert.severity, 9), alert.title))


def acknowledge(alert: Alert) -> Alert:
    alert.status = "acknowledged"
    alert.acknowledged_at = _now()
    return alert


def dismiss(alert: Alert) -> Alert:
    alert.status = "dismissed"
    alert.acknowledged_at = _now()
    return alert


def filter_alerts(alerts: Iterable[Alert], *, severity: str | None = None, status: str | None = None) -> list[Alert]:
    result = list(alerts)
    if severity and severity in SEVERITIES:
        result = [alert for alert in result if alert.severity == severity]
    if status and status in STATUSES:
        result = [alert for alert in result if alert.status == status]
    return result


def alerts_csv_bytes(alerts: Iterable[Alert]) -> bytes:
    rows = [
        {
            "id": alert.id,
            "severity": alert.severity,
            "status": alert.status,
            "title": alert.title,
            "description": alert.description,
            "metric": alert.metric,
            "scope": alert.scope,
            "current_value": alert.current_value,
            "previous_value": alert.previous_value,
            "pct_change": alert.pct_change,
            "comparison_period": alert.comparison_period,
            "suggestion": alert.suggestion,
            "detected_at": alert.detected_at,
            "acknowledged_at": alert.acknowledged_at,
        }
        for alert in alerts
    ]
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@dataclass
class NotificationPreferences:
    min_severity: str = "warning"
    email_enabled: bool = False
    recipients: tuple[str, ...] = ()
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    sender: str | None = None
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> "NotificationPreferences":
        recipients = tuple(
            address.strip()
            for address in os.environ.get("RETAILMIND_ALERT_EMAIL_TO", "").split(",")
            if address.strip()
        )
        return cls(
            min_severity=os.environ.get("RETAILMIND_ALERT_MIN_SEVERITY", "warning"),
            email_enabled=os.environ.get("RETAILMIND_ALERT_EMAIL_ENABLED", "0").lower() in {"1", "true", "yes"},
            recipients=recipients,
            smtp_host=os.environ.get("RETAILMIND_SMTP_HOST"),
            smtp_port=int(os.environ.get("RETAILMIND_SMTP_PORT", "587") or 587),
            smtp_user=os.environ.get("RETAILMIND_SMTP_USER"),
            smtp_password=os.environ.get("RETAILMIND_SMTP_PASSWORD"),
            sender=os.environ.get("RETAILMIND_SMTP_FROM") or os.environ.get("RETAILMIND_SMTP_USER"),
        )

    def configured(self) -> bool:
        return bool(self.email_enabled and self.recipients and self.smtp_host and self.sender)


@dataclass
class Notification:
    alert_id: str
    title: str
    message: str
    severity: str
    fingerprint: str
    created_at: str = field(default_factory=_now)
    read: bool = False
    email_status: str = "not_requested"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_notifications(
    alerts: Iterable[Alert],
    preferences: NotificationPreferences,
    existing: Iterable[Notification] = (),
) -> list[Notification]:
    threshold = SEVERITY_ORDER.get(preferences.min_severity, 1)
    known = {notification.fingerprint: notification for notification in existing}
    result: list[Notification] = []
    for alert in alerts:
        if SEVERITY_ORDER.get(alert.severity, 9) > threshold:
            continue
        if alert.status == "dismissed":
            continue
        fingerprint = f"{alert.fingerprint}:{preferences.min_severity}"
        notification = known.get(fingerprint)
        if notification is None:
            notification = Notification(
                alert_id=alert.id,
                title=alert.title,
                message=alert.description,
                severity=alert.severity,
                fingerprint=fingerprint,
            )
        result.append(notification)
    return result


def send_email_notification(notification: Notification, preferences: NotificationPreferences) -> str:
    """Attempt one email and return a truthful delivery status.

    "accepted_by_smtp" means the SMTP server accepted the message; it is not a
    guarantee of inbox delivery.  No email is attempted unless the environment
    explicitly enables it and all SMTP settings are present.
    """
    if not preferences.email_enabled:
        return "disabled"
    if not preferences.configured():
        return "not_configured"
    message = EmailMessage()
    message["Subject"] = f"[RetailMind AI] {notification.severity.upper()}: {notification.title}"
    message["From"] = preferences.sender or ""
    message["To"] = ", ".join(preferences.recipients)
    message.set_content(notification.message)
    try:
        with smtplib.SMTP(preferences.smtp_host or "", preferences.smtp_port, timeout=15) as client:
            if preferences.use_tls:
                client.starttls()
            if preferences.smtp_user and preferences.smtp_password:
                client.login(preferences.smtp_user, preferences.smtp_password)
            client.send_message(message)
        return "accepted_by_smtp"
    except Exception as error:  # never claim delivery on failure
        return f"failed: {type(error).__name__}: {error}"
