from httpx import ASGITransport, AsyncClient

from app.main import app
from app.tests.test_api import login
from app.tests.ws_helpers import _RawAsgiWebSocket


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
