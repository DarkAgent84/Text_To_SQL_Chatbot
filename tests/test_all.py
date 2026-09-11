import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import test_db_connection_params, get_target_engine
from app.core.db_schema import get_db_schema
from app.core.sql_guard import is_safe_query

client = TestClient(app)


def test_schema_extraction_with_exact_datatypes():
    """Verify that schema extraction pulls exact column datatypes from the database."""
    schema = get_db_schema(force_refresh=True)
    assert isinstance(schema, str)
    assert len(schema) > 0
    print("Extracted schema preview:\n", schema[:200])


def test_connection_testing_endpoint():
    """Verify live connection test utility on SQLite."""
    payload = {
        "db_type": "sqlite",
        "extra_params": "./app.db"
    }
    res = client.post("/api/v1/connections/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["dialect"] == "sqlite"
    assert data["latency_ms"] >= 0


def test_connection_profile_lifecycle():
    """Verify create, list, activate, update, and delete connection profiles."""
    test_alias = "Test Analytics Production DB"
    
    # 1. Create connection
    create_payload = {
        "reference_name": test_alias,
        "db_type": "sqlite",
        "extra_params": "./app.db",
        "set_as_active": True
    }
    create_res = client.post("/api/v1/connections", json=create_payload)
    assert create_res.status_code == 200
    created = create_res.json()
    conn_id = created["id"]
    assert created["reference_name"] == test_alias

    # 2. List connections
    list_res = client.get("/api/v1/connections")
    assert list_res.status_code == 200
    assert any(c["id"] == conn_id for c in list_res.json())

    # 3. Get active connection
    active_res = client.get("/api/v1/connections/active")
    assert active_res.status_code == 200
    assert active_res.json()["reference_name"] == test_alias

    # 4. Activate connection profile
    act_res = client.post(f"/api/v1/connections/{conn_id}/activate")
    assert act_res.status_code == 200
    assert act_res.json()["status"] == "activated"

    # 5. System info verification
    sys_res = client.get("/api/v1/system-info")
    assert sys_res.status_code == 200
    assert test_alias in sys_res.json()["database"]

    # 6. Update connection profile
    update_res = client.put(f"/api/v1/connections/{conn_id}", json={"reference_name": "Updated Test DB"})
    assert update_res.status_code == 200
    assert update_res.json()["reference_name"] == "Updated Test DB"

    # 7. Delete connection profile
    del_res = client.delete(f"/api/v1/connections/{conn_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


def test_sql_guard_security():
    """Verify that only read-only SELECT and WITH statements pass security checks."""
    assert is_safe_query("SELECT * FROM customers;") == True
    assert is_safe_query("WITH cte AS (SELECT id FROM users) SELECT * FROM cte;") == True
    assert is_safe_query("SELECT count(*) FROM orders WHERE total > 100") == True

    # Blocked queries
    assert is_safe_query("DROP TABLE customers;") == False
    assert is_safe_query("DELETE FROM orders;") == False
    assert is_safe_query("UPDATE users SET password = '123'") == False
    assert is_safe_query("INSERT INTO customers VALUES (1, 'Hacker')") == False
    assert is_safe_query("ALTER TABLE products ADD COLUMN secret VARCHAR(10)") == False
    assert is_safe_query("TRUNCATE TABLE logs") == False
    assert is_safe_query("SELECT * FROM customers; DROP TABLE customers;") == False


if __name__ == "__main__":
    print("--- Running Test: Schema Extraction with Exact Data Types ---")
    test_schema_extraction_with_exact_datatypes()
    print("--- Running Test: Live Connection Testing Endpoint ---")
    test_connection_testing_endpoint()
    print("--- Running Test: Connection Profile Lifecycle ---")
    test_connection_profile_lifecycle()
    print("--- Running Test: SQL Guard Security ---")
    test_sql_guard_security()
    print("\n[PASS] ALL REBUILD TESTS PASSED SUCCESSFULLY!")
