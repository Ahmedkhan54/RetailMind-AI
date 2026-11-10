import unittest
from unittest.mock import Mock

import pandas as pd

from python.safe_import import (CONFIRMATION_PHRASE, build_preview_report,
                                merge_staging_into_sales, staging_table_ddl,
                                validate_import_frame)

BATCH_ID = "12345678-1234-1234-1234-123456789abc"


def valid_frame():
    return pd.DataFrame({
        "order_id": ["A", "B"], "order_date": ["2025-01-01", "2025-01-02"],
        "customer_id": [1, 2], "product_name": ["Pen", "Phone"],
        "category": ["Office", "Tech"], "city": ["Delhi", "Pune"],
        "region": ["North", "West"], "quantity": [2, 1],
        "unit_price": [10.0, 200.0], "discount_pct": [0.1, 0.0],
        "sales": [18.0, 200.0], "profit": [4.0, 50.0],
        "payment_method": ["Card", "Cash"],
    })


class SafeImportTests(unittest.TestCase):
    def test_valid_candidate_has_preview_and_reconciliation_totals(self):
        source = valid_frame()
        original = source.copy(deep=True)
        result = validate_import_frame(source, expected_totals={"sales": 218, "profit": 54})
        self.assertTrue(result.valid)
        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.totals["quantity"], 3)
        self.assertEqual(len(result.preview), 2)
        pd.testing.assert_frame_equal(source, original)
        self.assertIn("Validation: PASS", build_preview_report(result))

    def test_validation_rejects_missing_columns_bad_ranges_and_duplicates(self):
        frame = valid_frame().assign(order_id=["A", "A"], quantity=[0, 1], discount_pct=[1.2, 0])
        frame = frame.drop(columns=["payment_method"])
        result = validate_import_frame(frame)
        self.assertFalse(result.valid)
        self.assertTrue(any("Missing required" in error for error in result.errors))
        self.assertTrue(any("Duplicate order_id" in error for error in result.errors))
        self.assertTrue(any("quantity" in error for error in result.errors))
        self.assertTrue(any("discount_pct" in error for error in result.errors))

    def test_validation_rejects_bad_dates_types_lengths_and_reconciliation(self):
        frame = valid_frame().assign(order_date=["not-a-date", "2025-01-02"], customer_id=["x", 2])
        frame.loc[0, "product_name"] = "x" * 101
        result = validate_import_frame(frame, expected_totals={"sales": 999})
        self.assertFalse(result.valid)
        self.assertTrue(any("order_date" in error for error in result.errors))
        self.assertTrue(any("customer_id" in error for error in result.errors))
        self.assertTrue(any("product_name" in error for error in result.errors))
        self.assertTrue(any("Reconciliation mismatch" in error for error in result.errors))

    def test_validation_rejects_empty_import_and_null_text_values(self):
        empty = validate_import_frame(valid_frame().iloc[0:0])
        self.assertFalse(empty.valid)
        self.assertIn("The import contains no rows.", empty.errors)
        frame = valid_frame().copy()
        frame.loc[0, "city"] = None
        frame.loc[1, "payment_method"] = ""
        result = validate_import_frame(frame)
        self.assertFalse(result.valid)
        self.assertTrue(any("city contains null or blank" in error for error in result.errors))
        self.assertTrue(any("payment_method contains null or blank" in error for error in result.errors))

    def test_validation_checks_existing_database_ids_without_connecting(self):
        result = validate_import_frame(valid_frame(), existing_order_ids=["B", "already-there"])
        self.assertFalse(result.valid)
        self.assertEqual(result.existing_order_ids, ("B",))
        self.assertTrue(any("already exist in sales" in error for error in result.errors))

    def test_validation_rejects_decimal_overprecision_and_rounding(self):
        frame = valid_frame().copy()
        # Keep the intentionally malformed values as object data so pandas does
        # not reject the assignment before the importer can validate them.
        frame["unit_price"] = frame["unit_price"].astype(object)
        frame["sales"] = frame["sales"].astype(object)
        frame.loc[0, "unit_price"] = "10.123"
        frame.loc[1, "sales"] = "123456789012.999"
        result = validate_import_frame(frame)
        self.assertFalse(result.valid)
        self.assertTrue(any("unit_price" in error and "DECIMAL" in error for error in result.errors))
        self.assertTrue(any("sales" in error and "DECIMAL" in error for error in result.errors))

    def test_staging_ddl_is_only_text_and_identifier_is_validated(self):
        ddl = staging_table_ddl()
        self.assertIn("CREATE TABLE IF NOT EXISTS `sales_staging`", ddl)
        self.assertIn("import_batch_id", ddl)
        with self.assertRaises(ValueError):
            staging_table_ddl("sales_staging; DELETE FROM sales")

    def test_merge_requires_confirmation_before_touching_connection(self):
        connection = Mock()
        validation = validate_import_frame(valid_frame())
        with self.assertRaises(PermissionError):
            merge_staging_into_sales(connection, validation, confirmation="yes")
        connection.cursor.assert_not_called()

    def test_merge_requires_batch_id_before_starting_transaction(self):
        connection = Mock()
        validation = validate_import_frame(valid_frame())
        with self.assertRaisesRegex(ValueError, "import_batch_id"):
            merge_staging_into_sales(connection, validation, confirmation=CONFIRMATION_PHRASE)
        connection.cursor.assert_not_called()

    def test_merge_rolls_back_mock_transaction_on_failure(self):
        connection = Mock()
        cursor = connection.cursor.return_value
        cursor.execute.side_effect = RuntimeError("simulated SQL failure")
        validation = validate_import_frame(valid_frame())
        with self.assertRaisesRegex(RuntimeError, "simulated SQL failure"):
            merge_staging_into_sales(connection, validation, confirmation=CONFIRMATION_PHRASE,
                                     import_batch_id=BATCH_ID)
        connection.start_transaction.assert_called_once_with()
        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()

    def test_merge_reports_when_rollback_itself_fails(self):
        connection = Mock()
        connection.cursor.return_value.execute.side_effect = RuntimeError("SQL failure")
        connection.rollback.side_effect = RuntimeError("rollback failure")
        validation = validate_import_frame(valid_frame())
        with self.assertRaisesRegex(RuntimeError, "rollback failed"):
            merge_staging_into_sales(connection, validation, confirmation=CONFIRMATION_PHRASE,
                                     import_batch_id=BATCH_ID)

    def test_confirmed_merge_is_transactional_and_insert_only(self):
        connection = Mock()
        validation = validate_import_frame(valid_frame())
        merge_staging_into_sales(connection, validation, confirmation=CONFIRMATION_PHRASE,
                                 import_batch_id=BATCH_ID)
        connection.start_transaction.assert_called_once_with()
        connection.commit.assert_called_once_with()
        sql = connection.cursor.return_value.execute.call_args.args[0]
        self.assertIn("INSERT INTO sales", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("staged.import_batch_id = %s", sql)
        self.assertEqual(connection.cursor.return_value.execute.call_args.args[1], (BATCH_ID,))
        self.assertNotIn("DELETE", sql.upper())


if __name__ == "__main__":
    unittest.main()
