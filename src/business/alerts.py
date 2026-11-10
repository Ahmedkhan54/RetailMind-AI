"""Evidence-based alerts with explicit insufficient-data results."""
from __future__ import annotations
import pandas as pd


def business_alerts(frame: pd.DataFrame, *, sales_decline_pct: float = 10, low_margin_pct: float = 10, low_product_margin_pct: float = 5, high_profit_share_pct: float = 35) -> list[dict]:
    work = frame.copy(); work["order_date"] = pd.to_datetime(work["order_date"], errors="coerce")
    work = work.dropna(subset=["order_date"])
    if work.empty or work["order_date"].dt.to_period("M").nunique() < 2:
        return [{"level": "info", "title": "Insufficient data", "detail": "At least two months of dated uploaded data are required for period-comparison alerts."}]
    monthly = work.groupby(work["order_date"].dt.to_period("M"), observed=True).agg(sales=("sales", "sum"), profit=("profit", "sum")).sort_index()
    current, previous = monthly.iloc[-1], monthly.iloc[-2]
    alerts: list[dict] = []
    sales_change = ((current.sales - previous.sales) / previous.sales * 100) if previous.sales else 0
    if sales_change <= -abs(sales_decline_pct): alerts.append({"level": "warning", "title": "Sales decline", "detail": f"Sales changed {sales_change:.1f}% versus the prior month (threshold −{sales_decline_pct:.1f}%)."})
    margin = current.profit / current.sales * 100 if current.sales else 0
    if margin < low_margin_pct: alerts.append({"level": "warning", "title": "Low profit margin", "detail": f"Latest monthly margin is {margin:.1f}% (threshold {low_margin_pct:.1f}%)."})
    category_monthly = work.groupby([work["order_date"].dt.to_period("M"), "category"], observed=True)["sales"].sum().unstack(fill_value=0).sort_index()
    if len(category_monthly) >= 2:
        declines = []
        for category in category_monthly.columns:
            previous_value, current_value = category_monthly[category].iloc[-2:].tolist()
            if previous_value and (current_value - previous_value) / previous_value * 100 <= -abs(sales_decline_pct):
                declines.append(str(category))
        if declines: alerts.append({"level": "warning", "title": "Declining category performance", "detail": f"{', '.join(declines[:3])} declined by at least {sales_decline_pct:.1f}% versus the prior month."})
    city_monthly = work.groupby([work["order_date"].dt.to_period("M"), "city"], observed=True)["profit"].sum().unstack(fill_value=0).sort_index()
    if len(city_monthly) >= 2:
        improving = []
        for city in city_monthly.columns:
            previous_value, current_value = city_monthly[city].iloc[-2:].tolist()
            if previous_value > 0 and (current_value - previous_value) / previous_value * 100 >= abs(sales_decline_pct): improving.append(str(city))
        if improving: alerts.append({"level": "success", "title": "Improving city performance", "detail": f"{', '.join(improving[:3])} profit improved by at least {sales_decline_pct:.1f}% versus the prior month."})
    products = work.groupby("product_name", observed=True).agg(sales=("sales", "sum"), profit=("profit", "sum"))
    low_products = products[(products.sales > 0) & (products.profit / products.sales * 100 < low_product_margin_pct)]
    if not low_products.empty: alerts.append({"level": "warning", "title": "Low product profitability", "detail": f"{len(low_products)} product(s) are below the {low_product_margin_pct:.1f}% margin threshold."})
    profit_by_city = work.groupby("city", observed=True)["profit"].sum()
    if profit_by_city.sum() > 0:
        city, value = profit_by_city.idxmax(), profit_by_city.max()
        share = value / profit_by_city.sum() * 100
        if share >= high_profit_share_pct: alerts.append({"level": "success", "title": "High profit contribution", "detail": f"{city} contributes {share:.1f}% of uploaded-data profit (threshold {high_profit_share_pct:.1f}%)."})
    return alerts or [{"level": "info", "title": "No threshold alerts", "detail": "Current uploaded data did not meet any configured alert threshold."}]
