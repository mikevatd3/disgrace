import asyncio
import json

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.tests.test_api import login


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


async def test_game_state_broadcasts_redacted_seat_per_viewer(client):
    # First WS test in the repo: proves the game_state broadcast/redaction
    # wiring (RoomConnectionManager.broadcast_per_user, called from the REST
    # join endpoint) actually reaches connected sockets, and that each
    # viewer's payload is computed for them specifically (my_seat differs).
    # The rules/state-machine correctness itself is covered by the pure
    # engine unit tests and the REST integration tests -- this only checks
    # the wiring is connected.
    c2 = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    await login(client, name="wsplayer1", password="correct-horse-1!")
    await login(c2, name="wsplayer2", password="correct-horse-1!")

    cookie1 = client.cookies.get("session")
    cookie2 = c2.cookies.get("session")
    assert cookie1 and cookie2

    resp = await client.post("/api/rooms", json={"name": "ws-room"})
    room_id = resp.json()["id"]

    resp = await client.post(f"/api/rooms/{room_id}/games")
    game_id = resp.json()["id"]

    ws1 = _RawAsgiWebSocket()
    ws2 = _RawAsgiWebSocket()
    try:
        await ws1.connect(room_id, cookie1)
        await ws1.receive_event("presence_state")

        await ws2.connect(room_id, cookie2)
        await ws2.receive_event("presence_state")
        await ws1.receive_event("presence_diff")  # ws2 joining the room

        resp = await client.post(f"/api/rooms/{room_id}/games/{game_id}/join")
        assert resp.status_code == 200

        m1 = await ws1.receive_event("game_state")
        m2 = await ws2.receive_event("game_state")
        assert m1["payload"]["my_seat"] is not None
        assert m2["payload"]["my_seat"] is None  # player 2 hasn't joined the game yet

        resp = await c2.post(f"/api/rooms/{room_id}/games/{game_id}/join")
        assert resp.status_code == 200

        m1 = await ws1.receive_event("game_state")
        m2 = await ws2.receive_event("game_state")
        assert m1["payload"]["my_seat"] is not None
        assert m2["payload"]["my_seat"] is not None
        assert m1["payload"]["my_seat"] != m2["payload"]["my_seat"]
    finally:
        await ws1.close()
        await ws2.close()
        await c2.aclose()
