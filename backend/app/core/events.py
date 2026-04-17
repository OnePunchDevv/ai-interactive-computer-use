import json
from typing import Any

TEXT_DELTA = "text_delta"
TOOL_USE = "tool_use"
TOOL_RESULT = "tool_result"
STATUS = "status"
ERROR = "error"
DONE = "done"


def make_event(event_type: str, session_id: str, data: Any) -> dict:
    return {
        "event": event_type,
        "session_id": session_id,
        "data": data,
    }


def serialize_event(event: dict) -> str:
    return json.dumps(event, default=str)
