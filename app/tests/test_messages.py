import json

from app.tests.test_api import login
from app.tests.ws_helpers import _RawAsgiWebSocket

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32


async def test_upload_message_image(client):
    await login(client)
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    resp = await client.post(
        f"/api/rooms/{room['id']}/messages/image",
        files={"file": ("photo.png", _PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["image_url"].startswith("/uploads/")


async def test_upload_message_image_rejects_bad_type(client):
    await login(client)
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    resp = await client.post(
        f"/api/rooms/{room['id']}/messages/image",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415


async def test_upload_message_image_rejects_too_large(client):
    await login(client)
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    oversized = b"0" * (5 * 1024 * 1024 + 1)
    resp = await client.post(
        f"/api/rooms/{room['id']}/messages/image",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert resp.status_code == 413


async def test_message_with_image_broadcasts_and_persists(client):
    await login(client)
    cookie = client.cookies.get("session")
    room = (await client.post("/api/rooms", json={"name": "general"})).json()

    upload = await client.post(
        f"/api/rooms/{room['id']}/messages/image",
        files={"file": ("photo.png", _PNG_BYTES, "image/png")},
    )
    image_url = upload.json()["image_url"]

    ws = _RawAsgiWebSocket()
    try:
        await ws.connect(room["id"], cookie)
        await ws.receive_event("presence_state")
        await ws.send_text(json.dumps({"body": "", "image_url": image_url}))
        evt = await ws.receive_event("new_message")
        assert evt["payload"]["image_url"] == image_url
        assert evt["payload"]["body"] == ""
    finally:
        await ws.close()

    history = (await client.get(f"/api/rooms/{room['id']}/messages")).json()
    assert history[0]["image_url"] == image_url
