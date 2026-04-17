# Setup & Changes Guide

## What Was Built

The original repo had only a Streamlit interface wired directly to the Anthropic Computer Use agent. Everything below was added on top of the existing `computer_use_demo/` package (which was **not modified**).

---

### New Directory Structure

```
computer-use-demo/
├── backend/                        ← NEW: entire FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   └── app/
│       ├── main.py                 ← FastAPI app, lifespan, CORS
│       ├── config.py               ← All env-var settings (pydantic-settings)
│       ├── database.py             ← Async SQLAlchemy engine + session factory
│       ├── models.py               ← Session + Message ORM models
│       ├── schemas.py              ← Pydantic request/response schemas
│       ├── core/
│       │   └── events.py           ← SSE event type constants
│       ├── services/
│       │   ├── session_manager.py  ← Spawns Xvfb/mutter/VNC per session, runs GC
│       │   └── agent_runner.py     ← Wraps sampling_loop(), writes DB + SSE queue
│       └── routers/
│           ├── sessions.py         ← CRUD: POST/GET/DELETE /sessions
│           ├── messages.py         ← POST /messages, GET /messages, GET /stream (SSE)
│           └── vnc.py              ← GET /vnc → returns noVNC URL
├── frontend/                       ← NEW: static HTML/JS/CSS UI
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── nginx.conf
├── postgres-init/
│   └── init.sql                    ← NEW: enables uuid-ossp extension
├── docker-compose.yml              ← NEW: db + backend + frontend services
├── .env.example                    ← NEW
├── .gitignore                      ← UPDATED: expanded from 4 lines to full coverage
├── CHANGELOG.md                    ← NEW
└── README.md                       ← REPLACED: full implementation docs
```

---

### Key Design Decisions

**Concurrency** — each session gets its own:
- Xvfb virtual display on a unique number (`:10`, `:11`, ...)
- mutter window manager on that display (required for Firefox to render)
- x11vnc + noVNC/websockify on a unique port pair
- `asyncio.Task` on the shared event loop (non-blocking, no fixed cap)
- `asyncio.Lock` that serialises messages *within* a session while other sessions run freely

**Real-time streaming** — Server-Sent Events (SSE) via `sse-starlette`. The agent loop pushes `text_delta`, `tool_use`, `tool_result`, `status`, and `done` events to a per-session `asyncio.Queue` which the SSE endpoint drains.

**Persistence** — PostgreSQL via async SQLAlchemy. Every message block (user, assistant text, tool calls, tool results) is stored as JSONB so the full Anthropic API message list can be reconstructed for multi-turn conversations.

**Idle GC** — a background task runs every 15 minutes and deletes sessions that have been idle longer than `SESSION_IDLE_TIMEOUT_MINUTES` (default 120).

---

## Prerequisites

### Docker (recommended)
- Docker Desktop 4.x or Docker Engine 24+ with Compose v2
- An Anthropic API key → https://console.anthropic.com/settings/keys

### Local (without Docker)
- Python 3.11+
- PostgreSQL 16 running locally
- `Xvfb`, `mutter`, `x11vnc`, `websockify` installed (Linux only — these are Linux display tools)
- The `computer_use_demo` package dependencies (see `computer_use_demo/requirements.txt`)

---

## Running with Docker Compose

### 1. Copy and fill the env file

```bash
cd computer-use-demo
cp .env.example .env
```

Open `.env` and set at minimum:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Everything else has working defaults.

### 2. Build and start

```bash
docker compose up --build
```

First build takes ~5–8 minutes (compiles Python, downloads noVNC). Subsequent starts are fast.

### 3. Open the UI

| What | URL |
|------|-----|
| Frontend (main UI) | http://localhost:3000 |
| API interactive docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

### 4. Stop

```bash
docker compose down          # stop containers, keep DB volume
docker compose down -v       # stop + delete DB volume (clean slate)
```

---

## Running Locally (without Docker)

> This only works on Linux because Xvfb, mutter, and x11vnc are Linux-only.

### 1. Start PostgreSQL

```bash
# Using the provided compose file for just the DB:
docker compose up db -d

# Or use your own local Postgres instance and create the DB:
createdb computer_use
```

### 2. Install Python dependencies

```bash
cd computer-use-demo/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Also install the computer_use_demo deps
pip install -r ../computer_use_demo/requirements.txt
```

### 3. Set environment variables

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/computer_use
export PYTHONPATH=$(pwd)/..   # makes computer_use_demo importable
```

### 4. Run database migrations

```bash
# From inside backend/
alembic upgrade head
```

### 5. Start the API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Serve the frontend

Open a second terminal:

```bash
cd computer-use-demo/frontend
python -m http.server 3000
```

Then open http://localhost:3000.

---

## API Quick Reference

```
POST   /api/v1/sessions                    Create a new session
GET    /api/v1/sessions                    List all sessions
GET    /api/v1/sessions/{id}               Get one session
DELETE /api/v1/sessions/{id}               Delete session + history

POST   /api/v1/sessions/{id}/messages      Send a message (returns 202 immediately)
GET    /api/v1/sessions/{id}/messages      Full message history
GET    /api/v1/sessions/{id}/stream        SSE real-time event stream

GET    /api/v1/sessions/{id}/vnc           Get noVNC URL for this session's desktop
GET    /health                             Health check
```

Full interactive docs with request/response schemas: http://localhost:8000/docs

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required** |
| `API_PROVIDER` | `anthropic` | `anthropic` / `bedrock` / `vertex` |
| `MODEL` | `claude-sonnet-4-5-20250929` | Claude model ID |
| `DATABASE_URL` | postgres @ db:5432 | Async PostgreSQL URL |
| `DISPLAY_START` | `10` | First Xvfb display number (`:10`, `:11`, ...) |
| `VNC_BASE_PORT` | `5910` | First raw VNC port |
| `NOVNC_BASE_PORT` | `6910` | First noVNC/websockify port |
| `NOVNC_WEB_PATH` | `/opt/noVNC` | Path to noVNC static files inside container |
| `DISPLAY_WIDTH` | `1024` | Virtual display width |
| `DISPLAY_HEIGHT` | `768` | Virtual display height |
| `SESSION_IDLE_TIMEOUT_MINUTES` | `120` | Auto-delete sessions idle longer than this |

---

## Common Issues

**`docker compose up` fails with "port already in use"**
Something on your machine is using port 5432, 8000, or 3000. Either stop that process or change the host port in `docker-compose.yml` (left side of the colon).

**Sessions show "VNC not available"**
The noVNC process inside the container takes 1–2 seconds to start after a session is created. Reload the session in the sidebar after a moment.

**Agent starts but nothing happens on the VNC screen**
Make sure `ANTHROPIC_API_KEY` in your `.env` is valid and not expired.

**`alembic upgrade head` fails with "relation already exists"**
The tables were already created by SQLAlchemy's `create_all` on first startup. Mark the migration as applied manually:
```bash
alembic stamp head
```

**Firefox does not open / windows don't appear**
mutter (window manager) may have failed to start on that session's display. Delete the session and create a new one. Check Docker logs:
```bash
docker compose logs backend
```
