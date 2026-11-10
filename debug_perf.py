import sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import pandas as pd, numpy as np
from retailmind.schema import infer_schema
from data_sources import profile_schema

# e-commerce role check
f = pd.DataFrame({
    "Session ID": [f"S{i}" for i in range(50)],
    "User ID": [f"U{i%10}" for i in range(50)],
    "Event Date": pd.date_range("2023-01-01", periods=50, freq="6h").strftime("%Y-%m-%d %H:%M"),
    "Product Category": ["Beauty", "Electronics", "Home", "Books"] * 12 + ["Beauty", "Electronics"],
    "Cart Value": np.round(np.random.uniform(10, 900, 50), 2),
    "Items": np.random.randint(1, 7, 50),
    "Payment Method": ["Card", "PayPal", "Apple Pay"] * 16 + ["Card", "PayPal"],
})
s = infer_schema(f)
print("ROLES:", s.roles)
print("DIMS:", s.dimensions)
print("DOMAIN:", s.domain)
print("CATEGORICAL:", s.categorical)

# perf breakdown without tracemalloc
import importlib
spec = importlib.util.spec_from_file_location("ap", "audit_domains_perf.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for rows in (10_000, 100_000):
    frame = m.retail_frame(rows, seed=rows)
    t0 = time.perf_counter(); ps = profile_schema(frame); t1 = time.perf_counter()
    t2 = time.perf_counter(); sc = infer_schema(frame); t3 = time.perf_counter()
    print(f"rows={rows}: profile_schema={1000*(t1-t0):.0f}ms infer_schema={1000*(t3-t2):.0f}ms")
    # time just the date column parse
    col = frame["Order Date"]
    t4 = time.perf_counter(); pd.to_datetime(col.dropna().astype("string"), format="mixed", errors="coerce"); t5 = time.perf_counter()
    print(f"   full date parse format=mixed: {1000*(t5-t4):.0f}ms")
    t6 = time.perf_counter(); pd.to_datetime(col.dropna().astype("string").head(5000), format="mixed", errors="coerce"); t7 = time.perf_counter()
    print(f"   sample 5000 date parse:      {1000*(t7-t6):.0f}ms")
