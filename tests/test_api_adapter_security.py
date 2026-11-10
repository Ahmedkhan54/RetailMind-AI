from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime
from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException, Response
import pytest
from starlette.datastructures import UploadFile

import api as retailmind_api
from src.auth import api as auth_api
from src.auth.api import LoginRequest
from src.auth.service import AuthenticationError, UserProfile, UserSession


USER = UserProfile(
    id=27,
    email="owner@example.test",
    full_name="Retail Owner",
    phone=None,
    account_status="active",
    session_version=1,
    created_at=datetime(2025, 1, 1),
    last_login_at=None,
)


class StubAuthService:
    def login(self, email: str, password: str) -> UserProfile:
        assert email == USER.email
        assert password == "a sufficiently long test password"
        return USER

    def create_user_session(self, user_id: int, lifetime_seconds: int) -> UserSession:
        assert user_id == USER.id
        return UserSession(str(uuid4()), "opaque-test-session-secret", datetime(2025, 1, 1))

    def get_current_role(self, user_id: int) -> str:
        assert user_id == USER.id
        return "user"

    def validate_user_session(self, session_id: str, secret: str) -> UserProfile:
        assert session_id
        assert secret == "opaque-test-session-secret"
        return USER

    def require_owner_admin(self, user_id: int) -> None:
        raise AuthenticationError("Owner administrator access is required.")


@pytest.fixture
def stub_auth(monkeypatch):
    stub = StubAuthService()
    monkeypatch.setattr(auth_api, "auth_service", lambda: stub)
    retailmind_api.RAG_STORES.pop(USER.id, None)
    yield stub
    retailmind_api.RAG_STORES.pop(USER.id, None)


def sign_in(stub_auth: StubAuthService) -> tuple[Response, str]:
    response = Response()
    payload = auth_api.login(
        LoginRequest(email=USER.email, password="a sufficiently long test password"),
        response,
    )
    cookie = response.headers["set-cookie"]
    value = cookie.split(";", 1)[0].split("=", 1)[1]
    assert payload["user"]["email"] == USER.email
    assert "opaque-test-session-secret" not in str(payload)
    assert "HttpOnly" in cookie
    assert auth_api.require_authenticated_user(value) == USER
    return response, value


def test_auth_session_cookie_is_httponly_and_session_secret_is_not_returned(stub_auth):
    _response, cookie_value = sign_in(stub_auth)
    session = auth_api.current_session(auth_api.require_authenticated_user(cookie_value))
    assert session["user"]["id"] == USER.id
    assert session["role"] == "user"
    assert "opaque-test-session-secret" not in str(session)


def test_owner_controls_are_denied_to_normal_users(stub_auth):
    sign_in(stub_auth)
    with pytest.raises(HTTPException) as error:
        auth_api.owner_overview(USER)
    assert error.value.status_code == 403
    assert "Owner administrator" in error.value.detail


def test_local_rag_upload_retrieval_and_citation_are_user_scoped(stub_auth):
    sign_in(stub_auth)
    policy = (
        "Refund policy. Customers may request a refund within 30 days of purchase.\n\n"
        "Shipping policy. Standard delivery takes five business days inside the country."
    ).encode()
    upload = UploadFile(filename="policy.txt", file=BytesIO(policy))
    result = asyncio.run(retailmind_api.add_rag_document(upload, USER))
    assert result["document"]["name"] == "policy.txt"

    answer = retailmind_api.rag_answer(
        retailmind_api.RAGQuestion(question="How many days to request a refund?"),
        USER,
    )
    assert "30 days" in answer["text"]
    assert answer["sources"][0]["doc_name"] == "policy.txt"
    assert answer["used_llm"] is False


def test_cached_dataset_is_hidden_from_other_users():
    retailmind_api.DATASETS.clear()
    retailmind_api.DATASETS["dataset-27"] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales.csv",
        frame=retailmind_api.pd.DataFrame({"sales": [1]}),
        mapping={},
    )
    with pytest.raises(HTTPException) as error:
        retailmind_api.get_dataset("dataset-27", USER.id + 1)
    assert error.value.status_code == 404
    retailmind_api.DATASETS.clear()


def test_mapping_update_is_user_scoped_and_explicitly_session_only():
    dataset_id = "dataset-mapping-27"
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales.csv",
        frame=retailmind_api.pd.DataFrame({"Gross Revenue": [100], "Net Profit": [25]}),
        mapping={"sales": None, "profit": None},
    )
    try:
        result = retailmind_api.update_dataset_mapping(
            dataset_id,
            retailmind_api.DatasetMappingRequest(mapping={"sales": "Gross Revenue", "profit": "Net Profit"}),
            USER,
        )
        assert result["mapping"] == {"sales": "Gross Revenue", "profit": "Net Profit"}
        assert result["persistence"] == "process-memory"
        with pytest.raises(HTTPException) as error:
            retailmind_api.update_dataset_mapping(
                dataset_id,
                retailmind_api.DatasetMappingRequest(mapping={"sales": "Gross Revenue"}),
                replace(USER, id=USER.id + 1),
            )
        assert error.value.status_code == 404
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


def test_cleaning_review_and_download_leave_original_frame_untouched():
    dataset_id = "dataset-cleaning-27"
    frame = retailmind_api.pd.DataFrame({
        "Order_Date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "invalid"],
        "Category": [" Store  A ", "store a", "B", "B", "A"],
        "Sales": ["100", "200", "300", "400", "not-number"],
    })
    original = frame.copy(deep=True)
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales report.csv",
        frame=frame,
        mapping={},
    )
    try:
        review = retailmind_api.dataset_cleaning_review(dataset_id, USER)
        assert review["original_preserved"] is True
        assert any(item["key"] == "numeric::Sales" for item in review["suggestions"])
        response = retailmind_api.export_cleaned_dataset(
            dataset_id,
            retailmind_api.CleaningOptionsRequest(options={"trim_whitespace": True}),
            USER,
        )
        assert response.status_code == 200
        assert response.headers["content-disposition"].endswith('filename="salesreport-cleaned.csv"')
        assert '"rows_before":5' in response.headers["x-cleaning-report"]
        assert b"400" in response.body
        assert b"not-number" not in response.body
        retailmind_api.pd.testing.assert_frame_equal(frame, original)
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


def test_scenario_projection_uses_valid_paired_measures_and_reports_assumptions():
    dataset_id = "dataset-scenario-27"
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales.csv",
        frame=retailmind_api.pd.DataFrame({
            "Revenue": [100, 200, "invalid"],
            "Profit": [20, 30, 40],
        }),
        mapping={"sales": "Revenue", "profit": "Profit"},
    )
    try:
        result = retailmind_api.project_business_scenario(
            retailmind_api.ScenarioRequest(
                dataset_id=dataset_id,
                discount_shift_points=10,
                margin_shift_points=2,
            ),
            USER,
        )
        assert result["available"] is True
        assert result["baseline_sales"] == 300
        assert result["baseline_profit"] == 50
        assert result["projected_sales"] == 270
        assert result["projected_profit"] == pytest.approx(25.4)
        assert result["rows_used"] == 2
        assert result["rows_excluded"] == 1
        assert "not a causal forecast" in result["notes"][0]
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)



def test_cleaning_rejects_unrecognized_options_and_mapping_collisions():
    dataset_id = "dataset-invalid-27"
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales.csv",
        frame=retailmind_api.pd.DataFrame({"Revenue": [10], "Profit": [2]}),
        mapping={"sales": None, "profit": None},
    )
    try:
        with pytest.raises(HTTPException) as option_error:
            retailmind_api.export_cleaned_dataset(
                dataset_id,
                retailmind_api.CleaningOptionsRequest(options={"drop_all_rows": True}),
                USER,
            )
        assert option_error.value.status_code == 422
        with pytest.raises(HTTPException) as mapping_error:
            retailmind_api.update_dataset_mapping(
                dataset_id,
                retailmind_api.DatasetMappingRequest(mapping={"sales": "Revenue", "profit": "Revenue"}),
                USER,
            )
        assert mapping_error.value.status_code == 422
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


def test_filtered_exports_apply_inclusive_dates_without_changing_source_data():
    dataset_id = "dataset-export-27"
    frame = retailmind_api.pd.DataFrame({
        "Order_Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "Sales": [100, 200, 300],
    })
    original = frame.copy(deep=True)
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales.csv",
        frame=frame,
        mapping={"order_date": "Order_Date"},
    )
    try:
        response = retailmind_api.export_dataset(
            dataset_id,
            "csv",
            USER,
            date_from=date(2025, 1, 2),
            date_to=date(2025, 1, 3),
        )
        csv_text = response.body.decode("utf-8-sig")
        assert "200" in csv_text and "300" in csv_text
        assert "100" not in csv_text
        retailmind_api.pd.testing.assert_frame_equal(frame, original)
        with pytest.raises(HTTPException) as error:
            retailmind_api.export_dataset(
                dataset_id,
                "csv",
                USER,
                date_from=date(2025, 1, 4),
                date_to=date(2025, 1, 2),
            )
        assert error.value.status_code == 422
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


def test_date_scoped_dashboard_and_breakdown_filter_all_metrics_without_mutating_source():
    dataset_id = "dataset-filtered-27"
    frame = retailmind_api.pd.DataFrame({
        "Order_ID": ["O1", "O2", "O3"],
        "Order_Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "Category": ["A", "B", "B"],
        "Product": ["P1", "P2", "P2"],
        "City": ["North", "South", "South"],
        "Customer": ["C1", "C2", "C2"],
        "Sales": [100, 200, 300],
        "Profit": [20, 40, 60],
    })
    original = frame.copy(deep=True)
    mapping = {
        "order_id": "Order_ID",
        "order_date": "Order_Date",
        "category": "Category",
        "product_name": "Product",
        "city": "City",
        "customer": "Customer",
        "sales": "Sales",
        "profit": "Profit",
    }
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales.csv",
        frame=frame,
        mapping=mapping,
    )
    try:
        start, end = date(2025, 1, 2), date(2025, 1, 3)
        overview = retailmind_api.dashboard_overview(
            dataset_id,
            USER,
            date_from=start,
            date_to=end,
        )
        assert overview["available"] is True
        assert overview["row_count"] == 2
        assert overview["kpis"]["total_sales"] == 500
        assert overview["kpis"]["total_customers"] == 1
        assert {row["category"] for row in overview["category_sales"]} == {"B"}

        breakdown = retailmind_api.analytics_breakdown(
            dataset_id,
            "category",
            USER,
            date_from=start,
            date_to=end,
        )
        assert breakdown["available"] is True
        assert breakdown["row_count"] == 1
        assert breakdown["rows"][0]["sales"] == 500
        retailmind_api.pd.testing.assert_frame_equal(frame, original)

        with pytest.raises(HTTPException) as error:
            retailmind_api.dashboard_overview(
                dataset_id,
                USER,
                date_from=end,
                date_to=start,
            )
        assert error.value.status_code == 422
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


def test_customer_tagging_paginates_and_exports_full_owner_scoped_result():
    dataset_id = "dataset-tags-27"
    frame = retailmind_api.pd.DataFrame({
        "cust_id": ["C1", "C2", "C3", "C4", "C5"],
        "order_date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"],
        "sales": [10, 20, 30, 40, 50],
    })
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="customers.csv",
        frame=frame,
        mapping={},
    )
    try:
        first = retailmind_api.customer_segmentation(dataset_id, USER, offset=0, limit=2)
        second = retailmind_api.customer_segmentation(dataset_id, USER, offset=2, limit=2)
        assert first["available"] is True
        assert first["customer_total"] == 5
        assert len(first["customers"]) == 2
        assert len(second["customers"]) == 2
        assert first["customers"][0]["customer_id"] != second["customers"][0]["customer_id"]

        csv_response = retailmind_api.export_customer_segmentation(dataset_id, "csv", USER)
        exported = csv_response.body.decode("utf-8-sig")
        assert csv_response.status_code == 200
        assert "C1" in exported and "C5" in exported
        assert len(exported.splitlines()) == 6
        with pytest.raises(HTTPException) as error:
            retailmind_api.customer_segmentation(dataset_id, replace(USER, id=USER.id + 1), offset=0, limit=2)
        assert error.value.status_code == 404
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


def test_inventory_recommendations_use_date_scoped_demand():
    dataset_id = "dataset-inventory-filter-27"
    frame = retailmind_api.pd.DataFrame({
        "product_name": ["Product A", "Product B", "Product B"],
        "order_date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "quantity": [100, 2, 4],
    })
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="inventory.csv",
        frame=frame,
        mapping={},
    )
    try:
        filtered = retailmind_api.inventory_recommendations(
            dataset_id,
            USER,
            date_from=date(2025, 1, 2),
            date_to=date(2025, 1, 3),
        )
        assert filtered["available"] is True
        assert [row["product"] for row in filtered["recommendations"]] == ["Product B"]
        assert filtered["recommendations"][0]["avg_daily_sales"] == 3
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)


def test_markdown_export_respects_inclusive_date_filter():
    dataset_id = "dataset-md-27"
    retailmind_api.DATASETS[dataset_id] = retailmind_api.DatasetRecord(
        owner_id=USER.id,
        filename="sales report.csv",
        frame=retailmind_api.pd.DataFrame({
            "Order_Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "Product": ["Before", "In range", "Last day"],
            "Sales": [10, 20, 30],
        }),
        mapping={"order_date": "Order_Date"},
    )
    try:
        response = retailmind_api.export_dataset(
            dataset_id,
            "md",
            USER,
            date_from=date(2025, 1, 2),
            date_to=date(2025, 1, 3),
        )
        markdown = response.body.decode("utf-8")
        assert response.status_code == 200
        assert response.headers["content-disposition"].endswith('filename="salesreport_report.md"')
        assert "In range" in markdown and "Last day" in markdown
        assert "Before" not in markdown
        assert "2025-01-02" in markdown and "2025-01-03" in markdown
    finally:
        retailmind_api.DATASETS.pop(dataset_id, None)
