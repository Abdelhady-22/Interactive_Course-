# Interactive Course Platform

AI-powered layout director for interactive educational courses. An instructor records a video, you provide a structured script with keywords and visual assets, and a hybrid AI agent (rule engine + CrewAI/LiteLLM) decides the optimal screen layout for each segment.

## Architecture

```
Script + Keywords + Assets
        ↓
  ┌─────────────┐
  │ Rule Engine  │ ← 5 rules for obvious cases (free, instant)
  └──────┬──────┘
         │ no match?
         ↓
  ┌─────────────┐
  │ CrewAI Agent │ ← Layout Director persona via LiteLLM
  └──────┬──────┘
         ↓
  ┌─────────────┐
  │  Validation  │ ← Pydantic schema enforcement
  └──────┬──────┘
         ↓
   Layout Decisions → Editor Review → Approve → Publish → Learner Playback
```

## Prerequisites

- **Python 3.11+**
- **PostgreSQL** running locally
- **LLM Provider** — one of:
  - [Ollama](https://ollama.ai) (local, free) — recommended for development
  - Groq, Cohere, OpenAI, Anthropic (cloud) — via [LiteLLM](https://docs.litellm.ai)

## Setup Instructions

### Step 1: Clone and Install

```bash
# Navigate to project directory
cd d:\interactive

# Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS/Linux

# Install all dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
# Copy the example environment file
copy .env.example .env

# Edit .env with your settings:
```

Edit `.env` with your database URL and LLM provider:

```ini
# Database — change password and database name as needed
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/interactive_course

# LLM — Option A: Ollama (local, free)
LLM_MODEL=ollama/llama3
LLM_API_BASE=http://localhost:11434

# LLM — Option B: Groq (fast, free tier available)
# LLM_MODEL=groq/llama-3.1-70b-versatile
# LLM_API_KEY=your-groq-api-key

# LLM — Option C: OpenAI
# LLM_MODEL=gpt-4o
# LLM_API_KEY=your-openai-key
```

### Step 3: Create the Database

```bash
# Create the PostgreSQL database
createdb interactive_course

# Generate and run migrations
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

### Step 4: Seed Mock Data

```bash
python -m mock_data.seed_db
```

This prints the **course ID** — copy it for the next step.

### Step 5: Start the Server

```bash
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for the Swagger UI.

### Step 6: Run the AI Agent

Using the Swagger UI or curl:

```bash
# 1. Process the course (run AI agent on all 6 paragraphs)
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/process"

# 2. View the decisions
curl "http://localhost:8000/api/courses/{COURSE_ID}/decisions"

# 3. Approve all decisions
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/approve-all"

# 4. Publish the course
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/publish"

# 5. Get the final playback data (for the frontend player)
curl "http://localhost:8000/api/courses/{COURSE_ID}/playback"
```

### Step 7: Run Tests

```bash
# All tests
pytest tests/ -v

# Rule engine tests only
pytest tests/test_agent_rules.py -v

# API tests only
pytest tests/test_api.py -v
```

## API Reference

### Course Management
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/courses/` | Create a course |
| `GET` | `/api/courses/` | List all courses |
| `GET` | `/api/courses/{id}` | Get course details |
| `PATCH` | `/api/courses/{id}` | Update course metadata |
| `POST` | `/api/courses/{id}/upload-video` | Upload video file |

### Paragraph Management
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/courses/{id}/paragraphs/` | Bulk import paragraphs (replaces existing) |
| `GET` | `/api/courses/{id}/paragraphs/` | List all paragraphs |

### Asset Management
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/courses/{id}/assets/` | Upload single asset (multipart) |
| `POST` | `/api/courses/{id}/assets/bulk` | Bulk create assets (JSON) |
| `GET` | `/api/courses/{id}/assets/` | List all assets |
| `DELETE` | `/api/courses/{id}/assets/{asset_id}` | Delete an asset |

### Agent & Decisions
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/courses/{id}/process` | Run AI agent on all paragraphs |
| `GET` | `/api/courses/{id}/decisions` | Get all layout decisions |
| `PUT` | `/api/decisions/{id}` | Override a decision (human editor) |
| `POST` | `/api/decisions/{id}/rerun` | Re-run agent on one paragraph |
| `POST` | `/api/decisions/{id}/approve` | Approve a single decision |
| `POST` | `/api/courses/{id}/approve-all` | Approve all decisions |
| `POST` | `/api/courses/{id}/publish` | Publish course (requires all approved) |
| `GET` | `/api/courses/{id}/playback` | Get playback JSON for frontend |

## Project Structure

```
interactive/
├── app/
│   ├── main.py              # FastAPI entry point + CORS + routers
│   ├── config.py            # Settings from .env (pydantic-settings)
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models/              # SQLAlchemy models
│   │   ├── course.py        # Course (status: draft→processing→reviewed→published)
│   │   ├── paragraph.py     # Paragraph (timestamped script segment)
│   │   ├── asset.py         # Asset (image, formula, chart, diagram, etc.)
│   │   └── decision.py      # Decision (agent output per paragraph)
│   ├── schemas/             # Pydantic validation
│   │   ├── course.py        # CourseCreate, CourseResponse, CourseUpdate
│   │   ├── paragraph.py     # ParagraphBulkCreate, ParagraphResponse
│   │   ├── asset.py         # AssetCreate, AssetResponse
│   │   └── decision.py      # DecisionOutput, DecisionOverride, PlaybackData
│   ├── api/                 # FastAPI route handlers
│   │   ├── courses.py       # CRUD + video upload
│   │   ├── paragraphs.py    # Bulk import from STT JSON
│   │   ├── assets.py        # Upload + bulk create
│   │   └── agent.py         # Process, override, approve, publish, playback
│   ├── agent/               # Hybrid AI agent
│   │   ├── rules.py         # 5 deterministic rules with relevance filtering
│   │   ├── prompts.py       # System prompt (8 layout modes + output schema)
│   │   ├── llm_client.py    # LiteLLM multi-provider wrapper
│   │   └── engine.py        # Orchestrator: rules → CrewAI → direct LLM → fallback
│   └── services/            # Business logic
│       ├── course_service.py
│       └── agent_service.py
├── alembic/                 # Database migrations
├── mock_data/
│   ├── sample_course.json   # 6 paragraphs + 6 assets (chemistry course)
│   └── seed_db.py           # Database seeder
├── tests/
│   ├── test_agent_rules.py  # Rule engine unit tests
│   └── test_api.py          # API integration tests (SQLite in-memory)
├── .env / .env.example      # Environment configuration
├── requirements.txt         # Python dependencies
├── alembic.ini              # Alembic config
└── README.md
```

## Key Design Decisions

1. **Script is the source of truth** — STT is only for timestamp alignment
2. **Text-only LLM input** — No video/image files sent to LLM; assets described in text
3. **Human-in-the-loop** — Every decision reviewed by editor before publication
4. **Hybrid agent** — Rules handle obvious cases (fast, free); LLM handles ambiguous ones
5. **Relevant asset filtering** — Rules only consider assets relevant to each paragraph, not all course assets
