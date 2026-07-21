from httpx import ASGITransport, AsyncClient

from app.euchre import effective_suit, legal_plays
from app.main import app
from app.tests.test_api import login


async def _make_room(client) -> int:
    resp = await client.post("/api/rooms", json={"name": "euchre-room"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _seat_four_players(room_id: int) -> tuple[list[dict], dict, int, dict]:
    """Registers 4 users, has each join the room's game lobby via its own
    client (cookies are per-client, so each player gets its own session),
    and returns (users, final_game, game_id, clients_by_seat)."""
    users = []
    clients = []
    for i in range(4):
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        user = await login(c, name=f"player{i}", password="correct-horse-1!")
        users.append(user)

    resp = await clients[0].post(f"/api/rooms/{room_id}/games")
    assert resp.status_code == 201
    game_id = resp.json()["id"]

    game = None
    for c in clients:
        resp = await c.post(f"/api/rooms/{room_id}/games/{game_id}/join")
        assert resp.status_code == 200, resp.text
        game = resp.json()

    seat_by_user = {p["user_id"]: p["seat"] for p in game["players"]}
    clients_by_seat = {seat_by_user[u["id"]]: c for u, c in zip(users, clients)}

    return users, game, game_id, clients_by_seat


async def test_start_lobby_requires_auth(client):
    resp = await client.post("/api/rooms/1/games")
    assert resp.status_code == 401


async def test_double_start_conflicts(client):
    await login(client)
    room_id = await _make_room(client)

    resp = await client.post(f"/api/rooms/{room_id}/games")
    assert resp.status_code == 201

    resp = await client.post(f"/api/rooms/{room_id}/games")
    assert resp.status_code == 409


async def test_four_joins_seats_randomly_and_deals(client):
    await login(client)
    room_id = await _make_room(client)

    _users, game, _game_id, clients_by_seat = await _seat_four_players(room_id)

    assert game["status"] == "in_progress"
    seats = {p["seat"] for p in game["players"]}
    assert seats == {0, 1, 2, 3}
    teams = {p["seat"]: p["team"] for p in game["players"]}
    for seat, team in teams.items():
        assert team == seat % 2

    assert game["hand"] is not None
    assert game["hand"]["phase"] == "bidding_round1"
    assert sum(game["hand"]["hand_sizes"].values()) == 20  # 5 cards x 4 seats

    for c in clients_by_seat.values():
        await c.aclose()


async def test_bid_and_play_flow(client):
    await login(client)
    room_id = await _make_room(client)
    _users, game, game_id, clients_by_seat = await _seat_four_players(room_id)

    dealer_seat = game["hand"]["dealer_seat"]
    turn_order = [(dealer_seat + 1 + i) % 4 for i in range(4)]

    resp = None
    for seat in turn_order:
        resp = await clients_by_seat[seat].post(
            f"/api/rooms/{room_id}/games/{game_id}/bid", json={"action": "pass"}
        )
        assert resp.status_code == 200, resp.text

    state = resp.json()
    assert state["hand"]["phase"] == "bidding_round2"

    caller_seat = state["hand"]["current_turn_seat"]
    turned_down = state["hand"]["turned_up_card"][1]
    other_suit = next(s for s in ["S", "H", "D", "C"] if s != turned_down)
    resp = await clients_by_seat[caller_seat].post(
        f"/api/rooms/{room_id}/games/{game_id}/bid",
        json={"action": "call", "suit": other_suit},
    )
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state["hand"]["phase"] == "playing"
    assert state["hand"]["trump_suit"] == other_suit

    # wrong-turn play should 422
    wrong_seat = (state["hand"]["current_turn_seat"] + 1) % 4
    resp = await clients_by_seat[wrong_seat].post(
        f"/api/rooms/{room_id}/games/{game_id}/play", json={"card": "9S"}
    )
    assert resp.status_code == 422

    for c in clients_by_seat.values():
        await c.aclose()


async def test_full_hand_reaches_review_and_continues(client):
    await login(client)
    room_id = await _make_room(client)
    _users, game, game_id, clients_by_seat = await _seat_four_players(room_id)

    dealer_seat = game["hand"]["dealer_seat"]
    turn_order = [(dealer_seat + 1 + i) % 4 for i in range(4)]

    resp = None
    for seat in turn_order:
        resp = await clients_by_seat[seat].post(
            f"/api/rooms/{room_id}/games/{game_id}/bid", json={"action": "pass"}
        )
        assert resp.status_code == 200, resp.text
    state = resp.json()

    caller_seat = state["hand"]["current_turn_seat"]
    turned_down = state["hand"]["turned_up_card"][1]
    other_suit = next(s for s in ["S", "H", "D", "C"] if s != turned_down)
    resp = await clients_by_seat[caller_seat].post(
        f"/api/rooms/{room_id}/games/{game_id}/bid",
        json={"action": "call", "suit": other_suit},
    )
    assert resp.status_code == 200, resp.text
    state = resp.json()
    trump = state["hand"]["trump_suit"]

    for _ in range(20):
        if state["hand"]["phase"] != "playing":
            break
        seat = state["hand"]["current_turn_seat"]
        resp = await clients_by_seat[seat].get(f"/api/rooms/{room_id}/games/current")
        my_state = resp.json()
        my_hand = my_state["my_hand"]
        led_suit = None
        if my_state["hand"]["current_trick_plays"]:
            led_card = my_state["hand"]["current_trick_plays"][0]["card"]
            led_suit = effective_suit(led_card, trump)
        legal = legal_plays(my_hand, trump, led_suit)
        resp = await clients_by_seat[seat].post(
            f"/api/rooms/{room_id}/games/{game_id}/play", json={"card": legal[0]}
        )
        assert resp.status_code == 200, resp.text
        state = resp.json()

    assert state["hand"]["phase"] == "hand_review"
    assert state["hand"]["result"] is not None
    assert state["team0_score"] + state["team1_score"] in (1, 2, 4)

    completed_hand_num = state["hand"]["hand_num"]
    completed_dealer = state["hand"]["dealer_seat"]

    any_seat = next(iter(clients_by_seat))
    resp = await clients_by_seat[any_seat].post(f"/api/rooms/{room_id}/games/{game_id}/continue")
    assert resp.status_code == 200, resp.text
    state2 = resp.json()
    assert state2["hand"]["hand_num"] == completed_hand_num + 1
    assert state2["hand"]["phase"] == "bidding_round1"
    assert state2["hand"]["dealer_seat"] == (completed_dealer + 1) % 4

    for c in clients_by_seat.values():
        await c.aclose()


async def test_abandon_game_frees_room_for_a_new_lobby(client):
    await login(client)
    room_id = await _make_room(client)

    resp = await client.post(f"/api/rooms/{room_id}/games")
    game_id = resp.json()["id"]

    resp = await client.post(f"/api/rooms/{room_id}/games/{game_id}/abandon")
    assert resp.status_code == 200
    assert resp.json()["status"] == "abandoned"

    resp = await client.post(f"/api/rooms/{room_id}/games")
    assert resp.status_code == 201
