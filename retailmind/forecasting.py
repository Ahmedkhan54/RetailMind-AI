"""Sales, profit and demand forecasting with honest metrics.

Supported methods are intentionally small and dependency-light:

* moving average
* simple exponential smoothing (alpha selected on a time-ordered split)
* linear trend regression (NumPy least squares)
* ARIMA/SARIMA only when ``statsmodels`` is installed; otherwise the method is
  reported as unavailable rather than silently replaced.

Every evaluation uses a time-based split (the last 20% is never used for
fitting), so there is no random leakage.  Prediction intervals are derived from
in-sample residual dispersion and are labelled as approximate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import math
from typing import Any

import numpy as np
import pandas as pd

from retailmind.schema import DatasetSchema


FREQUENCIES = {
    "Daily": "D",
    "Weekly": "W-MON",
    "Monthly": "MS",
}
METHODS = ("Auto (backtest)", "Moving average", "Exponential smoothing", "Linear trend", "ARIMA / SARIMA")


@dataclass
class ForecastResult:
    available: bool
    metric: str = ""
    frequency: str = "D"
    method: str = "auto"
    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    forecast: pd.DataFrame = field(default_factory=pd.DataFrame)
    metrics: dict[str, float | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    train_size: int = 0
    test_size: int = 0
    dimension: str | None = None
    dimension_value: str | None = None

    def to_csv_bytes(self) -> bytes:
        return self.forecast.to_csv(index=False).encode("utf-8-sig")

    def to_excel_bytes(self) -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            self.forecast.to_excel(writer, sheet_name="Forecast", index=False)
            if not self.history.empty:
                self.history.to_excel(writer, sheet_name="History", index=False)
            metrics = pd.DataFrame(
                [{"metric": key, "value": value} for key, value in self.metrics.items()]
            )
            metrics.to_excel(writer, sheet_name="Model Metrics", index=False)
        return output.getvalue()


def _metric_column(frame: pd.DataFrame, schema: DatasetSchema, metric_role: str) -> str | None:
    if metric_role in {"revenue", "profit", "cost", "quantity"}:
        return schema.role_column(metric_role)
    return metric_role if metric_role in frame.columns else None


def _dimension_column(frame: pd.DataFrame, schema: DatasetSchema, dimension_role: str | None) -> str | None:
    if not dimension_role:
        return None
    if dimension_role in {"product", "category", "region", "city", "store", "customer", "sales_rep"}:
        return schema.role_column(dimension_role)
    return dimension_role if dimension_role in frame.columns else None


def prepare_series(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    metric_role: str,
    *,
    frequency: str = "D",
    dimension_role: str | None = None,
    dimension_value: str | None = None,
    date_column: str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Aggregate the requested metric into a complete, regular time series."""
    notes: list[str] = []
    metric = _metric_column(frame, schema, metric_role)
    date = date_column or schema.role_column("date") or (schema.dates[0] if schema.dates else None)
    if not metric:
        return pd.DataFrame(), [f"No column is mapped to '{metric_role}'. Map it before forecasting."]
    if not date:
        return pd.DataFrame(), ["Forecasting needs a date column. Map one in the column-mapping review."]
    working = pd.DataFrame(
        {
            "ds": pd.to_datetime(frame[date], format="mixed", errors="coerce"),
            "y": pd.to_numeric(frame[metric], errors="coerce"),
        }
    )
    if dimension_role and dimension_value is not None:
        dimension = _dimension_column(frame, schema, dimension_role)
        if not dimension:
            return pd.DataFrame(), [f"Dimension '{dimension_role}' is not available in this dataset."]
        working = working[frame[dimension].astype("string") == str(dimension_value)]
    working = working.dropna(subset=["ds", "y"]).sort_values("ds")
    if working.empty:
        return pd.DataFrame(), ["No valid rows remain after removing missing dates and values."]
    if frequency not in FREQUENCIES:
        frequency = "D"
    rule = FREQUENCIES[frequency]
    series = working.set_index("ds")["y"].resample(rule).sum().reset_index()
    if series["ds"].dt.tz is not None:
        series["ds"] = series["ds"].dt.tz_localize(None)
    # A regular calendar is required for a fair time-series split.  Missing
    # periods are zero sales/demand, not fabricated observations.
    if series["ds"].duplicated().any():
        series = series.groupby("ds", as_index=False)["y"].sum()
    return series, notes


def _moving_average_forecast(y: np.ndarray, horizon: int, window: int = 7) -> tuple[np.ndarray, np.ndarray]:
    window = max(2, min(window, len(y)))
    base = float(np.mean(y[-window:]))
    forecast = np.repeat(base, horizon)
    residuals = np.array([y[i] - np.mean(y[max(0, i - window):i]) for i in range(window, len(y))])
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(y, ddof=1))
    return forecast, np.repeat(sigma, horizon)


def _exponential_smoothing(y: np.ndarray, horizon: int, alpha: float | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    if alpha is None:
        best_alpha, best_sse = 0.3, math.inf
        for candidate in np.linspace(0.05, 0.95, 19):
            fitted = _es_fitted(y, float(candidate))
            sse = float(np.nansum((y - fitted) ** 2))
            if sse < best_sse:
                best_alpha, best_sse = float(candidate), sse
        alpha = best_alpha
    fitted = _es_fitted(y, alpha)
    residuals = y - fitted
    sigma = float(np.nanstd(residuals, ddof=1)) if len(y) > 2 else float(np.nanstd(y))
    level = fitted[-1] if len(fitted) else float(y[-1])
    return np.repeat(level, horizon), np.repeat(sigma, horizon), alpha


def _es_fitted(y: np.ndarray, alpha: float) -> np.ndarray:
    fitted = np.empty(len(y), dtype=float)
    fitted[0] = y[0]
    for index in range(1, len(y)):
        fitted[index] = alpha * y[index - 1] + (1 - alpha) * fitted[index - 1]
    return fitted


def _linear_forecast(y: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    x = np.arange(len(y), dtype=float)
    if len(y) < 2:
        return np.repeat(float(y[-1]), horizon), np.repeat(0.0, horizon)
    slope, intercept = np.polyfit(x, y, 1)
    future_x = np.arange(len(y), len(y) + horizon, dtype=float)
    forecast = slope * future_x + intercept
    fitted = slope * x + intercept
    residuals = y - fitted
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0
    return forecast, np.repeat(sigma, horizon)


def _arima_forecast(y: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray] | None:
    try:  # optional dependency; never silently replaced
        from statsmodels.tsa.arima.model import ARIMA  # type: ignore
    except Exception:
        return None
    try:
        model = ARIMA(y, order=(1, 1, 1)).fit()
        result = model.get_forecast(steps=horizon)
        mean = np.asarray(result.predicted_mean, dtype=float)
        sigma = float(np.sqrt(np.nanmean(np.asarray(model.resid, dtype=float) ** 2)))
        return mean, np.repeat(sigma, horizon)
    except Exception:
        return None


def _fit_forecast(y: np.ndarray, horizon: int, method: str) -> tuple[np.ndarray, np.ndarray, str, list[str]]:
    notes: list[str] = []
    if method == "Moving average":
        forecast, sigma = _moving_average_forecast(y, horizon)
        return forecast, sigma, "Moving average", notes
    if method == "Exponential smoothing":
        forecast, sigma, alpha = _exponential_smoothing(y, horizon)
        notes.append(f"Exponential smoothing alpha={alpha:.2f}.")
        return forecast, sigma, "Exponential smoothing", notes
    if method == "Linear trend":
        forecast, sigma = _linear_forecast(y, horizon)
        return forecast, sigma, "Linear trend", notes
    if method == "ARIMA / SARIMA":
        result = _arima_forecast(y, horizon)
        if result is None:
            return np.array([]), np.array([]), "ARIMA / SARIMA", [
                "ARIMA/SARIMA requires the optional 'statsmodels' package, which is not installed. "
                "Choose Auto, Moving average, Exponential smoothing or Linear trend."
            ]
        return result[0], result[1], "ARIMA / SARIMA", notes
    # Auto: backtest each available deterministic method and keep the best MAE.
    candidates = ["Moving average", "Exponential smoothing", "Linear trend"]
    best: tuple[float, str, np.ndarray, np.ndarray] | None = None
    for candidate in candidates:
        fc, sigma, _label, _notes = _fit_forecast(y, horizon, candidate)
        if not len(fc):
            continue
        mae = float(np.mean(np.abs(fc - y[-horizon:]))) if len(fc) == horizon else math.inf
        if best is None or mae < best[0]:
            best = (mae, candidate, fc, sigma)
    if best is None:
        forecast, sigma = _moving_average_forecast(y, horizon)
        return forecast, sigma, "Moving average", notes
    notes.append(f"Auto selected {best[1]} on the hold-out period.")
    return best[2], best[3], best[1], notes


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if len(actual) != len(predicted) or not len(actual):
        return {"mae": None, "rmse": None, "mape": None}
    errors = actual - predicted
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    non_zero = actual != 0
    mape = float(np.mean(np.abs(errors[non_zero] / actual[non_zero])) * 100) if non_zero.any() else None
    return {"mae": mae, "rmse": rmse, "mape": mape}


def _future_dates(last_date: pd.Timestamp, frequency: str, horizon: int) -> pd.DatetimeIndex:
    rule = frequency if frequency in {"D", "W-MON", "MS"} else FREQUENCIES.get(frequency, "D")
    return pd.date_range(last_date, periods=horizon + 1, freq=rule)[1:]


def forecast_series(
    series: pd.DataFrame,
    *,
    metric: str,
    frequency: str = "D",
    periods: int = 14,
    method: str = "Auto (backtest)",
    dimension: str | None = None,
    dimension_value: str | None = None,
) -> ForecastResult:
    """Forecast a prepared ``ds``/``y`` series with a time-based evaluation."""
    periods = max(1, min(int(periods), 365))
    if series.empty:
        return ForecastResult(available=False, metric=metric, frequency=frequency, method=method)
    series = series.dropna(subset=["ds", "y"]).sort_values("ds").reset_index(drop=True)
    minimum = 8 if frequency == "D" else 6 if frequency == "W" else 4
    if len(series) < minimum:
        return ForecastResult(
            available=False,
            metric=metric,
            frequency=frequency,
            method=method,
            history=series.rename(columns={"ds": "date", "y": "actual"}),
            notes=[
                f"Only {len(series)} {frequency.lower()} observations are available; at least {minimum} are "
                "required for a defensible forecast. Upload a longer history or use a coarser frequency."
            ],
        )
    y = series["y"].to_numpy(dtype=float)
    test_size = max(2, int(round(len(y) * 0.2)))
    test_size = min(test_size, len(y) - 3)
    train, test = y[:-test_size], y[-test_size:]
    evaluation_forecast, _sigma, selected, notes = _fit_forecast(train, test_size, method)
    if not len(evaluation_forecast):
        return ForecastResult(
            available=False,
            metric=metric,
            frequency=frequency,
            method=method,
            history=series.rename(columns={"ds": "date", "y": "actual"}),
            notes=notes,
        )
    metrics = _metrics(test, evaluation_forecast)
    # Refit on all observations for the future forecast.
    future_forecast, sigma, selected, refit_notes = _fit_forecast(y, periods, selected)
    if not len(future_forecast):
        return ForecastResult(
            available=False,
            metric=metric,
            frequency=frequency,
            method=selected,
            history=series.rename(columns={"ds": "date", "y": "actual"}),
            notes=notes + refit_notes,
        )
    notes.extend(refit_notes)
    future_dates = _future_dates(series["ds"].iloc[-1], frequency, periods)
    interval = 1.96 * np.asarray(sigma, dtype=float)
    forecast = pd.DataFrame(
        {
            "date": future_dates,
            "forecast": np.asarray(future_forecast, dtype=float),
            "lower_bound": np.asarray(future_forecast, dtype=float) - interval,
            "upper_bound": np.asarray(future_forecast, dtype=float) + interval,
        }
    )
    forecast["lower_bound"] = forecast["lower_bound"].clip(lower=0)
    forecast["upper_bound"] = forecast["upper_bound"].clip(lower=0)
    history = series.rename(columns={"ds": "date", "y": "actual"})
    notes.append(
        "Prediction intervals are approximate (±1.96 × residual standard deviation) and widen "
        "only through the residual estimate; they are not a guarantee."
    )
    return ForecastResult(
        available=True,
        metric=metric,
        frequency=frequency,
        method=selected,
        history=history,
        forecast=forecast,
        metrics=metrics,
        notes=notes,
        train_size=len(train),
        test_size=len(test),
        dimension=dimension,
        dimension_value=dimension_value,
    )


def forecast_dataset(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    metric_role: str = "revenue",
    frequency: str = "Daily",
    periods: int = 14,
    method: str = "Auto (backtest)",
    dimension_role: str | None = None,
    dimension_value: str | None = None,
) -> ForecastResult:
    series, notes = prepare_series(
        frame,
        schema,
        metric_role,
        frequency=frequency,
        dimension_role=dimension_role,
        dimension_value=dimension_value,
    )
    if series.empty:
        return ForecastResult(
            available=False,
            metric=metric_role,
            frequency=FREQUENCIES.get(frequency, "D"),
            method=method,
            notes=notes,
            dimension=dimension_role,
            dimension_value=dimension_value,
        )
    result = forecast_series(
        series,
        metric=metric_role,
        frequency=FREQUENCIES.get(frequency, "D"),
        periods=periods,
        method=method,
        dimension=dimension_role,
        dimension_value=dimension_value,
    )
    result.notes = notes + result.notes
    return result


def available_dimension_values(frame: pd.DataFrame, schema: DatasetSchema, dimension_role: str) -> list[str]:
    column = _dimension_column(frame, schema, dimension_role)
    if not column:
        return []
    values = frame[column].dropna().astype("string").unique().tolist()
    return sorted(str(value) for value in values)[:500]
