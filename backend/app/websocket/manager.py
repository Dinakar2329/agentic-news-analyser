import json
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from app.core.time import utcnow


@dataclass
class ConnectionState:
    buffering: bool = False
    buffer: list[dict[str, Any]] = field(default_factory=list)


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, dict[WebSocket, ConnectionState]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def connect(self, investigation_id: str, websocket: WebSocket):
        await websocket.accept()
        await self.register(investigation_id, websocket)

    async def register(self, investigation_id: str, websocket: WebSocket, *, buffering: bool = False):
        async with self._lock:
            self.active[investigation_id][websocket] = ConnectionState(buffering=buffering)

    async def disconnect(self, investigation_id: str, websocket: WebSocket):
        async with self._lock:
            self.active[investigation_id].pop(websocket, None)
            if not self.active[investigation_id]:
                self.active.pop(investigation_id, None)

    async def broadcast(
        self,
        investigation_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
        created_at: str | None = None,
    ):
        message = {
            "id": event_id,
            "type": event_type,
            "investigation_id": investigation_id,
            "payload": payload,
            "created_at": created_at or utcnow().isoformat(),
        }
        to_send: list[WebSocket] = []
        async with self._lock:
            for websocket, state in self.active.get(investigation_id, {}).items():
                if state.buffering:
                    state.buffer.append(message)
                else:
                    to_send.append(websocket)

        stale = []
        encoded = json.dumps(message)
        for websocket in to_send:
            try:
                await websocket.send_text(encoded)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(investigation_id, websocket)

    async def flush_buffered(
        self,
        investigation_id: str,
        websocket: WebSocket,
        *,
        already_sent_ids: set[str] | None = None,
    ):
        already_sent_ids = already_sent_ids or set()
        while True:
            async with self._lock:
                state = self.active.get(investigation_id, {}).get(websocket)
                if not state:
                    return
                batch = state.buffer
                state.buffer = []
                if not batch:
                    state.buffering = False
                    return
            for message in batch:
                event_id = message.get("id")
                if event_id and event_id in already_sent_ids:
                    continue
                await websocket.send_json(message)


manager = ConnectionManager()
