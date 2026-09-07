from app.sql_guard import is_safe_query

test_cases = [
    ("SELECT * FROM customers; DROP TABLE customers;", False),
    ("WITH pune_customers AS (SELECT * FROM customers WHERE city = 'Pune') SELECT COUNT(*) FROM pune_customers", True),
    ("SELECT * FROM customers WHERE city = 'Adropland'", True),
]

for sql, expected in test_cases:
    result = is_safe_query(sql)
    status = "PASS" if result == expected else "FAIL"
    print(f"{status} | expected={expected} got={result} | {sql}")