# Interactive Course Platform

AI-powered layout director for interactive educational courses. An instructor records a video, you provide a structured script with keywords and visual assets, and a hybrid AI agent decides the optimal screen layout for each segment — with **cross-paragraph intelligence** for visual continuity.

## Architecture

```
Script + Keywords + Assets
        ↓
  ┌──────────────────┐
  │ Sequence Analyzer │ ← Groups consecutive paragraphs, detects pinning sequences
  └───────┬──────────┘
          ↓
  ┌─────────────┐
  │ Rule Engine  │ ← 6 context-aware rules (free, instant)
  └──────┬──────┘
         │ no match?
         ↓
  ┌─────────────┐
  │ CrewAI Agent │ ← Layout Director + prev 3 decisions as context
  │  ┌────────┐  │
  │  │LiteLLM │  │ ← Provider layer (Ollama, GPT, Claude, Groq...)
  │  └────────┘  │
  └──────┬──────┘
         ↓
  ┌──────────────────┐
  │ Continuity Apply  │ ← Pin instructor position across asset sequences
  └───────┬──────────┘
         ↓
   Layout Decisions → Editor Review → Approve → Publish → Learner Playback
```

- **CrewAI** = the agent framework (structured agent with role/goal/task)
- **LiteLLM** = the provider layer inside CrewAI (swap between Ollama, GPT, Claude, Groq via `.env`)
- **Sequence Analyzer** = pre-processes paragraphs for cross-paragraph continuity

## 14 Layout Modes

| # | Mode | Description |
|---|------|-------------|
| 1 | `instructor_only` | Instructor 100% |
| 2 | `board_only` | Board 100%, no instructor |
| 3 | `board_dominant` | Board 70%, instructor PiP |
| 4 | `instructor_dominant` | Instructor 70%, small overlay |
| 5 | `split_50_50` | Equal split |
| 6 | `split_60_40` | Board 60%, instructor 40% |
| 7 | `instructor_pip` | Content 100%, instructor 15% PiP |
| 8 | `picture_in_picture_large` | Content 100%, instructor 30% PiP |
| 9 | `instructor_behind_board` | Semi-transparent instructor behind board |
| 10 | `overlay_floating` | Instructor 100%, small floating asset |
| 11 | `board_with_side_strip` | Board center, instructor side strip |
| 12 | `multi_asset_grid` | Multiple assets in grid, instructor PiP |
| 13 | `fullscreen_asset` | Single asset 100%, no instructor |
| 14 | `stacked_vertical` | Instructor top, board bottom |

## Prerequisites

- **Python 3.11+**
- **PostgreSQL** running locally
- **LLM Provider** — one of:
  - [Ollama](https://ollama.ai) (local, free) — recommended for development
  - Groq, Cohere, OpenAI, Anthropic (cloud) — via [LiteLLM](https://docs.litellm.ai)

## Setup Instructions

### Step 1: Clone and Install

```bash
cd d:\Interactive_Course-

python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### Step 2: Configure Environment

```bash
copy .env.example .env
```

Edit `.env`:

```ini
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/interactive_course

# Ollama (local, free)
LLM_MODEL=ollama/llama3
LLM_API_BASE=http://localhost:11434

# Or Groq / OpenAI / Claude — just change LLM_MODEL and LLM_API_KEY
```

### Step 3: Create the Database

```bash
createdb interactive_course
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

### Step 4: Seed Mock Data

```bash
python -m mock_data.seed_db
```

### Step 5: Start the Server

```bash
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for Swagger UI.

### Step 6: Run the AI Agent

```bash
# Process all 10 paragraphs (sequence analyzer + rules + CrewAI)
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/process"

# View decisions (check pinning sequences!)
curl "http://localhost:8000/api/courses/{COURSE_ID}/decisions"

# Approve all → Publish → Get playback data
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/approve-all"
curl -X POST "http://localhost:8000/api/courses/{COURSE_ID}/publish"
curl "http://localhost:8000/api/courses/{COURSE_ID}/playback"
```

### Step 7: Run Tests

```bash
pytest tests/ -v
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
| `POST` | `/api/courses/{id}/paragraphs/` | Bulk import paragraphs |
| `GET` | `/api/courses/{id}/paragraphs/` | List all paragraphs |

### Asset Management
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/courses/{id}/assets/` | Upload single asset |
| `POST` | `/api/courses/{id}/assets/bulk` | Bulk create assets |
| `GET` | `/api/courses/{id}/assets/` | List all assets |
| `DELETE` | `/api/courses/{id}/assets/{asset_id}` | Delete an asset |

### Agent & Decisions
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/courses/{id}/process` | Run AI agent on all paragraphs |
| `GET` | `/api/courses/{id}/decisions` | Get all layout decisions |
| `PUT` | `/api/decisions/{id}` | Override a decision |
| `POST` | `/api/decisions/{id}/rerun` | Re-run agent on one paragraph |
| `POST` | `/api/decisions/{id}/approve` | Approve a single decision |
| `POST` | `/api/courses/{id}/approve-all` | Approve all decisions |
| `POST` | `/api/courses/{id}/publish` | Publish course |
| `GET` | `/api/courses/{id}/playback` | Get playback JSON for frontend |

## Project Structure

```
Interactive_Course-/
├── app/
│   ├── main.py              # FastAPI entry point + CORS
│   ├── config.py            # Settings from .env
│   ├── database.py          # SQLAlchemy engine + session
│   ├── models/              # SQLAlchemy models (Course, Paragraph, Asset, Decision)
│   ├── schemas/             # Pydantic validation (with PositionContinuity)
│   ├── api/                 # 16 REST endpoints
│   ├── agent/
│   │   ├── sequence_analyzer.py  # Cross-paragraph grouping + pinning hints
│   │   ├── rules.py              # 6 context-aware deterministic rules
│   │   ├── prompts.py            # 14 layout modes + continuity instructions
│   │   ├── llm_client.py         # LiteLLM config for CrewAI
│   │   └── engine.py             # Orchestrator: sequences → rules → CrewAI
│   └── services/
├── mock_data/
│   ├── sample_course.json   # 10 paragraphs + 8 assets (chemistry course)
│   └── seed_db.py
├── tests/
│   ├── test_agent_rules.py  # Rule engine + sequence analyzer tests
│   └── test_api.py          # API integration tests
├── alembic/
├── .env / .env.example
├── requirements.txt
└── README.md
```

## Key Design Decisions

1. **Script is the source of truth** — STT is only for timestamp alignment
2. **Text-only LLM input** — No video/image files sent to LLM; assets described in text
3. **Human-in-the-loop** — Every decision reviewed by editor before publication
4. **Hybrid agent** — Rules handle obvious cases (fast, free); LLM handles ambiguous ones
5. **Cross-paragraph continuity** — Sequence analyzer detects asset-heavy runs and pins instructor position
6. **Asset-driven pinning** — Asset type determines how to pin (full screen for detailed images, PiP for formulas)
