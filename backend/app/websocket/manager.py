import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, investigation_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active[investigation_id].add(websocket)

    def disconnect(self, investigation_id: str, websocket: WebSocket):
        self.active[investigation_id].discard(websocket)

    async def broadcast(self, investigation_id: str, event_type: str, payload: dict[str, Any]):
        message = json.dumps(
            {
                "type": event_type,
                "investigation_id": investigation_id,
                "payload": payload,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
        stale = []
        for websocket in self.active[investigation_id]:
            try:
                await websocket.send_text(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(investigation_id, websocket)


manager = ConnectionManager()
