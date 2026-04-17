import asyncio
import json
import logging
import pathlib
import sys
import uuid
from typing import Any

import httpx
from anthropic.types.beta import BetaContentBlockParam
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.events import (
    DONE,
    ERROR,
    STATUS,
    TEXT_DELTA,
    TOOL_RESULT,
    TOOL_USE,
    make_event,
    serialize_event,
)
from app.models import Message, Session

# computer_use_demo lives two directories above this file:
# backend/app/services/agent_runner.py → backend/app/services → backend/app → backend → computer-use-demo/
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from computer_use_demo.env_context import session_env  # noqa: E402
from computer_use_demo.loop import APIProvider, sampling_loop  # noqa: E402
from computer_use_demo.tools import ToolResult, ToolVersion  # noqa: E402

logger = logging.getLogger(__name__)

_DEFAULT_TOOL_VERSION: ToolVersion = "computer_use_20250124"


async def run_agent(
    *,
    session_id: uuid.UUID,
    user_message: str,
    display_num: int,
    event_queue: asyncio.Queue,
    db: AsyncSession,
) -> None:
    sid = str(session_id)

    async def _push(event_type: str, data: Any) -> None:
        try:
            await event_queue.put(serialize_event(make_event(event_type, sid, data)))
        except Exception:
            pass

    await _set_session_status(db, session_id, "running")
    await _push(STATUS, {"status": "running"})

    api_messages = await _load_api_messages(db, session_id)

    user_content: list[BetaContentBlockParam] = [{"type": "text", "text": user_message}]
    api_messages.append({"role": "user", "content": user_content})

    seq = await _next_seq(db, session_id)
    db.add(
        Message(
            session_id=session_id,
            role="user",
            content=user_content,
            text_preview=user_message[:500],
            seq=seq,
        )
    )
    await db.flush()

    display_env = {
        "DISPLAY": f":{display_num}",
        "WIDTH": str(settings.display_width),
        "HEIGHT": str(settings.display_height),
        "DISPLAY_NUM": str(display_num),
    }

    # Set the ContextVar for this asyncio.Task to scope the environment overrides locally
    token = session_env.set(display_env)

    try:
        # Get the running loop once so all callbacks schedule tasks on the correct loop.
        loop = asyncio.get_running_loop()
        # Track tasks so we can await them before finalising the turn.
        pending_tasks: list[asyncio.Task] = []
        db_lock = asyncio.Lock()

        def output_callback(content_block: BetaContentBlockParam) -> None:
            pending_tasks.append(loop.create_task(_handle_output_block(content_block)))

        async def _handle_output_block(block: BetaContentBlockParam) -> None:
            block_type = (
                block.get("type")
                if isinstance(block, dict)
                else getattr(block, "type", None)
            )

            if block_type == "text":
                text = (
                    block.get("text", "")
                    if isinstance(block, dict)
                    else getattr(block, "text", "")
                )
                await _push(TEXT_DELTA, {"text": text})
                async with db_lock:
                    seq = await _next_seq(db, session_id)
                    db.add(
                        Message(
                            session_id=session_id,
                            role="assistant",
                            content=block
                            if isinstance(block, dict)
                            else block.model_dump(),
                            text_preview=text[:500] if text else None,
                            seq=seq,
                        )
                    )
                    await db.flush()

            elif block_type == "tool_use":
                tool_name = (
                    block.get("name", "")
                    if isinstance(block, dict)
                    else getattr(block, "name", "")
                )
                tool_input = (
                    block.get("input", {})
                    if isinstance(block, dict)
                    else getattr(block, "input", {})
                )
                tool_id = (
                    block.get("id", "")
                    if isinstance(block, dict)
                    else getattr(block, "id", "")
                )
                await _push(
                    TOOL_USE, {"tool": tool_name, "input": tool_input, "id": tool_id}
                )
                async with db_lock:
                    seq = await _next_seq(db, session_id)
                    db.add(
                        Message(
                            session_id=session_id,
                            role="tool_use",
                            content=block
                            if isinstance(block, dict)
                            else block.model_dump(),
                            text_preview=f"{tool_name}({json.dumps(tool_input)[:200]})",
                            seq=seq,
                        )
                    )
                    await db.flush()

        def tool_output_callback(result: ToolResult, tool_use_id: str) -> None:
            pending_tasks.append(
                loop.create_task(_handle_tool_result(result, tool_use_id))
            )

        async def _handle_tool_result(result: ToolResult, tool_use_id: str) -> None:
            payload: dict[str, Any] = {"tool_use_id": tool_use_id}
            if result.error:
                payload["error"] = result.error
            if result.output:
                payload["output"] = result.output
            if result.base64_image:
                payload["has_screenshot"] = True

            await _push(TOOL_RESULT, payload)

            async with db_lock:
                seq = await _next_seq(db, session_id)
                db.add(
                    Message(
                        session_id=session_id,
                        role="tool_result",
                        content={
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "output": result.output,
                            "error": result.error,
                            "has_image": bool(result.base64_image),
                        },
                        text_preview=(result.output or result.error or "")[:500],
                        seq=seq,
                    )
                )
                await db.flush()

        def api_response_callback(
            request: httpx.Request,
            response: httpx.Response | object | None,
            error: Exception | None,
        ) -> None:
            if error:
                logger.warning("API error for session %s: %s", sid, error)

        try:
            await sampling_loop(
                model=settings.model,
                provider=APIProvider(settings.api_provider),
                system_prompt_suffix="",
                messages=api_messages,
                output_callback=output_callback,
                tool_output_callback=tool_output_callback,
                api_response_callback=api_response_callback,
                api_key=settings.anthropic_api_key,
                only_n_most_recent_images=3,
                max_tokens=settings.max_tokens,
                tool_version=_DEFAULT_TOOL_VERSION,
            )

            # Wait for all output/tool-result tasks to flush their events before
            # pushing the terminal status — this guarantees correct queue ordering.
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)

            await _set_session_status(db, session_id, "idle")
            await _push(STATUS, {"status": "idle"})
            await _push(DONE, {"message": "Agent turn complete"})

        except asyncio.CancelledError:
            logger.info("Agent task cancelled for session %s", sid)
            for t in pending_tasks:
                if not t.done():
                    t.cancel()
            await _set_session_status(db, session_id, "idle")
            await _push(STATUS, {"status": "idle"})
            raise

        except Exception as exc:
            logger.exception("Agent error for session %s: %s", sid, exc)
            await _set_session_status(db, session_id, "error")
            await _push(ERROR, {"message": str(exc)})
            await _push(STATUS, {"status": "error"})

    finally:
        session_env.reset(token)
        await db.commit()


async def _set_session_status(
    db: AsyncSession, session_id: uuid.UUID, status: str
) -> None:
    result = await db.get(Session, session_id)
    if result:
        result.status = status
        await db.flush()


async def _next_seq(db: AsyncSession, session_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(Message.seq), -1)).where(
            Message.session_id == session_id
        )
    )
    return (result.scalar() or -1) + 1


async def _load_api_messages(db: AsyncSession, session_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.seq)
    )
    messages = result.scalars().all()

    api_messages: list[dict] = []
    for msg in messages:
        if msg.role in ("user", "assistant"):
            content = msg.content
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            elif isinstance(content, dict):
                content = [content]
            # The Anthropic API requires consecutive same-role blocks be merged
            if api_messages and api_messages[-1]["role"] == msg.role:
                existing = api_messages[-1]["content"]
                if isinstance(existing, list) and isinstance(content, list):
                    existing.extend(content)
                    continue
            api_messages.append({"role": msg.role, "content": content})

        elif msg.role == "tool_use":
            # tool_use blocks are part of the assistant turn — merge into last assistant message
            block = msg.content if isinstance(msg.content, dict) else {}
            if api_messages and api_messages[-1]["role"] == "assistant":
                existing = api_messages[-1]["content"]
                if isinstance(existing, list):
                    existing.append(block)
                    continue
            api_messages.append({"role": "assistant", "content": [block]})

        elif msg.role == "tool_result":
            tool_result_block = {
                "type": "tool_result",
                "tool_use_id": msg.content.get("tool_use_id", ""),
                "content": msg.content.get("output") or msg.content.get("error") or "",
                "is_error": bool(msg.content.get("error")),
            }
            if api_messages and api_messages[-1]["role"] == "user":
                existing = api_messages[-1]["content"]
                if isinstance(existing, list):
                    existing.append(tool_result_block)
                    continue
            api_messages.append({"role": "user", "content": [tool_result_block]})

    return api_messages
