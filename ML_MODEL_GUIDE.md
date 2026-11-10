# RetailMind AI — Machine Learning & Statistical Model Guide

**Version:** 2.0.0-phase2
**Verified against:** `retailmind/segmentation.py`, `retailmind/inventory.py`, `retailmind/forecasting.py`, `retailmind/alerts.py`
**Audit date:** 8 November 2026

> This guide describes what the code actually does. Where the earlier documentation described Holt-Winters, growing prediction intervals, or an “Overstocked” status, those descriptions were inaccurate and have been corrected here.

---

## 1. Customer segmentation (RFM + K-Means)

### 1.1 Required columns
Segmentation runs only when the schema provides:
- a customer identifier,
- a date,
- revenue **or** quantity + unit price.

Otherwise the result is `available=False` with a note naming the missing columns.

### 1.2 RFM definitions
With `snapshot = max(order_date) + 1 day`:

| Feature | Formula |
|:---|:---|
| Recency | `(snapshot − max(customer order date)).days` |
| Frequency | `nunique(order_id)` for that customer (rows are treated as orders if no order ID is mapped) |
| Monetary | `sum(revenue)` for that customer (or `sum(quantity × unit_price)`) |

Derived fields: `avg_purchase_value = monetary / frequency`, `tenure_days = last_purchase − first_purchase`, `total_orders = frequency`.

### 1.3 Preprocessing
1. `log1p` on recency, frequency and monetary.
2. Standardise each feature: `(x − mean) / std`, with `std` replaced by `1.0` when zero.

### 1.4 Clustering
- NumPy K-Means with **K-Means++** seeding.
- `n_init = 10`, `max_iter = 150`, fixed seed **42** → deterministic.
- Empty clusters are repaired by splitting the largest cluster.
- `k` candidates are `2 … max_clusters`; the candidate with the **highest silhouette score** wins.
- Silhouette is computed on a deterministic sample of at most **1,500** customers (`seed=42`), avoiding O(n²) memory.
- If fewer than 2 customers exist, segmentation is unavailable.

### 1.5 Behavioural labels
Cluster numbers are never used as labels. Each cluster is scored relative to the others using normalised recency (`r_score`, higher = more recent), frequency (`f_score`) and monetary value (`m_score`). Labels are assigned in this order:

| Label | Rule (on cluster profile) |
|:---|:---|
| Big Spenders | `m_score ≥ 0.75` |
| Loyal Customers | `f_score ≥ 0.6` and `r_score ≥ 0.4` |
| New Customers | `r_score ≥ 0.7` and `f_score ≤ 0.45` |
| Potential Loyalists | `r_score ≥ 0.5` and `f_score ≥ 0.35` |
| At-Risk Customers | `r_score ≤ 0.45` and (`m_score ≥ 0.4` or `f_score ≥ 0.4`) |
| Churn Risk Customers | all remaining clusters |

### 1.6 Rule-based churn flag (not a predictive model)
```
High rule-based risk : recency > 2 × median(recency) AND frequency ≤ median(frequency)
Monitor              : recency > median(recency)
Low rule-based risk  : otherwise
```
This is a transparent rule, **not** a trained future-churn probability. The app labels it as such.

### 1.7 Verified example
On a 3,000-row retail dataset: `k=2`, silhouette `0.3475`, 60 customers, independently recomputed RFM matched to **0.0000** difference.

---

## 2. Predictive stock recommendations

### 2.1 Required data
- Product identifier and date.
- Quantity (or a metric usable as demand).
- Stock column optional: without it, demand/ROP/safety stock are still computed, but days-remaining, depletion date and suggested quantity are left blank with an explanatory note.
- Optional columns: lead time, safety stock, incoming orders.

### 2.2 Demand estimates
- `avg_daily_sales`: mean daily quantity over the full product history.
- `recent_daily_demand`: mean over the last `max(7, history_window)` days (default window 28).
- `forecast_daily_demand`: the demand estimate used for planning.
- `std_daily`: standard deviation of recent daily demand (`ddof=1`).

### 2.3 Safety stock
```
if a safety-stock column is mapped:
    SS = that value
elif std_daily > 0:
    SS = Z × std_daily × sqrt(lead_time)
else:
    SS = forecast_daily × safety_days      # zero-variance fallback
```
`Z` values: 90% = 1.2816, 95% = 1.6449, 98% = 2.0537, 99% = 2.3263.

> The earlier guide claimed `SS = Z·σ·√L` unconditionally. That is only true when demand variability exists. With constant demand, the app deliberately falls back to a days-of-cover buffer rather than reporting zero safety stock.

### 2.4 Reorder point and suggested order
```
Lead-time demand = forecast_daily × lead_time
ROP              = Lead-time demand + SS
Target level     = ROP + forecast_daily × target_cover_days
Suggested order  = max(0, Target level − (current_stock + incoming_orders))
```

### 2.5 Status classification (actual)
| Status | Condition |
|:---|:---|
| Stock data required | No stock column/value |
| Out of stock | `stock ≤ 0` |
| Critical — reorder now | `days_remaining ≤ lead_time` |
| Low — reorder soon | `stock ≤ ROP` |
| Healthy | otherwise |

There is **no** “Overstocked” status in the current code.

### 2.6 Verified example
Constant demand 10/day, stock 200, lead 7, safety 7 days, 95% service:
`avg_daily=10`, `safety=70`, `ROP=140`, `suggested=80`, `days_remaining=20`, status `Healthy`.

---

## 3. Sales & profit forecasting

### 3.1 Data preparation
- Dates parsed with `format="mixed"` and coerced; invalid rows dropped.
- Values coerced numeric; missing rows dropped.
- Aggregation: Daily (`D`), Weekly (`W-MON`), Monthly (`MS`), summing the metric within each period.
- Optional dimension filter (e.g. one category/product).

### 3.2 Minimum history
| Frequency | Minimum observations |
|:---|:---:|
| Daily | 8 |
| Weekly | 6 |
| Monthly | 4 |

Below the minimum, the result is `available=False` with a clear note. No forecast is fabricated.

### 3.3 Evaluation protocol
- Time-ordered split: last `max(2, round(20% × n))` observations are held out (capped at `n − 3`).
- The model is fitted on the training portion and evaluated on the hold-out.
- It is then **refitted on the full series** to produce the future forecast.
- No random shuffling → no leakage.

### 3.4 Implemented methods
1. **Moving average** — mean of the last window (`window = max(2, min(7, len(y)))`), projected flat. Residual σ from rolling errors.
2. **Simple exponential smoothing** — `level_t = α·y_{t−1} + (1−α)·level_{t−1}`. α is grid-searched over `linspace(0.05, 0.95, 19)` by in-sample SSE. Forecast is the final level, repeated. **No trend/seasonal (Holt/Holt-Winters) term exists.**
3. **Linear trend** — ordinary least squares `y = slope·t + intercept` via NumPy, projected forward.
4. **ARIMA / SARIMA** — only if `statsmodels` is installed. Otherwise the method returns `available=False` with an explicit “optional package missing” note.
5. **Auto (backtest)** — evaluates moving average, exponential smoothing and linear trend on the hold-out and keeps the **lowest MAE**.

### 3.5 Metrics
```
MAE  = mean(|y − ŷ|)
RMSE = sqrt(mean((y − ŷ)²))
MAPE = mean(|y − ŷ| / |y|) × 100   (zero actuals excluded)
```
These definitions were independently verified against hand calculations (`[10,20]` vs `[8,25]` → MAE 3.5, RMSE √14.5, MAPE 17.5%).

### 3.6 Prediction intervals
```
lower = max(0, forecast − 1.96 × σ_residual)
upper = forecast + 1.96 × σ_residual
```
The interval width is **constant across the horizon**; it does not grow with `sqrt(h)`. The app’s notes label the intervals as approximate.

### 3.7 Verified example
3,000-row monthly retail series, auto-selected linear trend: `MAE=12,578.91`, `RMSE=12,733.97`, `MAPE=9.75`.

---

## 4. Anomaly and alert detection

`detect_alerts` is rule/statistics based, not a trained anomaly model:

- Period-over-period changes with configurable decline threshold (default 15%).
- Z-score outliers (default threshold 3.0).
- Margin/profit deterioration, expense surges, and stock-out conditions where the required columns exist.
- Group-level changes (e.g. by region/category).
- Every alert carries a title, description, metric, severity, comparison period, scope, and suggestion.
- Alerts are deduplicated by fingerprint with `merge_alerts`; lifecycle states are `new`, `acknowledged`, `dismissed`.

Alerts are deterministic and recomputed from the active filtered frame.

---

## 5. Known limitations

1. **No trained churn classifier** — the churn flag is a rule.
2. **No seasonal model** — exponential smoothing is level-only.
3. **Intervals are approximate and constant-width.**
4. **ARIMA requires an optional package** not installed in this environment.
5. **Inventory formulas assume independent daily demand**; they do not model promotions or correlated SKUs.
6. **Silhouette is sampled** above 1,500 customers for tractability.
7. **K-Means assumes spherical clusters** after log/standard scaling; it is not a guarantee of business-meaningful segments.

---

## 6. Reproduce the checks

```powershell
.\.venv\Scripts\python.exe audit_functional.py   # RFM, inventory, forecasting, metrics
.\.venv\Scripts\python.exe audit_domains_perf.py # schema/edge cases
.\.venv\Scripts\python.exe -m pytest tests/test_retailmind_segmentation.py tests/test_retailmind_inventory.py tests/test_retailmind_forecasting.py -q --basetemp=./tmp_ml
```
