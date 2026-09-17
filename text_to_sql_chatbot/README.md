# Enterprise Text-to-SQL AI Chatbot & Data Intelligence Platform

An enterprise-ready, production-hardened FastAPI platform that dynamically inspects relational database schemas (PostgreSQL, MySQL, SQLite) and tabular datasets (Excel, CSV, TSV, JSON), infers exact semantic data types (`DATE`, `CURRENCY`, `IDENTIFIER`, `CATEGORICAL`), generates accurate SQL queries using **Google Gemini AI**, executes them safely with AST read-only guardrails, and provides plain-English executive summaries and interactive visual charts.

---

## 🚀 Key Production Features

- **Multi-Database Dynamic Switching**: Connect to **PostgreSQL**, **MySQL**, or **SQLite** databases dynamically at runtime without restarting the server.
- **Dataset Ingestion & Semantic Profiler (`/datasets.html` & `data_profiler.py`)**:
  - Drag & Drop upload for `.xlsx`, `.xls`, `.csv`, `.tsv`, and `.json` datasets.
  - Deep semantic type inference for `DATE` (`DD-MM-YYYY`), `CURRENCY` (`DECIMAL(15,2)`), `IDENTIFIER` (LAN, PAN, Telecaller ID), `CATEGORICAL` discrete enums, and `COORDINATE` lat/lon.
  - Generates LLM Markdown schema context and SQL DDL statements.
  - One-click ingestion into database tables with normalized SQL column names.
- **AI Text-to-SQL Engine with Self-Correction**:
  - Dialect-aware prompts (`strftime` for SQLite, `EXTRACT/ILIKE` for PostgreSQL, `DATE_FORMAT` for MySQL).
  - Automated Multi-Model Fallback Ladder (`gemini-2.5-flash`, `gemini-3.5-flash`, `gemini-3.6-flash`, etc.).
  - Self-Correction loop that automatically fixes execution syntax errors.
  - Natural language executive summary of query results.
  - Chart type recommendation engine (Bar, Line, Pie, Doughnut).
- **Security & SQL Guard**:
  - AST-level validation blocking destructive statements (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `ALTER`, `GRANT`).
  - Blocks stacked / chained injection attacks (`;`).
  - Strips comments to prevent injection hiding.
- **Database Connection Manager Web UI (`/connections.html`)**:
  - Test credentials and latency before saving.
  - Save, edit, delete, and switch active databases with a single click.
- **Observability & Health Checks**:
  - `/health/live` and `/health/ready` endpoints with database latency ping.
  - Request ID correlation (`X-Request-ID`) and response time tracking (`X-Response-Time-Ms`).
  - Structured application logging.

---

## 📂 Project Structure

```
Text_To_SQL_Chatbot/
├── data_profiler.py          # Standalone CLI Data Profiler & Ingestion Tool
├── .env.example              # Environment variables template
├── requirements.txt          # Python dependencies
├── app.db                    # SQLite metadata store for chats and saved connections
│
├── text_to_sql_chatbot/
│   ├── data_profiler.py      # App copy of the profiler CLI
│   ├── app/                  # Main application package
│   │   ├── config.py         # Production settings & Gemini configuration
│   │   ├── main.py           # FastAPI entry point, middlewares & lifecycle
│   │   │
│   │   ├── api/              # REST API layer
│   │   │   ├── endpoints.py  # Routes (/chats, /ask, /connections, /datasets, /health)
│   │   │   └── schemas.py    # Pydantic request & response models
│   │   │
│   │   ├── core/             # Core database & profiler engines
│   │   │   ├── database.py   # Thread-safe engine switcher, connection pooling
│   │   │   ├── db_schema.py  # Dynamic schema extractor with exact data types
│   │   │   ├── models.py     # SQLAlchemy ORM models (Chat, Message, DatabaseConnection)
│   │   │   ├── sql_guard.py  # Read-only SQL safety validator
│   │   │   └── data_profiler.py # Tabular data understanding & semantic inference
│   │   │
│   │   └── services/         # AI service integrations
│   │       └── llm_service.py # Gemini client, fallback ladder & self-correction
│   │
│   ├── data/                 # Sample reports (Excel, CSV) and SQL schemas
│   │
│   ├── static/               # Frontend web application (Vanilla HTML/CSS/JS)
│   │   ├── index.html        # Main Chatbot Dashboard
│   │   ├── app.js            # Chat controller & profile switcher
│   │   ├── datasets.html     # Dataset Ingestion & Profiler UI
│   │   ├── datasets.js       # Dataset upload and ingestion controller
│   │   ├── connections.html  # Database Connection Manager
│   │   ├── connections.js    # Connection form & profile manager
│   │   ├── dashboard.html    # Collections & Loan Analytics Dashboard
│   │   └── styles.css        # Dark glassmorphism design system
│   │
│   └── tests/                # Automated test suite
│       └── test_all.py       # Comprehensive unit & integration tests
```

---

## ⚙️ Setup & Installation

### 1. Prerequisites
- Python 3.10+
- A Google Gemini API Key

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file from `.env.example`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

### 4. Start the Application Server
```powershell
uvicorn app.main:app --reload --port 8000
```

---

## 🛠️ CLI Data Profiler Usage

You can run `data_profiler.py` directly from the command line on any tabular dataset:

```bash
# 1. Print colorized column summary table
python data_profiler.py --file "text_to_sql_chatbot/data/Dynamic Collection Done MIS Report (1).xlsx"

# 2. Generate LLM Prompt Markdown schema
python data_profiler.py --file "text_to_sql_chatbot/data/SOA Master Export Report-28-Jul-2026 (2).csv" --format markdown

# 3. Export JSON schema dictionary
python data_profiler.py --file "text_to_sql_chatbot/data/SOA Master Export Report-28-Jul-2026 (2).csv" --to-json schema.json

# 4. Generate SQL CREATE TABLE DDL
python data_profiler.py --file "text_to_sql_chatbot/data/Dynamic Collection Done MIS Report (1).xlsx" --format ddl

# 5. Ingest file directly into SQLite database
python data_profiler.py --file "text_to_sql_chatbot/data/Dynamic Collection Done MIS Report (1).xlsx" --to-sqlite app.db --table-name collection_mis
```

---

## 🌐 Web Interfaces

- **AI Chatbot**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Dataset Ingestion & Profiler**: [http://127.0.0.1:8000/datasets.html](http://127.0.0.1:8000/datasets.html)
- **Database Connection Manager**: [http://127.0.0.1:8000/connections.html](http://127.0.0.1:8000/connections.html)
- **Analytics Dashboard**: [http://127.0.0.1:8000/dashboard.html](http://127.0.0.1:8000/dashboard.html)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Running Automated Tests

```powershell
python text_to_sql_chatbot/tests/test_all.py
```
*(All 13 unit and integration tests covering security, profiling, database switching, and API endpoints).*
