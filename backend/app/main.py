import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import AsyncSessionLocal, create_tables
from app.models import (  # noqa: F401 — required for Base.metadata.create_all
    Message,
    Session,
)
from app.routers import messages, sessions, vnc
from app.schemas import HealthResponse
from app.services.session_manager import session_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    async with AsyncSessionLocal() as db:
        await session_manager.ensure_state_loaded(db)
        await db.commit()
    await session_manager.start()
    logger.info("Application ready.")
    yield
    await session_manager.stop()
    logger.info("Application shutting down.")


app = FastAPI(
    title="Computer Use Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/v1")
app.include_router(messages.router, prefix="/api/v1")
app.include_router(vnc.router, prefix="/api/v1")


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse()
