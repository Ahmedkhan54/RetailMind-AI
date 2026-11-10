"""Goal calculations; persistence is deliberately separate and user-scoped."""
from __future__ import annotations
import pandas as pd


def goal_progress(goal: dict, frame: pd.DataFrame) -> dict:
    """Calculate a goal only from the active uploaded frame and its period."""
    work = frame.copy()
    dates = pd.to_datetime(work["order_date"], errors="coerce")
    mask = dates.between(pd.Timestamp(goal["period_start"]), pd.Timestamp(goal["period_end"]))
    if goal.get("target_category"):
        mask &= work["category"].eq(goal["target_category"])
    scoped = work.loc[mask]
    actual_sales = float(scoped["sales"].sum())
    actual_profit = float(scoped["profit"].sum())
    def measure(actual: float, target: object) -> dict | None:
        if target is None: return None
        target_value = float(target)
        return {"target": target_value, "actual": actual, "achievement_pct": (actual / target_value * 100) if target_value else 0.0, "remaining": max(0.0, target_value - actual)}
    return {"id": goal.get("id"), "name": goal["goal_name"], "category": goal.get("target_category"), "sales": measure(actual_sales, goal["target_sales"]), "profit": measure(actual_profit, goal.get("target_profit"))}
