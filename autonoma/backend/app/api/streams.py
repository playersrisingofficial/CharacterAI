"""SSE + WebSocket helpers that turn the event bus into live HTTP streams.

All payloads pass through the secret redactor before leaving the process, so
no secret can appear in a live event stream (Section 10)."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import WebSocket
from fastapi.responses import StreamingResponse

from ..events import bus
from ..secrets_vault import redact


async def _sse_gen(event_types: set[str] | None, filter_fn=None) -> AsyncIterator[bytes]:
    async for ev in bus.stream(event_types):
        data = redact(ev.to_dict())
        if filter_fn and not filter_fn(data):
            continue
        yield f"event: {ev.event_type}\ndata: {json.dumps(data)}\n\n".encode()


def sse_response(event_types: set[str] | None = None, filter_fn=None) -> StreamingResponse:
    return StreamingResponse(
        _sse_gen(event_types, filter_fn),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def ws_pump(ws: WebSocket, event_types: set[str] | None = None, filter_fn=None) -> None:
    await ws.accept()
    try:
        async for ev in bus.stream(event_types):
            data = redact(ev.to_dict())
            if filter_fn and not filter_fn(data):
                continue
            await ws.send_json(data)
    except Exception:
        # Client disconnected or send failed; end the pump quietly.
        pass
