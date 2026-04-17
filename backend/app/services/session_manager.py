import asyncio
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Session
from app.services.agent_runner import run_agent

logger = logging.getLogger(__name__)

_QUEUE_MAX_SIZE = 512


@dataclass
class _SessionState:
    session_id: uuid.UUID
    display_num: int
    vnc_port: int
    novnc_port: int
    xvfb_proc: asyncio.subprocess.Process | None = None
    mutter_proc: asyncio.subprocess.Process | None = None
    tint2_proc: asyncio.subprocess.Process | None = None
    x11vnc_proc: asyncio.subprocess.Process | None = None
    novnc_proc: asyncio.subprocess.Process | None = None
    event_queue: asyncio.Queue = field(
        default_factory=lambda: asyncio.Queue(_QUEUE_MAX_SIZE)
    )
    run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    current_task: asyncio.Task | None = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[uuid.UUID, _SessionState] = {}
        self._alloc_lock = asyncio.Lock()
        self._next_display = settings.display_start
        self._gc_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start background tasks. Called from app lifespan."""
        self._gc_task = asyncio.create_task(self._gc_loop(), name="session-gc")

    async def stop(self) -> None:
        """Cancel background tasks. Called from app lifespan."""
        if self._gc_task and not self._gc_task.done():
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass

    async def create_session(
        self, db: AsyncSession, title: str = "New Session"
    ) -> Session:
        display_num, vnc_port, novnc_port = await self._allocate_ports()

        session = Session(
            title=title,
            status="idle",
            display_num=display_num,
            vnc_port=vnc_port,
            novnc_port=novnc_port,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)

        state = _SessionState(
            session_id=session.id,
            display_num=display_num,
            vnc_port=vnc_port,
            novnc_port=novnc_port,
        )
        self._sessions[session.id] = state
        await self._start_display(state)

        logger.info(
            "Created session %s on display :%d (VNC :%d, noVNC :%d)",
            session.id,
            display_num,
            vnc_port,
            novnc_port,
        )
        return session

    async def delete_session(self, db: AsyncSession, session_id: uuid.UUID) -> bool:
        state = self._sessions.pop(session_id, None)
        if state:
            await self._cancel_task(state)
            await self._stop_display(state)

        session = await db.get(Session, session_id)
        if session is None:
            return False
        await db.delete(session)
        await db.flush()
        return True

    async def dispatch_message(self, session_id: uuid.UUID, user_message: str) -> None:
        """Fire-and-forget: spawns an asyncio.Task per message, returns immediately."""
        state = self._get_state_or_raise(session_id)

        async def _run() -> None:
            async with state.run_lock:
                async with AsyncSessionLocal() as db:
                    await run_agent(
                        session_id=session_id,
                        user_message=user_message,
                        display_num=state.display_num,
                        event_queue=state.event_queue,
                        db=db,
                    )

        task = asyncio.create_task(_run(), name=f"agent-{session_id}")
        state.current_task = task
        task.add_done_callback(self._task_done_callback)

    def get_event_queue(self, session_id: uuid.UUID) -> asyncio.Queue:
        return self._get_state_or_raise(session_id).event_queue

    def session_is_active(self, session_id: uuid.UUID) -> bool:
        return session_id in self._sessions

    async def ensure_state_loaded(self, db: AsyncSession) -> None:
        """Restart display processes for sessions that survived a server restart."""
        result = await db.execute(select(Session))
        for session in result.scalars().all():
            if session.id not in self._sessions and session.display_num:
                state = _SessionState(
                    session_id=session.id,
                    display_num=session.display_num,
                    vnc_port=session.vnc_port or 0,
                    novnc_port=session.novnc_port or 0,
                )
                self._sessions[session.id] = state
                await self._start_display(state)
            if session.status == "running":
                session.status = "idle"
        await db.flush()

    async def _allocate_ports(self) -> tuple[int, int, int]:
        async with self._alloc_lock:
            display_num = self._next_display
            self._next_display += 1

        offset = display_num - settings.display_start
        return (
            display_num,
            settings.vnc_base_port + offset,
            settings.novnc_base_port + offset,
        )

    async def _start_display(self, state: _SessionState) -> None:
        w, h = settings.display_width, settings.display_height
        display = f":{state.display_num}"
        # Per-display env — passed explicitly to each subprocess so they
        # target the correct virtual display without touching os.environ.
        display_env = {**os.environ, "DISPLAY": display}

        try:
            state.xvfb_proc = await asyncio.create_subprocess_exec(
                "Xvfb",
                display,
                "-screen",
                "0",
                f"{w}x{h}x24",
                "-ac",
                "-nolisten",
                "tcp",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(0.8)  # let Xvfb initialise before anything connects

            # Window manager — required for Firefox and other GUI apps to render correctly
            state.mutter_proc = await asyncio.create_subprocess_exec(
                "mutter",
                "--replace",
                "--sm-disable",
                env={**display_env, "XDG_SESSION_TYPE": "x11"},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(0.5)  # give mutter a moment before VNC connects

            # Taskbar — provides UI for switching/closing windows
            state.tint2_proc = await asyncio.create_subprocess_exec(
                "tint2",
                env=display_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            state.x11vnc_proc = await asyncio.create_subprocess_exec(
                "x11vnc",
                "-display",
                display,
                "-rfbport",
                str(state.vnc_port),
                "-nopw",
                "-forever",
                "-shared",
                "-quiet",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            state.novnc_proc = await asyncio.create_subprocess_exec(
                "websockify",
                "--web",
                settings.novnc_web_path,
                str(state.novnc_port),
                f"localhost:{state.vnc_port}",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        except FileNotFoundError as exc:
            logger.warning("Display startup skipped (binary not found): %s", exc)

    async def _stop_display(self, state: _SessionState) -> None:
        for attr in (
            "novnc_proc",
            "x11vnc_proc",
            "tint2_proc",
            "mutter_proc",
            "xvfb_proc",
        ):
            proc: asyncio.subprocess.Process | None = getattr(state, attr)
            if proc and proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except (asyncio.TimeoutError, Exception):
                    try:
                        proc.kill()
                    except Exception:
                        pass

    async def _cancel_task(self, state: _SessionState) -> None:
        if state.current_task and not state.current_task.done():
            state.current_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(state.current_task), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def _gc_loop(self) -> None:
        """Periodically delete sessions that have been idle past the configured timeout."""
        interval = 15 * 60  # check every 15 minutes
        while True:
            try:
                await asyncio.sleep(interval)
                await self._gc_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("GC loop error: %s", exc)

    async def _gc_once(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=settings.session_idle_timeout_minutes
        )
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Session).where(
                    Session.status == "idle",
                    Session.updated_at < cutoff,
                )
            )
            stale = result.scalars().all()
            for session in stale:
                logger.info(
                    "GC: removing stale idle session %s (last updated %s)",
                    session.id,
                    session.updated_at,
                )
                await self.delete_session(db, session.id)
            if stale:
                await db.commit()

    def _get_state_or_raise(self, session_id: uuid.UUID) -> _SessionState:
        state = self._sessions.get(session_id)
        if state is None:
            raise KeyError(f"Session {session_id} not found or not active")
        return state

    def _task_done_callback(self, task: asyncio.Task) -> None:
        if not task.cancelled() and (exc := task.exception()):
            logger.error(
                "Unhandled exception in agent task %s: %s", task.get_name(), exc
            )


session_manager = SessionManager()
