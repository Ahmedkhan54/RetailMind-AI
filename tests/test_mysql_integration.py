"""Runs against Docker MySQL; CI supplies MYSQL_* and initializes the schema."""
import os
import uuid
import pandas as pd
import mysql.connector
import pytest

from python.safe_import import (CONFIRMATION_PHRASE, merge_staging_into_sales, stage_import_frame,
                                staging_table_ddl, validate_import_frame)

pytestmark = pytest.mark.skipif(
    not all(os.getenv(name) for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")),
    reason="requires explicitly configured disposable MySQL integration environment",
)


def candidate(order_id="IT-001"):
    return pd.DataFrame({"order_id": [order_id], "order_date": ["2025-01-01"], "customer_id": [1],
        "product_name": ["Pen"], "category": ["Office"], "city": ["Delhi"], "region": ["North"],
        "quantity": [1], "unit_price": [10.0], "discount_pct": [0.0], "sales": [10.0], "profit": [2.0], "payment_method": ["Card"]})


@pytest.fixture
def connection():
    connection = mysql.connector.connect(host=os.environ["MYSQL_HOST"], port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"], password=os.environ["MYSQL_PASSWORD"], database=os.environ["MYSQL_DATABASE"])
    cursor = connection.cursor(); cursor.execute(staging_table_ddl()); cursor.execute("DELETE FROM sales_staging"); cursor.execute("DELETE FROM sales WHERE order_id LIKE 'IT-%'"); connection.commit(); cursor.close()
    yield connection
    connection.close()


@pytest.mark.integration
def test_staging_merge_duplicate_rejection_and_atomic_rollback(connection):
    frame = candidate("IT-001")
    validation = validate_import_frame(frame)
    batch = str(uuid.uuid4())
    assert stage_import_frame(connection, frame, validation, import_batch_id=batch) == 1
    merge_staging_into_sales(connection, validation, confirmation=CONFIRMATION_PHRASE, import_batch_id=batch)
    cursor = connection.cursor(); cursor.execute("SELECT COUNT(*) FROM sales WHERE order_id = 'IT-001'"); assert cursor.fetchone()[0] == 1
    duplicate = validate_import_frame(candidate("IT-001"), existing_order_ids=["IT-001"])
    assert not duplicate.valid and duplicate.existing_order_ids == ("IT-001",)
    # A duplicate primary-key batch fails as one transaction; neither new row persists.
    bad = pd.concat([candidate("IT-002"), candidate("IT-002")], ignore_index=True)
    bad_validation = validate_import_frame(bad)
    assert not bad_validation.valid
    with pytest.raises(ValueError): stage_import_frame(connection, bad, bad_validation, import_batch_id=str(uuid.uuid4()))
    cursor.execute("SELECT COUNT(*) FROM sales_staging WHERE order_id = 'IT-002'"); assert cursor.fetchone()[0] == 0
    cursor.close()
