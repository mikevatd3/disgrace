import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import euchre
from app.auth import get_current_user
from app.db import get_db
from app.models import Game, GameBid, GameHand, GamePlayer, GameTrick, Room, User
from app.schemas import (
    BidIn,
    DiscardIn,
    GameHandPublicOut,
    GameHandResultOut,
    GameOut,
    GamePlayerOut,
    PlayCardIn,
)
from app.ws import manager

router = APIRouter(prefix="/api/rooms/{room_id}/games", tags=["games"], dependencies=[Depends(get_current_user)])

ACTIVE_STATUSES = ("lobby", "in_progress")


def _query_options():
    return [
        selectinload(Game.players).selectinload(GamePlayer.user),
        selectinload(Game.hands).selectinload(GameHand.bids),
    ]


async def _load_game(db: AsyncSession, room_id: int, game_id: int) -> Game:
    # populate_existing forces already-identity-mapped relationships (players,
    # hands) to be refreshed -- needed because this is called again within the
    # same request/session right after a commit that added rows to them.
    game = await db.scalar(
        select(Game)
        .where(Game.id == game_id, Game.room_id == room_id)
        .options(*_query_options())
        .execution_options(populate_existing=True)
    )
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


def _current_hand(game: Game) -> GameHand | None:
    return game.hands[-1] if game.hands else None


def _serialize_game(game: Game, viewer_user_id: int) -> GameOut:
    players = [
        GamePlayerOut(
            seat=p.seat,
            team=p.team,
            user_id=p.user_id,
            user_name=p.user.name if p.user else None,
            user_avatar=p.user.avatar_url if p.user else None,
        )
        for p in game.players
    ]
    my_player = next((p for p in game.players if p.user_id == viewer_user_id), None)
    my_seat = my_player.seat if my_player else None

    hand_out = None
    my_hand = None
    h = _current_hand(game)
    if h is not None:
        hand_sizes = {str(seat): len(h.deal_json.get(str(seat), [])) for seat in range(4)}
        if my_seat is not None:
            my_hand = list(h.deal_json.get(str(my_seat), []))

        result = None
        if h.result_points_team0 is not None:
            result = GameHandResultOut(
                maker_team=h.result_maker_team,
                euchred=h.result_euchred,
                march=h.result_march,
                points_team0=h.result_points_team0,
                points_team1=h.result_points_team1,
            )

        hand_out = GameHandPublicOut(
            hand_num=h.hand_num,
            dealer_seat=h.dealer_seat,
            phase=h.phase,
            turned_up_card=h.turned_up_card,
            upcard_turned_down=h.upcard_turned_down,
            trump_suit=h.trump_suit,
            maker_seat=h.maker_seat,
            going_alone=h.going_alone,
            alone_sitting_out_seat=h.alone_sitting_out_seat,
            current_turn_seat=h.current_turn_seat,
            current_trick_num=h.current_trick_num,
            current_trick_leader_seat=h.current_trick_leader_seat,
            current_trick_plays=h.current_trick_plays,
            team0_tricks_won=h.team0_tricks_won,
            team1_tricks_won=h.team1_tricks_won,
            hand_sizes=hand_sizes,
            result=result,
        )

    return GameOut(
        id=game.id,
        room_id=game.room_id,
        status=game.status,
        players=players,
        team0_score=game.team0_score,
        team1_score=game.team1_score,
        winning_team=game.winning_team,
        my_seat=my_seat,
        my_hand=my_hand,
        hand=hand_out,
    )


def _row_to_hand_state(h: GameHand) -> euchre.HandState:
    hands = {int(k): list(v) for k, v in h.deal_json.items()}
    round1_passes = sum(1 for b in h.bids if b.round == 1 and b.action == "pass")
    round2_passes = sum(1 for b in h.bids if b.round == 2 and b.action == "pass")
    return euchre.HandState(
        dealer_seat=h.dealer_seat,
        hands=hands,
        kitty=list(h.kitty_json),
        phase=h.phase,
        turned_up_card=h.turned_up_card,
        upcard_turned_down=h.upcard_turned_down,
        trump_suit=h.trump_suit,
        maker_seat=h.maker_seat,
        going_alone=h.going_alone,
        alone_sitting_out_seat=h.alone_sitting_out_seat,
        current_turn_seat=h.current_turn_seat,
        current_trick_num=h.current_trick_num,
        current_trick_leader_seat=h.current_trick_leader_seat,
        current_trick_plays=[dict(p) for p in h.current_trick_plays],
        team_tricks_won={0: h.team0_tricks_won, 1: h.team1_tricks_won},
        bid_round1_passes=round1_passes,
        bid_round2_passes=round2_passes,
    )


def _apply_hand_state_to_row(h: GameHand, state: euchre.HandState) -> None:
    h.phase = state.phase
    h.deal_json = {str(k): v for k, v in state.hands.items()}
    h.turned_up_card = state.turned_up_card
    h.upcard_turned_down = state.upcard_turned_down
    h.trump_suit = state.trump_suit
    h.maker_seat = state.maker_seat
    h.going_alone = state.going_alone
    h.alone_sitting_out_seat = state.alone_sitting_out_seat
    h.current_turn_seat = state.current_turn_seat
    h.current_trick_num = state.current_trick_num
    h.current_trick_leader_seat = state.current_trick_leader_seat
    h.current_trick_plays = state.current_trick_plays
    h.team0_tricks_won = state.team_tricks_won[0]
    h.team1_tricks_won = state.team_tricks_won[1]
    if state.result is not None:
        h.result_maker_team = state.maker_seat % 2 if state.maker_seat is not None else None
        h.result_points_team0 = state.result["points_team0"]
        h.result_points_team1 = state.result["points_team1"]
        h.result_euchred = state.result["euchred"]
        h.result_march = state.result["march"]


def _deal_new_hand(game: Game, hand_num: int, dealer_seat: int) -> GameHand:
    dealt = euchre.deal()
    return GameHand(
        game_id=game.id,
        hand_num=hand_num,
        dealer_seat=dealer_seat,
        phase="bidding_round1",
        deal_json={str(k): v for k, v in dealt["hands"].items()},
        kitty_json=dealt["kitty"],
        turned_up_card=dealt["kitty"][0],
        current_turn_seat=(dealer_seat + 1) % 4,
    )


async def _broadcast(room_id: int, game: Game) -> None:
    await manager.broadcast_per_user(
        room_id, "game_state", lambda uid: _serialize_game(game, uid).model_dump(mode="json")
    )


@router.get("/current", response_model=GameOut | None)
async def get_current_game(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await db.scalar(
        select(Game)
        .where(Game.room_id == room_id)
        .options(*_query_options())
        .order_by(Game.id.desc())
        .limit(1)
    )
    if game is None:
        return None
    return _serialize_game(game, current_user.id)


@router.post("", response_model=GameOut, status_code=201)
async def start_lobby(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    existing = await db.scalar(
        select(Game).where(Game.room_id == room_id, Game.status.in_(ACTIVE_STATUSES))
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="A game is already active in this room")

    game = Game(room_id=room_id, status="lobby", created_by_user_id=current_user.id)
    db.add(game)
    await db.commit()
    game = await _load_game(db, room_id, game.id)
    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)


@router.post("/{game_id}/join", response_model=GameOut)
async def join_game(
    room_id: int,
    game_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await _load_game(db, room_id, game_id)
    if game.status != "lobby":
        raise HTTPException(status_code=409, detail="Game is not in its lobby phase")
    if any(p.user_id == current_user.id for p in game.players):
        raise HTTPException(status_code=409, detail="Already joined")
    if len(game.players) >= 4:
        raise HTTPException(status_code=409, detail="Lobby is full")

    taken_seats = {p.seat for p in game.players}
    seat = next(s for s in range(4) if s not in taken_seats)
    db.add(GamePlayer(game_id=game.id, user_id=current_user.id, seat=seat, team=seat % 2))
    await db.commit()

    game = await _load_game(db, room_id, game_id)
    if len(game.players) == 4:
        seats = list(range(4))
        random.shuffle(seats)
        ordered_players = sorted(game.players, key=lambda p: p.id)
        # Two-phase reassignment: the (game_id, seat) unique constraint is
        # checked immediately (not deferred), so writing final seats directly
        # can collide with another player's not-yet-updated current seat.
        # Temporary negative seats guarantee no collision in either phase.
        for i, player in enumerate(ordered_players):
            player.seat = -(i + 1)
        await db.flush()
        for player, seat in zip(ordered_players, seats):
            player.seat = seat
            player.team = seat % 2
        game.status = "in_progress"
        game.dealer_seat = 0
        db.add(_deal_new_hand(game, hand_num=1, dealer_seat=0))
        await db.commit()
        game = await _load_game(db, room_id, game_id)

    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)


@router.post("/{game_id}/leave", response_model=GameOut)
async def leave_game(
    room_id: int,
    game_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await _load_game(db, room_id, game_id)
    if game.status != "lobby":
        raise HTTPException(status_code=409, detail="Can only leave while in the lobby")

    player = next((p for p in game.players if p.user_id == current_user.id), None)
    if player is None:
        raise HTTPException(status_code=404, detail="You are not in this game")
    await db.delete(player)
    await db.commit()

    game = await _load_game(db, room_id, game_id)
    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)


def _require_seat(game: Game, user_id: int) -> GamePlayer:
    player = next((p for p in game.players if p.user_id == user_id), None)
    if player is None:
        raise HTTPException(status_code=403, detail="You are not seated in this game")
    return player


@router.post("/{game_id}/bid", response_model=GameOut)
async def bid(
    room_id: int,
    game_id: int,
    payload: BidIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await _load_game(db, room_id, game_id)
    if game.status != "in_progress":
        raise HTTPException(status_code=409, detail="Game is not in progress")
    player = _require_seat(game, current_user.id)
    h = _current_hand(game)
    if h is None:
        raise HTTPException(status_code=409, detail="No active hand")

    state = _row_to_hand_state(h)
    try:
        if h.phase == "bidding_round1":
            euchre.apply_bid_round1(state, player.seat, payload.action, alone=payload.alone)
            round_num = 1
        elif h.phase == "bidding_round2":
            euchre.apply_bid_round2(state, player.seat, payload.action, suit=payload.suit, alone=payload.alone)
            round_num = 2
        else:
            raise ValueError("not in a bidding phase")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.add(GameBid(
        hand_id=h.id, round=round_num, seat=player.seat,
        action=payload.action, suit=payload.suit, alone=payload.alone,
    ))
    _apply_hand_state_to_row(h, state)
    db.add(h)
    await db.commit()

    game = await _load_game(db, room_id, game_id)
    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)


@router.post("/{game_id}/discard", response_model=GameOut)
async def discard(
    room_id: int,
    game_id: int,
    payload: DiscardIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await _load_game(db, room_id, game_id)
    if game.status != "in_progress":
        raise HTTPException(status_code=409, detail="Game is not in progress")
    player = _require_seat(game, current_user.id)
    h = _current_hand(game)
    if h is None:
        raise HTTPException(status_code=409, detail="No active hand")

    state = _row_to_hand_state(h)
    try:
        euchre.apply_dealer_discard(state, player.seat, payload.card)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    _apply_hand_state_to_row(h, state)
    db.add(h)
    await db.commit()

    game = await _load_game(db, room_id, game_id)
    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)


@router.post("/{game_id}/play", response_model=GameOut)
async def play_card(
    room_id: int,
    game_id: int,
    payload: PlayCardIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await _load_game(db, room_id, game_id)
    if game.status != "in_progress":
        raise HTTPException(status_code=409, detail="Game is not in progress")
    player = _require_seat(game, current_user.id)
    h = _current_hand(game)
    if h is None:
        raise HTTPException(status_code=409, detail="No active hand")

    state = _row_to_hand_state(h)
    try:
        euchre.apply_play_card(state, player.seat, payload.card)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    _apply_hand_state_to_row(h, state)
    db.add(h)

    if state.last_completed_trick is not None:
        t = state.last_completed_trick
        db.add(GameTrick(
            hand_id=h.id, trick_num=t["trick_num"], leader_seat=t["leader_seat"],
            plays_json=t["plays"], winner_seat=t["winner_seat"],
        ))

    if state.result is not None:
        game.team0_score += state.result["points_team0"]
        game.team1_score += state.result["points_team1"]
        if game.team0_score >= 10 or game.team1_score >= 10:
            game.status = "completed"
            game.winning_team = 0 if game.team0_score >= 10 else 1
        db.add(game)

    await db.commit()

    game = await _load_game(db, room_id, game_id)
    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)


@router.post("/{game_id}/continue", response_model=GameOut)
async def continue_game(
    room_id: int,
    game_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await _load_game(db, room_id, game_id)
    if game.status != "in_progress":
        raise HTTPException(status_code=409, detail="Game is not in progress")
    _require_seat(game, current_user.id)
    h = _current_hand(game)
    if h is None or h.phase != "hand_review":
        raise HTTPException(status_code=409, detail="Current hand is not awaiting continue")

    next_dealer = (h.dealer_seat + 1) % 4
    game.dealer_seat = next_dealer
    db.add(_deal_new_hand(game, hand_num=h.hand_num + 1, dealer_seat=next_dealer))
    db.add(game)
    await db.commit()

    game = await _load_game(db, room_id, game_id)
    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)


@router.post("/{game_id}/abandon", response_model=GameOut)
async def abandon_game(
    room_id: int,
    game_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    game = await _load_game(db, room_id, game_id)
    if game.status not in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Game is not active")

    game.status = "abandoned"
    db.add(game)
    await db.commit()

    game = await _load_game(db, room_id, game_id)
    await _broadcast(room_id, game)
    return _serialize_game(game, current_user.id)
