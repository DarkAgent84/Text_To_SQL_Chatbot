from sqlalchemy import inspect, text
from app.core.database import engine
from app.core.auto_ingest import auto_ingest_if_needed, IGNORED_TABLES

# Static fallback schema representation
STATIC_DB_SCHEMA = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(20),
    city VARCHAR(50),
    state VARCHAR(50),
    signup_date DATE,
    customer_segment VARCHAR(20),
    is_active INTEGER
);

CREATE TABLE suppliers (
    supplier_id INTEGER PRIMARY KEY,
    supplier_name VARCHAR(100),
    contact_email VARCHAR(100),
    city VARCHAR(50),
    country VARCHAR(50),
    rating DECIMAL(3,1),
    is_active INTEGER
);

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    category_name VARCHAR(100),
    parent_category VARCHAR(100),
    description VARCHAR(255)
);

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    employee_name VARCHAR(100),
    role VARCHAR(50),
    department VARCHAR(50),
    hire_date DATE,
    salary DECIMAL(10,2),
    manager_id INTEGER,
    FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR(100),
    category_id INTEGER,
    supplier_id INTEGER,
    price DECIMAL(10,2),
    stock_quantity INTEGER,
    is_active INTEGER,
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    employee_id INTEGER,
    order_date DATE,
    order_status VARCHAR(20),
    shipping_city VARCHAR(50),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    unit_price DECIMAL(10,2),
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    payment_date DATE,
    amount DECIMAL(10,2),
    payment_method VARCHAR(30),
    payment_status VARCHAR(20),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE shipments (
    shipment_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    carrier VARCHAR(50),
    shipment_date DATE,
    delivery_date DATE,
    shipment_status VARCHAR(20),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE reviews (
    review_id INTEGER PRIMARY KEY,
    product_id INTEGER,
    customer_id INTEGER,
    rating INTEGER,
    review_date DATE,
    review_comment VARCHAR(255),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
"""

_SCHEMA_CACHE = {}


def get_db_schema(user_question: str = "", force_refresh: bool = False) -> str:
    """
    Dynamically inspects the connected database engine (SQLite, MySQL, PostgreSQL)
    and constructs an ultra-compact schema representation tailored for token minimization,
    including column names, types, primary/foreign keys, and key categorical sample values.
    Caches schema in memory for sub-millisecond response times.
    """
    global _SCHEMA_CACHE
    engine_key = str(engine.url)
    if not force_refresh and engine_key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[engine_key]

    try:
        # Check and auto-ingest datasets if database user tables are missing
        auto_ingest_if_needed()

        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        
        user_tables = [t for t in table_names if t.lower() not in IGNORED_TABLES]
        
        if not user_tables:
            return STATIC_DB_SCHEMA

        compact_statements = []
        with engine.connect() as conn:
            for table in user_tables:
                columns = inspector.get_columns(table)
                pk_constraint = inspector.get_pk_constraint(table)
                pk_cols = set(pk_constraint.get("constrained_columns", []))
                fk_constraints = inspector.get_foreign_keys(table)

                col_parts = []
                for col in columns:
                    col_name = col["name"]
                    col_type = str(col["type"])
                    is_pk = col_name in pk_cols
                    
                    part = f"{col_name} {col_type}"
                    if is_pk:
                        part += " PK"

                    if any(c in col_name.lower() for c in ["bucket", "product", "status", "type", "mode", "category", "city", "segment"]):
                        try:
                            dialect = engine.dialect.name
                            q = "`" if dialect == "mysql" else '"'
                            sample_query = f"SELECT DISTINCT {q}{col_name}{q} FROM (SELECT {q}{col_name}{q} FROM {q}{table}{q} WHERE {q}{col_name}{q} IS NOT NULL LIMIT 100) sub LIMIT 3"
                            res = conn.execute(text(sample_query)).fetchall()
                            samples = [str(r[0]) for r in res if r[0] is not None and str(r[0]).strip() != ""]
                            if samples:
                                part += f" [eg: {', '.join(samples[:3])}]"
                        except Exception:
                            pass

                    col_parts.append(part)

                fk_parts = []
                for fk in fk_constraints:
                    referred_table = fk.get("referred_table")
                    constrained_cols = fk.get("constrained_columns", [])
                    referred_cols = fk.get("referred_columns", [])
                    if constrained_cols and referred_cols and referred_table:
                        c_col = ", ".join(constrained_cols)
                        r_col = ", ".join(referred_cols)
                        fk_parts.append(f"FK({c_col}->{referred_table}.{r_col})")

                table_str = f"Table `{table}`:\nColumns: " + ", ".join(col_parts)
                if fk_parts:
                    table_str += "\nConstraints: " + ", ".join(fk_parts)
                compact_statements.append(table_str)

        result_schema = "\n\n".join(compact_statements)
        _SCHEMA_CACHE[engine_key] = result_schema
        return result_schema
    except Exception as e:
        print(f"Warning: Dynamic schema reflection failed ({e}). Using static schema fallback.")
        return STATIC_DB_SCHEMA


