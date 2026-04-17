import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Session
from app.schemas import VNCInfo

router = APIRouter(prefix="/sessions", tags=["vnc"])


@router.get("/{session_id}/vnc", response_model=VNCInfo)
async def get_vnc_info(
    session_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Return VNC / noVNC connection details for a session.

    The noVNC URL is built from the request host so it works regardless of
    the deployment environment (local Docker, remote VM, etc.).
    """
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    novnc_url: str | None = None
    if session.novnc_port:
        host = request.headers.get("host", "localhost").split(":")[0]
        novnc_url = (
            f"http://{host}:{session.novnc_port}"
            "/vnc.html?autoconnect=true&reconnect=true&resize=scale"
        )

    return VNCInfo(
        session_id=session.id,
        display_num=session.display_num,
        vnc_port=session.vnc_port,
        novnc_port=session.novnc_port,
        novnc_url=novnc_url,
    )
