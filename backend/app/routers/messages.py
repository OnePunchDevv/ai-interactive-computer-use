import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models import Message, Session
from app.schemas import MessageCreate, MessageListResponse
from app.services.session_manager import session_manager

router = APIRouter(prefix="/sessions/{session_id}", tags=["messages"])

_SSE_PING_INTERVAL = 15


@router.post("/messages", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    session_id: uuid.UUID,
    payload: MessageCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session_manager.session_is_active(session_id):
        raise HTTPException(
            status_code=409,
            detail="Session display is not running. Delete and recreate the session.",
        )

    await session_manager.dispatch_message(session_id, payload.content)
    return {"accepted": True, "session_id": str(session_id)}


@router.get("/messages", response_model=MessageListResponse)
async def get_messages(
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.seq)
    )
    messages = result.scalars().all()
    return MessageListResponse(messages=list(messages), total=len(messages))


@router.get("/stream")
async def stream_events(
    session_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session_manager.session_is_active(session_id):
        raise HTTPException(status_code=409, detail="Session display is not running")

    event_queue = session_manager.get_event_queue(session_id)

    async def event_generator():
        loop = asyncio.get_running_loop()
        last_ping = loop.time()
        while True:
            if await request.is_disconnected():
                break
            try:
                raw = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield {"data": raw}
            except asyncio.TimeoutError:
                now = loop.time()
                if now - last_ping >= _SSE_PING_INTERVAL:
                    yield {"comment": "ping"}
                    last_ping = now

    return EventSourceResponse(event_generator())
