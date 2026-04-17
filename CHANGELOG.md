# Changelog

## [Unreleased]

### Added
- `backend/` — FastAPI application replacing the Streamlit interface
  - `app/main.py` — FastAPI app with lifespan, CORS, router registration
  - `app/config.py` — pydantic-settings configuration
  - `app/database.py` — async SQLAlchemy engine with asyncpg
  - `app/models.py` — `Session` and `Message` ORM models (PostgreSQL JSONB content)
  - `app/schemas.py` — Pydantic request/response schemas
  - `app/core/events.py` — SSE event type constants and helpers
  - `app/services/session_manager.py` — per-session Xvfb/VNC lifecycle + concurrent asyncio.Task dispatch
  - `app/services/agent_runner.py` — wraps `computer_use_demo.loop.sampling_loop` with SSE callbacks and DB persistence
  - `app/routers/sessions.py` — session CRUD endpoints
  - `app/routers/messages.py` — message send (202), history, and SSE stream endpoint
  - `app/routers/vnc.py` — noVNC URL endpoint
  - `alembic/` — database migrations (initial schema: sessions + messages tables)
  - `Dockerfile` — extends Ubuntu 22.04 base with Xvfb, VNC, Python 3.11, FastAPI stack
  - `requirements.txt`
- `frontend/` — Vanilla HTML/JS/CSS single-page application
  - Three-panel layout: session sidebar, VNC desktop iframe, chat panel
  - Real-time SSE event rendering (text_delta, tool_use, tool_result, status)
  - `nginx.conf` with SSE-aware proxy (buffering disabled)
- `docker-compose.yml` — orchestrates `db` (postgres:16), `backend`, `frontend` services
- `postgres-init/init.sql` — enables `uuid-ossp` extension
- `.env.example`
- `.gitignore` — expanded to cover Python, Node, Docker, secrets, OS artifacts

### Changed
- `README.md` — replaced with full implementation documentation: architecture diagram, API reference, sequence diagrams (Mermaid), quick start, and local dev setup
