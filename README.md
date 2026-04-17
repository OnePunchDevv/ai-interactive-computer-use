# Marcus Kale

# Computer Use Agent — Backend API

A production-ready, highly parallelized FastAPI backend for the [Anthropic Computer Use](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo) reference implementation. This repository completely replaces the experimental Streamlit GUI layer with a strict REST API, Server-Sent Events (SSE) streaming infrastructure, and a robust asynchronous concurrency model that allows multiple independent users to operate simultaneously without thread-blocking.

## Demo Video

> 📹 [Demo Video](https://www.loom.com/share/79a83cb24a774b6db07de8d82d439380)
> 📹 [Use Case 1](https://www.loom.com/share/212e0765822f41b09919d603be6c9256)
> 📹 [Use Case 2](https://www.loom.com/share/ce21ead92a714adeb868beb95cb01a90)

https://www.loom.com/share/ce21ead92a714adeb868beb95cb01a90
---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│          HTML / Vanilla JS  (port 3000)                     │
└─────────────────┬───────────────────────┬───────────────────┘
                  │ REST                  │ SSE
                  ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI  (port 8000)                       │
│                                                             │
│  POST /sessions          GET /sessions/:id/stream           │
│  POST /sessions/:id/messages    GET /sessions/:id/vnc       │
│  GET  /sessions/:id/messages                                │
│                                                             │
│  ┌──────────────────┐   ┌────────────────────────────────┐  │
│  │  SessionManager  │   │        AgentRunner             │  │
│  │  (per-session    │   │  wraps sampling_loop()         │  │
│  │   asyncio.Task + │   │  callbacks → SSE queue + DB    │  │
│  │   Xvfb process)  │   └────────────────────────────────┘  │
│  └──────────────────┘                                       │
└──────────────┬──────────────────────────────────────────────┘
               │
   ┌───────────┴────────────┐
   ▼                        ▼
┌──────────┐         ┌──────────────────────────────────────┐
│PostgreSQL│         │  Per-session isolated virtual display│
│          │         │                                      │
│ sessions │         │  Xvfb  :10   x11vnc :5910            │
│ messages │         │  Xvfb  :11   x11vnc :5911            │
└──────────┘         │  Xvfb  :N    x11vnc :59NN   ...      │
                     │                                      │
                     │  noVNC websockify → browser iframe   │
                     └──────────────────────────────────────┘
```

### Concurrency Design

Every incoming session gets its own:
- **Xvfb virtual display** on a unique display number (`:10`, `:11`, …) — no shared X11 state between sessions.
- **x11vnc + noVNC** process pair on a unique port pair, so each session's desktop is viewable independently.
- **asyncio.Task** scheduled on the single-process event loop — truly non-blocking; the HTTP handler returns `202 Accepted` immediately.
- **Per-session `asyncio.Lock`** (`run_lock`) that serialises consecutive messages within one session while leaving other sessions unaffected.

Display numbers and ports are allocated from an ever-incrementing counter protected by an `asyncio.Lock`, so concurrent `POST /sessions` calls never race. There is **no hardcoded session limit** — the OS and available memory are the only practical ceiling.

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd computer-use-demo

# 2. Create your .env
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 3. Launch everything
docker compose up --build
```

| Service  | URL                          |
|----------|------------------------------|
| Frontend | http://localhost:3000        |
| API      | http://localhost:8000        |
| API Docs | http://localhost:8000/docs   |
| Postgres | localhost:5432               |

---

## API Reference

### Sessions

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/v1/sessions` | Create a new session (spawns Xvfb + VNC) | 201 |
| `GET` | `/api/v1/sessions` | List all sessions | 200 |
| `GET` | `/api/v1/sessions/{id}` | Get a single session | 200 |
| `DELETE` | `/api/v1/sessions/{id}` | Stop session and delete all data | 204 |

**Create session — request**
```json
POST /api/v1/sessions
{ "title": "Weather search" }
```

**Create session — response**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "title": "Weather search",
  "status": "idle",
  "display_num": 10,
  "vnc_port": 5910,
  "novnc_port": 6910,
  "created_at": "2026-04-08T12:00:00Z",
  "updated_at": "2026-04-08T12:00:00Z"
}
```

---

### Messages

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/v1/sessions/{id}/messages` | Send a message — returns immediately | 202 |
| `GET` | `/api/v1/sessions/{id}/messages` | Full message history | 200 |
| `GET` | `/api/v1/sessions/{id}/stream` | **SSE** real-time event stream | 200 |

**Send message — request**
```json
POST /api/v1/sessions/{id}/messages
{ "content": "Search the weather in Dubai" }
```

**SSE stream event types**

| `event` field | Payload | Meaning |
|---------------|---------|---------|
| `status` | `{ "status": "running" \| "idle" \| "error" }` | Session state changed |
| `text_delta` | `{ "text": "..." }` | Assistant text chunk |
| `tool_use` | `{ "tool": "computer", "input": {...}, "id": "..." }` | Agent calling a tool |
| `tool_result` | `{ "tool_use_id": "...", "output": "...", "has_screenshot": true }` | Tool execution result |
| `error` | `{ "message": "..." }` | Unhandled error |
| `done` | `{ "message": "Agent turn complete" }` | Turn finished, stream closes |

**Consuming the stream (JavaScript)**
```js
const es = new EventSource(`/api/v1/sessions/${id}/stream`);
es.onmessage = ({ data }) => {
  const event = JSON.parse(data);
  if (event.event === 'text_delta') console.log(event.data.text);
  if (event.event === 'done') es.close();
};
```

---

### VNC

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/sessions/{id}/vnc` | Returns noVNC URL for the session's desktop |

**Response**
```json
{
  "session_id": "3fa85f64-...",
  "display_num": 10,
  "vnc_port": 5910,
  "novnc_port": 6910,
  "novnc_url": "http://localhost:6910/vnc.html?autoconnect=true&reconnect=true&resize=scale"
}
```

---

### Health

```
GET /health  →  { "status": "ok", "version": "1.0.0" }
```

---

## Sequence Diagrams

### Creating a session and running a task

```mermaid
sequenceDiagram
    participant Browser
    participant API as FastAPI
    participant SM as SessionManager
    participant DB as PostgreSQL
    participant Xvfb

    Browser->>API: POST /api/v1/sessions
    API->>SM: create_session()
    SM->>SM: allocate display_num + ports
    SM->>Xvfb: spawn Xvfb :N + x11vnc + noVNC
    SM->>DB: INSERT sessions
    API-->>Browser: 201 { id, vnc_port, novnc_port }

    Browser->>API: GET /api/v1/sessions/{id}/stream (SSE)
    Note over Browser,API: SSE connection held open

    Browser->>API: POST /api/v1/sessions/{id}/messages
    API->>SM: dispatch_message() — asyncio.create_task()
    API-->>Browser: 202 Accepted (immediate)

    Note over SM: Task runs on event loop
    SM->>DB: UPDATE sessions SET status='running'
    SM-->>Browser: SSE: { event: "status", data: { status: "running" } }
    SM->>SM: sampling_loop() → Anthropic API
    SM-->>Browser: SSE: { event: "text_delta", data: { text: "..." } }
    SM->>Xvfb: computer_use tool (screenshot / click / type)
    SM-->>Browser: SSE: { event: "tool_use", data: { tool: "computer", ... } }
    SM-->>Browser: SSE: { event: "tool_result", data: { has_screenshot: true } }
    SM->>DB: INSERT messages (role=tool_use / tool_result)
    SM->>SM: loop until no more tool calls
    SM->>DB: UPDATE sessions SET status='idle'
    SM-->>Browser: SSE: { event: "done" }
```

### Concurrent sessions (non-blocking)

```mermaid
sequenceDiagram
    participant A as Browser A
    participant B as Browser B
    participant API as FastAPI
    participant T1 as Task: session-1 (display :10)
    participant T2 as Task: session-2 (display :11)

    A->>API: POST /sessions → id=1 (display :10)
    B->>API: POST /sessions → id=2 (display :11)

    A->>API: POST /sessions/1/messages ("Tokyo weather")
    API->>T1: create_task() — returns 202 immediately
    B->>API: POST /sessions/2/messages ("New York weather")
    API->>T2: create_task() — returns 202 immediately

    Note over T1,T2: Both tasks run concurrently on the event loop

    T1-->>A: SSE stream: Tokyo agent progress
    T2-->>B: SSE stream: New York agent progress

    T1->>T1: Firefox opens on display :10
    T2->>T2: Firefox opens on display :11

    T1-->>A: SSE: done
    T2-->>B: SSE: done
```

---

## Local Development (without Docker)

**Prerequisites:** Python 3.11+, PostgreSQL 16, Xvfb, x11vnc, noVNC/websockify installed.

```bash
# Install Python deps
cd backend
pip install -r requirements.txt

# Set environment
export ANTHROPIC_API_KEY=sk-ant-...
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/computer_use
export PYTHONPATH=..   # makes computer_use_demo importable

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Serve frontend (separate terminal)
cd ../frontend
python -m http.server 3000
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required.** Anthropic API key |
| `API_PROVIDER` | `anthropic` | `anthropic` \| `bedrock` \| `vertex` |
| `MODEL` | `claude-sonnet-4-5-20250929` | Claude model ID |
| `DATABASE_URL` | postgres @ db:5432 | Async PostgreSQL connection string |
| `DISPLAY_START` | `10` | First Xvfb display number allocated |
| `VNC_BASE_PORT` | `5910` | First VNC raw port |
| `NOVNC_BASE_PORT` | `6910` | First noVNC websockify port |
| `DISPLAY_WIDTH` | `1024` | Virtual display width (px) |
| `DISPLAY_HEIGHT` | `768` | Virtual display height (px) |

---

## Project Structure

```
computer-use-demo/
├── backend/
│   ├── Dockerfile
│   ├── alembic/                  # DB migrations
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── alembic.ini
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # FastAPI app + lifespan
│       ├── config.py             # pydantic-settings
│       ├── database.py           # async SQLAlchemy engine
│       ├── models.py             # Session + Message ORM
│       ├── schemas.py            # Pydantic request/response
│       ├── core/
│       │   └── events.py         # SSE event constants
│       ├── services/
│       │   ├── session_manager.py  # concurrent session orchestrator
│       │   └── agent_runner.py     # wraps computer_use_demo loop
│       └── routers/
│           ├── sessions.py
│           ├── messages.py       # send + history + SSE stream
│           └── vnc.py
├── frontend/
│   ├── index.html
│   ├── app.js                    # Vanilla JS SSE client
│   ├── style.css
│   └── nginx.conf
├── computer_use_demo/            # Anthropic Reference Agent
│   ├── env_context.py            # Task-local ContextVars for GUI rendering
│   ├── loop.py                   # AsyncAnthropic non-blocking LLM loop
├── postgres-init/
│   └── init.sql
├── docker-compose.yml
└── .env.example
```

---

## Database Schema

```sql
sessions (
  id          UUID PRIMARY KEY,
  title       VARCHAR(255),
  status      VARCHAR(20),   -- idle | running | done | error
  display_num INTEGER,
  vnc_port    INTEGER,
  novnc_port  INTEGER,
  created_at  TIMESTAMPTZ,
  updated_at  TIMESTAMPTZ
)

messages (
  id           UUID PRIMARY KEY,
  session_id   UUID REFERENCES sessions(id) ON DELETE CASCADE,
  role         VARCHAR(20),  -- user | assistant | tool_use | tool_result
  content      JSONB,        -- full Anthropic API block
  text_preview TEXT,         -- plain-text summary for UI display
  seq          INTEGER,      -- monotonically increasing per session
  created_at   TIMESTAMPTZ
)
```
