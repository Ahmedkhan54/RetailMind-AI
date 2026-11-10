#!/usr/bin/env python3
"""
RetailMind AI Independent Audit Test
Tests core functionality without Unicode characters in output
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

print("RetailMind AI Audit Test")
print("=" * 40)

# Load sample data if available
sample_files = [
    "test_retail_sales.csv",
    "test_finance.csv", 
    "test_hr.csv",
    "test_ecommerce.csv",
    "test_inventory.csv"
]

print("Sample data files:")
for file in sample_files:
    if Path(file).exists():
        print("  Found:", file)
    else:
        print("  Missing:", file)

# Test core module imports
print("\nCore module imports:")
try:
    from retailmind.schema import infer_schema
    print("  infer_schema: OK")
except Exception as e:
    print("  infer_schema:", e)

try:
    from retailmind.segmentation import segment_customers
    print("  segment_customers: OK")
except Exception as e:
    print("  segment_customers:", e)

try:
    from retailmind.powerbi import build_pbip
    print("  build_pbip: OK")
except Exception as e:
    print("  build_pbip:", e)

try:
    from retailmind.ai.chat import answer_question
    print("  answer_question: OK")
except Exception as e:
    print("  answer_question:", e)

# Create simple test dataframe
print("\nSchema inference test:")
test_data = {
    "customer_id": ["C1", "C2", "C1"],
    "order_date": ["2023-01-01", "2023-/easy/inference", "2023-01-03"],
    "product": ["A", "B", "A"],
    "quantity": [2, 1, 3],
    "unit_price": [10.0, 20.0, 10.0],
    "revenue": [20.0, 20.0, 30.0],
    "profit": [4.0, 4.0, 6.0]
}
df = pd.DataFrame(test_data)

try:
    schema = infer_schema(df)
    print("  Schema inferred successfully")
    print("    Columns:", len(schema.columns))
    print("    Revenue detected:", schema.has("revenue"))
    print("    Customer detected:", schema.has("customer"))
    print("    Date detected:", schema.has("date"))
    print("    Domain:", schema.domain)
except Exception as e:
    print("  Schema inference failed:", str(e))

# Test customer segmentation
print("\nCustomer segmentation test:")
try:
    customer_data = {
        "cust_id": ["C1", "C2", "C1", "C3", "C2"],
        "order_date": ["2023-01-01", "2023-01-05", "2023-01-10",
                       "2023-01-02", "2023-01-06"],
        "sales": [100.0, 500.0, 200.0, 50.0, 1500.0],
        "order_id": ["O1", "O2", "O3", "O4", "O5"]
    }
    customer_df = pd.DataFrame(customer_data)
    schema = infer_schema(customer_df)
    result = segment_customers(customer_df, schema, max_clusters=2)
    
    print("  Segmentation result:")
    print("    Available:", result.available)
    print("    Clusters:", result.k)
    print("    Customers:", len(result.rfm) if not result.rfm.empty else 0)
    print("    Notes:", len(result.notes))
except Exception as e:
    print("  Segmentation failed:", str(e))

print("\n" + "=" * 40)
print("Audit Test Complete")
print("If all tests pass, core functionality is working.")
print("=" * 40)