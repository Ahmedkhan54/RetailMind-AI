import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import numpy as np
import pandas as pd
from retailmind.schema import infer_schema
from retailmind.forecasting import forecast_dataset, _metrics

# reuse the audit builder
import importlib.util
spec = importlib.util.spec_from_file_location("audit_functional", "audit_functional.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
frame = mod.build_retail()
schema = infer_schema(frame)

res = forecast_dataset(frame, schema, metric_role="revenue", frequency="Monthly", periods=3, method="Auto (backtest)")
print("available:", res.available)
print("notes:", res.notes)
print("method:", res.method, "train:", res.train_size, "test:", res.test_size)
print("metrics:", res.metrics)
print(res.forecast.head())
print("lower<=fc:", (res.forecast["lower_bound"] <= res.forecast["forecast"]).all())
print("fc<=upper:", (res.forecast["forecast"] <= res.forecast["upper_bound"]).all())

m = _metrics(np.array([10.0, 20.0]), np.array([8.0, 25.0]))
print("metrics check:", m, "mae ok", abs(m["mae"] - 3.5) < 1e-9, "rmse ok", abs(m["rmse"] - np.sqrt((4+25)/2)) < 1e-9, "mape ok", abs(m["mape"] - ((2/10 + 5/20)/2)*100) < 1e-9)

short = frame.head(5)
short_res = forecast_dataset(short, infer_schema(short), metric_role="revenue", frequency="Daily")
print("short available:", short_res.available, "notes:", short_res.notes)
