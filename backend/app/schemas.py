import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    title: str = Field(default="New Session", max_length=255)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    display_num: int | None
    vnc_port: int | None
    novnc_port: int | None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    total: int


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: Any
    text_preview: str | None
    seq: int
    created_at: datetime


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    total: int


class VNCInfo(BaseModel):
    session_id: uuid.UUID
    display_num: int | None
    vnc_port: int | None
    novnc_port: int | None
    novnc_url: str | None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
