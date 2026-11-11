"""Tests for the additive visual-analytics aggregate endpoint.

The endpoint is exercised directly with an in-memory dataset so the tests do
not need MySQL, uploaded files, or the browser. Every expectation is derived
from the same fixture rows the endpoint receives.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
import pytest
from fastapi import HTTPException

import api as retailmind_api
from src.auth.service import UserProfile

USER = UserProfile(
    id=91,
    email="visuals@example.test",
    full_name="Visual Owner",
    phone=None,
    account_status="active",
    session_version=1,
    created_at=datetime(2025, 1, 1),
    last_login_at=None,
)

DATASET_ID = "visuals-test-dataset"


def fixture_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Order": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "Date": [
                "2025-01-05",
                "2025-01-18",
                "2025-02-02",
                "2025-02-11",
                "2025-02-19",
                "2025-02-24",
                "2025-03-03",
                "2025-03-10",
            ],
            "Category": ["Office", "Tech", "Office", "Tech", "Office", "Furniture", "Tech", "Returns"],
            "Product": ["Pen", "Phone", "Pad", "Laptop", "Chair", "Desk", "Tablet", "Return"],
            "City": ["Delhi", "Pune", "Delhi", "Mumbai", "Delhi", "Pune", "Mumbai", "Delhi"],
            "Region": ["North", "West", "North", "West", "North", "West", "West", "North"],
            "Customer": ["alice", "bob", "alice", "carol", "alice", "bob", "carol", "alice"],
            "Sales": [100.0, 200.0, 150.0, 400.0, 250.0, 300.0, 500.0, 20.0],
            "Profit": [20.0, 50.0, 30.0, -40.0, 75.0, 60.0, 100.0, -30.0],
        }
    )


def fixture_record(frame: pd.DataFrame | None = None, *, map_region: bool = True) -> retailmind_api.DatasetRecord:
    mapping = {
        "order_id": "Order",
        "order_date": "Date",
        "category": "Category",
        "product_name": "Product",
        "city": "City",
        "customer": "Customer",
        "sales": "Sales",
        "profit": "Profit",
    }
    if map_region:
        mapping["region"] = "Region"
    return retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="visual-fixture.csv",
        frame=fixture_frame() if frame is None else frame,
        mapping=mapping,
    )


@pytest.fixture
def dataset(monkeypatch):
    frame = fixture_frame()
    monkeypatch.setitem(retailmind_api.DATASETS, DATASET_ID, fixture_record(frame))
    return frame


def call(**kwargs):
    dataset_id = kwargs.pop("dataset_id", DATASET_ID)
    options = {"date_from": None, "date_to": None, "category": None, "city": None, "region": None}
    options.update(kwargs)
    return retailmind_api.visual_analytics(dataset_id=dataset_id, user=USER, **options)


def test_visuals_return_real_aggregates_and_chart_series(dataset):
    payload = call()
    assert payload["available"] is True
    assert payload["matched_rows"] == len(dataset)
    assert payload["kpis"]["total_sales"] == pytest.approx(float(dataset["Sales"].sum()))
    assert payload["kpis"]["total_profit"] == pytest.approx(float(dataset["Profit"].sum()))

    assert sum(row["sales"] for row in payload["categories"]) == pytest.approx(float(dataset["Sales"].sum()))
    assert {row["category"] for row in payload["categories"]} == {"Office", "Tech", "Furniture", "Returns"}
    assert {row["region"] for row in payload["regions"]} == {"North", "West"}
    assert len(payload["monthly"]) == 3
    assert len(payload["category_month"]) >= 3
    assert len(payload["scatter"]) == len(dataset)
    assert all("sales" in row and "profit" in row for row in payload["scatter"])
    assert payload["decomposition"]["value"] == pytest.approx(float(dataset["Sales"].sum()))
    assert payload["decomposition"]["children"]
    assert json.dumps(payload)  # every value is JSON serialisable


def test_histogram_and_box_values_match_observed_measure(dataset):
    payload = call()
    histogram = payload["histogram"]["sales"]
    assert histogram
    assert sum(row["count"] for row in histogram) == len(dataset)
    for row in histogram:
        assert row["bin_start"] <= row["bin_end"]
        assert row["count"] > 0

    box = payload["box"]["sales_by_category"]
    assert box
    assert sum(row["count"] for row in box) == len(dataset)
    for row in box:
        assert row["min"] <= row["q1"] <= row["median"] <= row["q3"] <= row["max"]


def test_category_filter_is_applied_server_side(dataset):
    payload = call(category="Tech")
    tech = dataset[dataset["Category"] == "Tech"]
    assert payload["matched_rows"] == len(tech)
    assert payload["kpis"]["total_sales"] == pytest.approx(float(tech["Sales"].sum()))
    assert payload["applied_filters"] == {"category": "Tech"}
    assert {row["category"] for row in payload["categories"]} == {"Tech"}
    # Filter options still expose every category so the user can switch.
    assert set(payload["filters"]["category"]) == {"Tech", "Furniture", "Office", "Returns"}


def test_city_and_region_filters_combine(dataset):
    payload = call(city="Delhi", region="North")
    expected = dataset[(dataset["City"] == "Delhi") & (dataset["Region"] == "North")]
    assert payload["matched_rows"] == len(expected)
    assert payload["kpis"]["total_sales"] == pytest.approx(float(expected["Sales"].sum()))
    assert payload["applied_filters"] == {"city": "Delhi", "region": "North"}


def test_date_range_filter_matches_february_rows(dataset):
    payload = call(date_from=date(2025, 2, 1), date_to=date(2025, 2, 28))
    expected = dataset[dataset["Date"].str.startswith("2025-02")]
    assert payload["matched_rows"] == len(expected)
    assert payload["kpis"]["total_sales"] == pytest.approx(float(expected["Sales"].sum()))
    assert len(payload["monthly"]) == 1


def test_unknown_filter_value_returns_no_matches(dataset):
    payload = call(category="Not a category")
    assert payload["available"] is False
    assert payload["matched_rows"] == 0
    assert payload["notes"]


def test_region_filter_requires_a_mapped_region(monkeypatch):
    monkeypatch.setitem(retailmind_api.DATASETS, DATASET_ID, fixture_record(map_region=False))
    with pytest.raises(HTTPException) as error:
        call(region="North")
    assert error.value.status_code == 422
    assert "region" in error.value.detail.lower()


def test_unmapped_dataset_reports_unavailable(monkeypatch):
    frame = fixture_frame().drop(columns=["Profit"])
    monkeypatch.setitem(retailmind_api.DATASETS, DATASET_ID, fixture_record(frame))
    payload = call()
    assert payload["available"] is False
    assert payload["notes"]


def test_pareto_and_waterfall_use_observed_values(dataset):
    payload = call()
    pareto = payload["pareto"]
    assert pareto
    assert pareto[-1]["cumulative_share"] <= 1.0 + 1e-9
    assert [row["cumulative_share"] for row in pareto] == sorted(row["cumulative_share"] for row in pareto)
    assert pareto[0]["label"] == "Tablet"

    waterfall = payload["waterfall"]
    assert waterfall[-1]["type"] == "total"
    assert waterfall[-1]["value"] == pytest.approx(float(dataset["Profit"].sum()))
    assert any(row["type"] == "decrease" for row in waterfall)


def test_funnel_stages_reflect_product_concentration(dataset):
    payload = call()
    stages = payload["funnel"]
    assert stages
    assert stages[-1]["products"] == int(dataset["Product"].nunique())
    assert stages[-1]["share"] == pytest.approx(1.0)


def test_concurrent_dataset_isolation(dataset, monkeypatch):
    other_id = "visuals-other-dataset"
    other = fixture_record(fixture_frame().assign(Sales=lambda frame: frame["Sales"] * 2))
    monkeypatch.setitem(retailmind_api.DATASETS, other_id, other)
    own = call()
    theirs = call(dataset_id=other_id)
    assert own["kpis"]["total_sales"] != theirs["kpis"]["total_sales"]
    assert theirs["kpis"]["total_sales"] == pytest.approx(own["kpis"]["total_sales"] * 2)
