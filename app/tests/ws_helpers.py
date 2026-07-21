import asyncio
import json

from app.main import app


class _RawAsgiWebSocket:
    """Drives the app's ASGI websocket protocol directly over asyncio queues,
    on the *same* event loop as the rest of the test. Starlette's own
    TestClient.websocket_connect runs each connection in a separate
    background-thread event loop, which breaks this app's shared async
    SQLAlchemy engine (a pooled connection created under one loop can't be
    reused from another) as soon as more than one request/connection touches
    it. Since this project's whole test suite otherwise runs REST calls via
    an async httpx client on the single pytest-asyncio loop, a websocket test
    needs to stay on that same loop too -- hence this minimal harness instead
    of the synchronous TestClient.
    """

    def __init__(self):
        self._to_app: asyncio.Queue = asyncio.Queue()
        self._from_app: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def _receive(self):
        return await self._to_app.get()

    async def _send(self, message):
        await self._from_app.put(message)

    async def connect(self, room_id: int, session_cookie: str):
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": f"/ws/rooms/{room_id}",
            "raw_path": f"/ws/rooms/{room_id}".encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"cookie", f"session={session_cookie}".encode())],
            "client": ("testclient", 12345),
            "server": ("testserver", 80),
            "subprotocols": [],
            "state": {},
        }
        self._task = asyncio.create_task(app(scope, self._receive, self._send))
        await self._to_app.put({"type": "websocket.connect"})
        msg = await self._from_app.get()
        assert msg["type"] == "websocket.accept", msg

    async def send_text(self, text: str):
        await self._to_app.put({"type": "websocket.receive", "text": text})

    async def receive_event(self, event: str, max_tries: int = 5) -> dict:
        for _ in range(max_tries):
            msg = await self._from_app.get()
            assert msg["type"] == "websocket.send", msg
            payload = json.loads(msg["text"])
            if payload["event"] == event:
                return payload
        raise AssertionError(f"did not receive {event!r} within {max_tries} messages")

    async def close(self):
        await self._to_app.put({"type": "websocket.disconnect", "code": 1000})
        if self._task:
            await self._task
