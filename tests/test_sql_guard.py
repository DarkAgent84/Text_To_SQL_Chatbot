import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.sql_guard import is_safe_query

test_cases = [
    ("SELECT * FROM customers; DROP TABLE customers;", False),
    ("WITH pune_customers AS (SELECT * FROM customers WHERE city = 'Pune') SELECT COUNT(*) FROM pune_customers", True),
    ("SELECT * FROM customers WHERE city = 'Adropland'", True),
    ("INSERT INTO customers (customer_name) VALUES ('Hacker')", False),
    ("DELETE FROM orders", False),
    ("UPDATE products SET price = 0", False),
    ("DROP TABLE reviews", False),
]

def test_sql_guard():
    all_passed = True
    for sql, expected in test_cases:
        result = is_safe_query(sql)
        status = "PASS" if result == expected else "FAIL"
        print(f"{status} | expected={expected} got={result} | {sql}")
        if result != expected:
            all_passed = False
    return all_passed

if __name__ == "__main__":
    success = test_sql_guard()
    if not success:
        sys.exit(1)
