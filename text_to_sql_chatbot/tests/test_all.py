"""
Comprehensive Production Test Suite.
Covers SQL Guard, Data Profiler, Database Switching, and REST API Endpoints.
Compatible with standard library unittest and pytest.
"""

import os
import sys
import unittest
from pathlib import Path

# Ensure paths are configured
current_dir = Path(__file__).resolve().parent.parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from fastapi.testclient import TestClient
from app.main import app
from app.core.sql_guard import validate_sql_safety, is_safe_query, strip_sql_comments
from app.core.data_profiler import (
    DatasetProfiler,
    clean_identifier,
    try_parse_numeric_string,
    detect_date_string
)

client = TestClient(app)


class TestSQLGuard(unittest.TestCase):
    """Tests for SQL Guard security and injection prevention."""

    def test_sql_guard_valid_queries(self):
        valid_queries = [
            "SELECT * FROM users;",
            "SELECT id, name, email FROM customers WHERE status = 'ACTIVE' LIMIT 10",
            "WITH monthly_sales AS (SELECT month, SUM(amount) AS total FROM sales GROUP BY month) SELECT * FROM monthly_sales",
            "SELECT a.id, b.name FROM table_a a JOIN table_b b ON a.id = b.a_id WHERE a.created_at >= '2026-01-01'",
            "EXPLAIN SELECT count(*) FROM orders"
        ]
        for q in valid_queries:
            safe, reason = validate_sql_safety(q)
            self.assertTrue(safe, f"Expected safe query '{q}' but got rejected: {reason}")
            self.assertTrue(is_safe_query(q))

    def test_sql_guard_blocked_destructive_statements(self):
        destructive_queries = [
            "DROP TABLE users;",
            "DROP DATABASE production;",
            "TRUNCATE TABLE logs;",
            "DELETE FROM customers WHERE id = 1;",
            "UPDATE accounts SET balance = 0;",
            "INSERT INTO users (name, role) VALUES ('admin', 'super');",
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN;",
            "CREATE TABLE backdoor (id INT);",
            "GRANT ALL PRIVILEGES ON *.* TO 'hacker'@'%';",
            "EXEC xp_cmdshell('dir');",
            "SELECT * FROM users INTO OUTFILE '/tmp/dump.txt';"
        ]
        for q in destructive_queries:
            safe, reason = validate_sql_safety(q)
            self.assertFalse(safe, f"Expected destructive query '{q}' to be blocked, but it passed!")
            self.assertFalse(is_safe_query(q))

    def test_sql_guard_blocked_injection_vectors(self):
        injection_queries = [
            "SELECT * FROM users; DROP TABLE accounts;",
            "SELECT 1; TRUNCATE TABLE users;",
            "SELECT 1; UPDATE users SET role = 'admin';",
            "SELECT * FROM orders; DELETE FROM orders;"
        ]
        for q in injection_queries:
            safe, reason = validate_sql_safety(q)
            self.assertFalse(safe, f"Expected stacked injection '{q}' to be blocked!")

    def test_strip_sql_comments(self):
        self.assertEqual(strip_sql_comments("SELECT 1 -- this is a comment\nWHERE 1=1"), "SELECT 1 WHERE 1=1")
        self.assertEqual(strip_sql_comments("SELECT /* multi line comment */ id FROM users"), "SELECT id FROM users")


class TestDataProfiler(unittest.TestCase):
    """Tests for Tabular Data Profiler and semantic type inference."""

    def test_clean_identifier(self):
        self.assertEqual(clean_identifier("Total loan outstanding amount"), "total_loan_outstanding_amount")
        self.assertEqual(clean_identifier("App user ID"), "app_user_id")
        self.assertEqual(clean_identifier("123_invalid_start"), "col_123_invalid_start")
        self.assertEqual(clean_identifier("Charges ($) / Total %"), "charges_total")
        self.assertEqual(clean_identifier(""), "unnamed_column")

    def test_numeric_parsing(self):
        self.assertEqual(try_parse_numeric_string("$1,250.50"), 1250.50)
        self.assertEqual(try_parse_numeric_string("₹50,000"), 50000)
        self.assertEqual(try_parse_numeric_string("15.5%"), 0.155)
        self.assertEqual(try_parse_numeric_string("(100.00)"), -100.00)
        self.assertIsNone(try_parse_numeric_string("N/A"))
        self.assertIsNone(try_parse_numeric_string("invalid_text"))

    def test_date_detection(self):
        d1 = detect_date_string("30-06-2026")
        self.assertIsNotNone(d1)
        self.assertEqual(d1[0], "DD-MM-YYYY")
        self.assertEqual(d1[1], "2026-06-30")

        d2 = detect_date_string("2026-06-30")
        self.assertIsNotNone(d2)
        self.assertEqual(d2[0], "YYYY-MM-DD")
        self.assertEqual(d2[1], "2026-06-30")

        d3 = detect_date_string("28-Jul-2026")
        self.assertIsNotNone(d3)
        self.assertEqual(d3[0], "DD-Mon-YYYY")
        self.assertEqual(d3[1], "2026-07-28")

        self.assertIsNone(detect_date_string("not_a_date"))


class TestAPIEndpoints(unittest.TestCase):
    """Tests for FastAPI endpoints."""

    def test_health_check_endpoint(self):
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("version", data)
        self.assertIn("database", data)
        self.assertIn("llm", data)

    def test_system_info_endpoint(self):
        response = client.get("/api/v1/system/info")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("database", data)
        self.assertIn("dialect", data)
        self.assertIn("active_model", data)

    def test_chat_lifecycle_endpoints(self):
        # 1. Create chat
        create_res = client.post("/api/v1/chats", json={"title": "Test Production Chat"})
        self.assertEqual(create_res.status_code, 201)
        chat = create_res.json()
        chat_id = chat["id"]
        self.assertEqual(chat["title"], "Test Production Chat")

        # 2. List chats
        list_res = client.get("/api/v1/chats")
        self.assertEqual(list_res.status_code, 200)
        chats = list_res.json()
        self.assertTrue(any(c["id"] == chat_id for c in chats))

        # 3. Rename chat
        rename_res = client.put(f"/api/v1/chats/{chat_id}", json={"title": "Renamed Production Chat"})
        self.assertEqual(rename_res.status_code, 200)
        self.assertEqual(rename_res.json()["title"], "Renamed Production Chat")

        # 4. Delete chat
        del_res = client.delete(f"/api/v1/chats/{chat_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["status"], "success")

        # 5. Verify deleted
        get_res = client.get(f"/api/v1/chats/{chat_id}")
        self.assertEqual(get_res.status_code, 404)

    def test_dataset_list_and_profile_endpoint(self):
        list_res = client.get("/api/v1/datasets")
        self.assertEqual(list_res.status_code, 200)
        data = list_res.json()
        self.assertIn("datasets", data)

        datasets = data["datasets"]
        if datasets:
            sample_file = datasets[0]["file_name"]
            prof_res = client.post("/api/v1/datasets/profile", json={"file_name": sample_file, "sample_size": 100})
            self.assertEqual(prof_res.status_code, 200)
            prof_data = prof_res.json()
            self.assertEqual(prof_data["status"], "success")
            self.assertGreater(len(prof_data["tables"]), 0)
            self.assertIn("llm_markdown", prof_data)

    def test_connection_test_endpoint(self):
        test_res = client.post("/api/v1/connections/test", json={"db_type": "sqlite", "database_name": "app.db"})
        self.assertEqual(test_res.status_code, 200)
        data = test_res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["dialect"], "sqlite")

    def test_schema_endpoint(self):
        schema_res = client.get("/api/v1/schema")
        self.assertEqual(schema_res.status_code, 200)
        data = schema_res.json()
        self.assertIn("schema", data)
        self.assertIn("database", data)


if __name__ == "__main__":
    unittest.main()
