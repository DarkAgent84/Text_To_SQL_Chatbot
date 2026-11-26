# Enterprise Text-to-SQL Chatbot Backend

An enterprise-ready, modular FastAPI application that converts natural language business questions into executable SQL queries, runs them safely against a relational database (SQLite or MySQL), and provides natural-language business insights using Google Gemini AI.

---

## 🚀 Features

- **Natural Language to SQL**: Automatically generates valid SQL queries matching complex multi-table schemas using Google Gemini AI.
- **SQL Security Guard**: Built-in AST and regex guardrails preventing data-modifying (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`) or multi-statement SQL injection attacks.
- **Multi-Turn Chat History**: Preserves context across chat sessions for follow-up analytical questions.
- **Natural Language Data Interpretation**: Translates raw database query results into clear, concise business summaries.
- **Dual Database Support**: Supports local zero-config SQLite (`app.db`) and production-grade MySQL via environment configuration.
- **Automated Seeder & Benchmark**: Utility scripts for populating full 10-table datasets and running sequential evaluation benchmarks.

---

## 📂 Project Structure

```
Text_To_SQL_Chatbot/
├── .env.example              # Environment variables template
├── .gitignore                # Standard Git ignore configuration
├── README.md                 # Project documentation & usage guide
├── requirements.txt          # Python package dependencies
├── app.db                    # SQLite database instance
│
├── app/                      # Main application package
│   ├── __init__.py
│   ├── main.py               # FastAPI entry point & CORS configuration
│   ├── config.py             # Centralized application settings & env variables
│   │
│   ├── api/                  # API routing & Pydantic DTO schemas
│   │   ├── __init__.py
│   │   ├── endpoints.py      # Route handlers (/ask, /health)
│   │   └── schemas.py        # Pydantic request & response models
│   │
│   ├── core/                 # Business logic, database & security core
│   │   ├── __init__.py
│   │   ├── database.py       # Engine, SessionLocal & session dependencies
│   │   ├── db_schema.py      # SQL DDL schema for Gemini prompt context
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   └── sql_guard.py      # Read-only SQL safety validator
│   │
│   └── services/             # External service integrations
│       ├── __init__.py
│       └── llm_service.py    # Google Gemini client wrapper
│
├── data/                     # Raw CSV datasets & SQL DDL files
│   ├── categories.csv
│   ├── customers.csv
│   ├── employees.csv
│   ├── order_items.csv
│   ├── orders.csv
│   ├── payments.csv
│   ├── products.csv
│   ├── reviews.csv
│   ├── shipments.csv
│   ├── suppliers.csv
│   ├── text_to_sql_test_cases.csv
│   ├── schema.sql
│   └── schema_mysql.sql
│
├── scripts/                  # Administrative & seeder scripts
│   ├── load_dataset.py       # SQLite database seeder
│   └── load_dataset_mysql.py # MySQL database seeder
│
└── tests/                    # Tests and benchmark evaluation
    ├── __init__.py
    ├── evaluate.py           # Benchmark evaluation harness
    └── test_sql_guard.py     # SQL Guard unit tests
```

---

## 🛠️ Installation & Setup

### 1. Clone & Setup Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate on Windows PowerShell
.\venv\Scripts\Activate.ps1

# Activate on Linux/macOS
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root (or copy `.env.example`):

```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.7-flash

# Optional MySQL Configuration (Defaults to SQLite if omitted)
# MYSQL_USER=root
# MYSQL_PASSWORD=your_password
# MYSQL_HOST=localhost
# MYSQL_PORT=3306
# MYSQL_DB=text_to_sql_db
```

---

## 📊 Database Seeding

Populate the 10 relational tables (`customers`, `orders`, `products`, `employees`, etc.) with test datasets:

### SQLite (Default)
```bash
python scripts/load_dataset.py
```

### MySQL
```bash
python scripts/load_dataset_mysql.py
```

---

## 🏃 Running the Application

Start the FastAPI development server with Uvicorn:

```bash
uvicorn app.main:app --reload
```

The API will be available at:
- **Base URL**: `http://127.0.0.1:8000`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`

---

## 🔌 API Endpoints

### 1. Health Check
- **`GET /health`**
- **Response**: `{"status": "ok"}`

### 2. Ask Question (Text-to-SQL)
- **`POST /ask`**
- **Request Body**:
```json
{
  "question": "Which customer placed the highest number of orders in Pune?",
  "chat_id": 1
}
```

- **Success Response**:
```json
{
  "Chat Id": 1,
  "Question": "Which customer placed the highest number of orders in Pune?",
  "SQL Query": "SELECT c.customer_name, COUNT(o.order_id) AS order_count FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE c.city = 'Pune' GROUP BY c.customer_id ORDER BY order_count DESC LIMIT 1;",
  "SQL Results": [
    {
      "customer_name": "Rohan Sharma",
      "order_count": 5
    }
  ],
  "Answer": "Rohan Sharma placed the highest number of orders in Pune, with a total of 5 orders."
}
```

---

## 🧪 Testing & Evaluation

### Run SQL Guard Unit Tests
```bash
python tests/test_sql_guard.py
```

### Run Benchmark Evaluation
Evaluates model accuracy sequentially against benchmark test cases:

```bash
# Evaluate top 10 test cases
python tests/evaluate.py --limit 10

# Evaluate all test cases
python tests/evaluate.py --limit 0
```

Detailed results will be saved to `evaluation_report.json`.

---

## 🔒 Security & Safety

- **Read-Only Enforcement**: All generated SQL statements are strictly inspected before execution.
- **SQL Injection Prevention**: Any statement attempting `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, or multiple chained queries (`;) is blocked instantly.

---

## 📄 License

MIT License.
