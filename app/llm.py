import os
from dotenv import load_dotenv
from google import genai

load_dotenv()


def get_client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is missing or empty. "
            "Please add GEMINI_API_KEY=your_key_here to your .env file."
        )
    return genai.Client(api_key=key)

def test_connection():
    client = get_client()
    response = client.models.generate_content(
        model="gemini-3.7-flash",
        contents="Say hello in one short sentence.",
    )
    return response.text

SCHEMA = """
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

def generate_sql(question: str, history: str = "") -> str:
    client = get_client()
    prompt = f"""You are an expert SQL query generator for SQLite databases.
Given a database schema and a natural language question, generate ONLY the SQL query needed to answer it.
Do not include markdown code block formatting (e.g. ```sql), explanations, or anything other than the raw executable SQL query.

Rules:
- Use standard MySQL syntax and functions (e.g. YEAR(), DATE_FORMAT()).
- When joining tables, use explicit JOIN syntax with clear aliases.
- Use column names strictly as defined in the Schema below.

Schema:
{SCHEMA}

Previous conversation:
{history}

Question: {question}

SQL Query:"""

    response = client.models.generate_content(
        model="gemini-3.7-flash",
        contents=prompt,
    )
    sql = response.text.strip()
    
    # Strip markdown code blocks if the model included them despite instructions
    if sql.startswith("```"):
        lines = sql.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines).strip()

    return sql

MAX_ROWS_FOR_LLM = 50

def interpret_result(question: str, result: list) -> str:
    client = get_client()
    
    total_rows = len(result)
    if total_rows > MAX_ROWS_FOR_LLM:
        result_preview = result[:MAX_ROWS_FOR_LLM]
        result_str = f"{result_preview}\n... [Showing first {MAX_ROWS_FOR_LLM} of {total_rows} total rows]"
    else:
        result_str = str(result)

    prompt = f"""You are a helpful business intelligence assistant. A user asked a question, and a database query was run to answer it. Given the user's original question and the raw query results (Total records returned: {total_rows}), write a clear, natural-language answer.

Do not mention raw SQL, database internal schemas, or technical jargon. Provide a concise, plain English answer as if you were a helpful data analyst.

Question: {question}
Raw results: {result_str}

Answer:"""

    response = client.models.generate_content(
        model="gemini-3.7-flash",
        contents=prompt,
    )
    return response.text.strip()
