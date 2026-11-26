"""
Root level wrapper for tests/test_sql_guard.py
"""
from tests.test_sql_guard import test_sql_guard

if __name__ == "__main__":
    success = test_sql_guard()
    if not success:
        exit(1)