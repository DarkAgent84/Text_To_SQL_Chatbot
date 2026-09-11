# Enterprise Text-to-SQL Chatbot

An enterprise-ready, modular FastAPI application that dynamically inspects relational database schemas (PostgreSQL, MySQL, SQLite) with **exact data types**, generates accurate SQL queries using **Google Gemini AI**, executes them safely with read-only guardrails, and provides plain-English executive summaries.

---

## 🚀 Key Features

- **Multi-Database Support**: Connect to **PostgreSQL**, **MySQL**, or **SQLite** databases dynamically.
- **Dynamic Schema Reflection**: Inspects connected databases in real-time, extracting exact table names, precise column data types (`VARCHAR`, `INTEGER`, `DECIMAL`, `DATE`, `TIMESTAMP`, etc.), Primary Keys, and Foreign Keys.
- **Database Connection Manager Web UI (`/connections.html`)**:
  - Configure connections with a unique Reference Name (Alias).
  - ⚡ **Live Test Connection**: Tests credentials, measures latency, and discovers preview tables.
  - Save, edit, delete, and switch active databases with a single click.
- **AI Chatbot Dashboard (`/`)**:
  - Natural language questions to SQL generation.
  - Live **Active Database Switcher Dropdown** in the header.
  - LLM Self-Correction Loop for automatic query error recovery.
  - Visual SQL query drawer and tabular execution results.
  - Plain-English business summaries.
- **SQL Security Guard**: AST and regex guardrails permitting only read-only `SELECT` and `WITH ... SELECT` queries while strictly blocking any modifying statements.

---

## 📂 Project Structure

```
Text_To_SQL_Chatbot/
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore rules
├── README.md                 # Project documentation
├── requirements.txt          # Python dependencies
├── app.db                    # SQLite metadata store for chats and saved connections
│
├── app/                      # Main application package
│   ├── config.py             # Application settings & Gemini configuration
│   ├── main.py               # FastAPI entry point & route mounting
│   │
│   ├── api/                  # API layer
│   │   ├── endpoints.py      # Route handlers (/ask, /system-info, /connections)
│   │   └── schemas.py        # Pydantic request & response models
│   │
│   ├── core/                 # Core logic & database engines
│   │   ├── database.py       # Metadata engine, dynamic target engine & live tester
│   │   ├── db_schema.py      # Dynamic schema extractor with exact data types
│   │   ├── models.py         # SQLAlchemy models (Chat, Message, DatabaseConnection)
│   │   └── sql_guard.py      # Read-only SQL safety validator
│   │
│   └── services/             # External service integrations
│       └── llm_service.py    # Google Gemini client, prompt engine & self-correction
│
├── static/                   # Frontend web application (Vanilla HTML/CSS/JS)
│   ├── index.html            # Main Chatbot Dashboard
│   ├── app.js                # Chat controller & profile switcher
│   ├── connections.html      # Database Connection Manager
│   ├── connections.js        # Connection form & profile manager
│   └── styles.css            # Dark glassmorphism design system
│
└── tests/                    # Automated test suite
    └── test_all.py           # End-to-end verification tests
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
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

---

## 🌐 Web Interfaces

- **Chatbot Dashboard**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Database Connection Manager**: [http://127.0.0.1:8000/connections.html](http://127.0.0.1:8000/connections.html)
- **Interactive Swagger API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Running Automated Tests

```powershell
.\venv\Scripts\python.exe tests/test_all.py
```
