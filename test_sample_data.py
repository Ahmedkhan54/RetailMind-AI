"""
Sample data generation for RetailMind AI independent audit testing.
This creates realistic datasets for each business domain to test all 12 feature categories.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# Retail/Sales Dataset
print("Generating Retail Sales sample data...")
np.random.seed(42)
dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")

retail_data = []
for i in range(10000):
    date = np.random.choice(dates)
    customer_id = f"CUST_{np.random.randint(1, 500)}"
    product_id = f"PROD_{np.random.randint(1, 200)}"
    category = np.random.choice(["Electronics", "Clothing", "Home", "Sports", "Books"])
    quantity = np.random.randint(1, 10)
    unit_price = round(np.random.uniform(10, 500), 2)
    discount = round(np.random.uniform(0, 0.3), 3)
    
    revenue = quantity * unit_price * (1 - discount)
    profit = revenue * np.random.uniform(0.2, 0.5)
    cost = revenue - profit
    
    retail_data.append({
        "order_id": f"ORD_{i:06d}",
        "cust_id": customer_id,
        "date": date.strftime("%Y-%m-%d"),
        "product_id": product_id,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount": discount,
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "region": np.random.choice(["North", "South", "East", "West"]),
        "store": f"STORE_{np.random.randint(1, 20)}",
        "sales_rep": f"REP_{np.random.randint(1, 10)}"
    })

retail_df = pd.DataFrame(retail_data)
print(f"Created retail dataset with {len(retail_df):,} rows and {len(retail_df.columns)} columns")

# Finance Dataset
print("\nGenerating Finance sample data...")
finance_data = []
for i in range(5000):
    emp_id = f"EMP_{np.random.randint(1, 100)}"
    dept = np.random.choice(["Engineering", "Sales", "Marketing", "HR", "Finance"])
    salary = np.random.randint(50000, 150000)
    bonus = round(np.random.uniform(0, salary * 0.3), 2)
    expense = round(np.random.uniform(0, 5000), 2)
    
    finance_data.append({
        "employee_id": emp_id,
        "department": dept,
        "salary": salary,
        "bonus": bonus,
        "expense": expense,
        "cost_center": f"CC_{np.random.randint(1, 10)}",
        "month": np.random.randint(1, 13),
        "year": 2023,
        "attendance_days": np.random.randint(20, 25),
        "grade": np.random.choice(["A", "B", "C", "D", "F"], p=[0.3, 0.4, 0.2, 0.08, 0.02])
    })

finance_df = pd.DataFrame(finance_data)
print(f"Created finance dataset with {len(finance_df):,} rows and {len(finance_df.columns)} columns")

# HR Dataset (slightly different structure)
print("\nGenerating HR sample data...")
hr_data = []
for i in range(3000):
    student_id = f"STU_{np.random.randint(1, 300)}"
    course_id = f"COURSE_{np.random.randint(1, 50)}"
    grade = np.random.choice(["A", "B", "C", "D", "F"], p=[0.25, 0.35, 0.30, 0.08, 0.02])
    attendance_rate = round(np.random.uniform(0.7, 1.0), 3)
    
    hr_data.append({
        "student_id": student_id,
        "course_id": course_id,
        "grade": grade,
        "attendance_rate": attendance_rate,
        "credits": np.random.randint(2, 4),
        "semester": f"FALL_{2023 - np.random.randint(0, 5)}",
        "instructor": f"INST_{np.random.randint(1, 20)}",
        "enrollment_date": (datetime.now() - timedelta(days=np.random.randint(0, 365))).strftime("%Y-%m-%d")
    })

hr_df = pd.DataFrame(hr_data)
print(f"Created HR dataset with {len(hr_df):,} rows and {len(hr_df.columns)} columns")

# E-commerce Dataset (for e-commerce testing)
print("\nGenerating E-commerce sample data...")
ecommerce_data = []
for i in range(8000):
    user_id = f"USER_{np.random.randint(1, 400)}"
    session_id = f"SESS_{i:06d}"
    product_category = np.random.choice(["Clothing", "Electronics", "Home", "Beauty", "Books", "Sports"])
    cart_value = round(np.random.uniform(10, 1000), 2)
    items_purchased = np.random.randint(1, 8)
    payment_method = np.random.choice(["Credit Card", "PayPal", "Apple Pay", "Cash"])
    
    ecommerce_data.append({
        "user_id": user_id,
        "session_id": session_id,
        "product_category": product_category,
        "cart_value": cart_value,
        "items_purchased": items_purchased,
        "payment_method": payment_method,
        "device_type": np.random.choice(["Mobile", "Desktop", "Tablet"]),
        "conversion_rate": round(np.random.uniform(0.1, 1.0), 3),
        "revenue_per_session": round(cart_value * (items_purchased / max(1, np.random.randint(1, 5))), 2)
    })

ecommerce_df = pd.DataFrame(ecommerce_data)
print(f"Created e-commerce dataset with {len(ecommerce_df):,} rows and {len(ecommerce_df.columns)} columns")

# Save datasets to CSV for testing
print("\nSaving sample datasets...")
retail_df.to_csv("test_retail_sales.csv", index=False)
finance_df.to_csv("test_finance.csv", index=False)
hr_df.to_csv("test_hr.csv", index=False)
ecommerce_df.to_csv("test_ecommerce.csv", index=False)

print("\nDataset generation complete!")
print("\nSample data created:")
print("- test_retail_sales.csv (retail/sales data)")
print("- test_finance.csv (finance data)")
print("- test_hr.csv (HR data)")
print("- test_ecommerce.csv (e-commerce data)")

# Create inventory data for testing
print("\nGenerating Inventory sample data...")
inventory_data = []
for i in range(2000):
    product_id = f"PROD_{np.random.randint(1, 200)}"
    current_stock = np.random.randint(0, 100)
    sales_30_days = np.random.randint(0, 50)
    lead_time_days = np.random.randint(1, 30)
    
    # Calculate some derived metrics
    avg_daily_demand = sales_30_days / 30
    days_remaining = current_stock / avg_daily_demand if avg_daily_demand > 0 else float('inf')
    
    inventory_data.append({
        "product_id": product_id,
        "current_stock": current_stock,
        "sales_30_days": sales_30_days,
        "lead_time_days": lead_time_days,
        "supplier": f"SUPP_{np.random.randint(1, 15)}",
        "unit_cost": round(np.random.uniform(5, 100), 2),
        "sales_history": json.dumps({
            "day1": np.random.randint(0, 10),
            "day2": np.random.randint(0, 10),
            "day3": np.random.randint(0, 10),
            "day4": np.random.randint(0, 10),
            "day5": np.random.randint(0, 10),
        }),
        "incoming_stock": max(0, np.random.randint(-20, 50))
    })

inventory_df = pd.DataFrame(inventory_data)
print(f"Created inventory dataset with {len(inventory_df):,} rows and {len(inventory_df.columns)} columns")

# Save inventory data
inventory_df.to_csv("test_inventory.csv", index=False)
print("- test_inventory.csv (inventory data)")

print("\nAll sample datasets ready for RetailMind AI independent audit!")