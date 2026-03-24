# Quick Start — From Zero to Running

> **OS**: Windows (PowerShell). For Linux/macOS, swap `venv\Scripts\activate` → `source venv/bin/activate`.

---

## 1. Prerequisites

| Requirement | Install |
|-------------|---------|
| **Python 3.11+** | [python.org/downloads](https://www.python.org/downloads/) |
| **PostgreSQL 15+** | [postgresql.org/download](https://www.postgresql.org/download/) |
| **Ollama** (free local LLM) | [ollama.ai](https://ollama.ai) |

After installing Ollama, pull a model:
```bash
ollama pull llama3
```

---

## 2. Setup (one-time)

```powershell
# Navigate to project
cd d:\Interactive_Course-

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 3. Configure Environment

```powershell
# Create .env from template
copy .env.example .env
```

Edit `.env` — these are the only 3 values you need:

```ini
# Your PostgreSQL connection (change password if needed)
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/interactive_course

# Local Ollama (free, no API key needed)
LLM_MODEL=ollama/llama3
LLM_API_BASE=http://localhost:11434
```

> **Alternative LLM providers** (pick ONE):
> ```ini
> # Groq (fast, free tier)
> LLM_MODEL=groq/llama-3.1-70b-versatile
> LLM_API_KEY=your-groq-api-key
>
> # OpenAI
> LLM_MODEL=gpt-4o
> LLM_API_KEY=your-openai-key
>
> # Anthropic
> LLM_MODEL=anthropic/claude-3-sonnet
> LLM_API_KEY=your-anthropic-key
> ```

---

## 4. Create Database

Open **pgAdmin** or **psql** and run:

```sql
CREATE DATABASE interactive_course;
```

Or from PowerShell (if `psql` is in PATH):
```powershell
psql -U postgres -c "CREATE DATABASE interactive_course;"
```

---

## 5. Run Migrations

```powershell
# Generate migration from models
alembic revision --autogenerate -m "initial tables"

# Apply migration
alembic upgrade head
```

---

## 6. Seed Mock Data

```powershell
python -m mock_data.seed_db
```

**Copy the Course ID** from the output — you'll need it next.

Example output:
```
Created course: Introduction to Chemistry (ID: a1b2c3d4-...)
  Paragraph 0: Welcome to this course...
  Paragraph 1: Let's start with a real experiment...
  ...
  Asset: HCl zinc reaction photo (image)
  Asset: Zinc-HCl reaction equation (formula)
  ...
Seeding complete!
  Course ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 7. Start the Server

```powershell
uvicorn app.main:app --reload
```

Server runs at **http://localhost:8000**

- Swagger UI: **http://localhost:8000/docs**
- Health check: **http://localhost:8000/health**

---

## 8. Process the Course (Run AI Agent)

Replace `{COURSE_ID}` with the ID from step 6.

### Option A: Swagger UI (visual)

1. Open **http://localhost:8000/docs**
2. Find `POST /api/courses/{course_id}/process`
3. Click **Try it out**, paste your Course ID, click **Execute**
4. View the decisions with `GET /api/courses/{course_id}/decisions`

### Option B: curl (command line)

```powershell
# Make sure Ollama is running first!
# ollama serve   (if not already running)

# Process all 10 paragraphs
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/process"

# View decisions (check continuity.pin_instructor!)
curl "http://localhost:8000/api/courses/{COURSE_ID}/decisions"

# Approve all decisions
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/approve-all"

# Publish
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/publish"

# Get final playback JSON (for frontend player)
curl "http://localhost:8000/api/courses/{COURSE_ID}/playback"
```

---

## 9. Run Tests

```powershell
# All tests (no DB or LLM needed — uses SQLite in-memory)
pytest tests/ -v

# Rule engine + sequence analyzer tests only
pytest tests/test_agent_rules.py -v

# API tests only
pytest tests/test_api.py -v
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Make sure venv is activated: `venv\Scripts\activate` |
| `sqlalchemy.exc.OperationalError` | Check PostgreSQL is running and `DATABASE_URL` in `.env` is correct |
| `Connection refused` on LLM | Make sure Ollama is running: `ollama serve` |
| `alembic: command not found` | Activate venv first, or run: `python -m alembic upgrade head` |
| `database "interactive_course" does not exist` | Create it first: `psql -U postgres -c "CREATE DATABASE interactive_course;"` |
| Agent returns `FALLBACK` decisions | LLM might be slow/down. Check Ollama logs. Rule-based decisions should still work. |

---

## What to Expect

After processing, each paragraph gets a layout decision with:

```json
{
  "layout": { "mode": "board_dominant", "instructor": {...}, "board": {...} },
  "assets": [{ "name": "Zinc-HCl equation", "position": "board_center" }],
  "transition": { "type": "fade", "duration_ms": 400 },
  "continuity": {
    "pin_instructor": true,
    "pin_from_paragraph": "p_002",
    "sequence_note": "Paragraphs 2-4 form asset sequence"
  },
  "director_note": "Formula paragraph — board dominant for maximum visual clarity.",
  "confidence": 0.90,
  "decided_by": "rule"
}
```

Paragraphs 2-4 should show `pin_instructor: true` (instructor stays in same position across the asset sequence).
