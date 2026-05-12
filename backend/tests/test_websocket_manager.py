import json

import pytest

from app.websocket.manager import ConnectionManager


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, message: str):
        self.messages.append(json.loads(message))

    async def send_json(self, message: dict):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_buffered_connection_receives_replay_gap_events_after_flush():
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    await manager.register("investigation-1", websocket, buffering=True)

    await manager.broadcast(
        "investigation-1",
        "source_found",
        {"source": {"id": "source-1"}},
        event_id="event-1",
        created_at="2026-05-12T00:00:00",
    )
    assert websocket.messages == []

    await manager.flush_buffered("investigation-1", websocket, already_sent_ids=set())
    assert websocket.messages[0]["id"] == "event-1"

    await manager.broadcast(
        "investigation-1",
        "final_verdict",
        {"verdict": "UNVERIFIED"},
        event_id="event-2",
        created_at="2026-05-12T00:00:01",
    )
    assert websocket.messages[-1]["id"] == "event-2"
