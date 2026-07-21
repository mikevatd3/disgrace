"""Pure euchre rules engine: dealing, legal plays, trick resolution, scoring,
and the bidding/play state machine. No FastAPI or DB imports -- this module
is a plain library operating on primitive data (card strings, dicts, a
HandState dataclass) so it can be unit tested in isolation.

Card encoding: 2-character strings, rank + suit.
  rank: "9", "T", "J", "Q", "K", "A"
  suit: "S" (spades), "H" (hearts), "D" (diamonds), "C" (clubs)
Seats are ints 0-3. Seats 0 & 2 are team 0; seats 1 & 3 are team 1
(partners sit across from each other). Turn order is (seat + 1) % 4.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

SUITS = ["S", "H", "D", "C"]
RANKS = ["9", "T", "J", "Q", "K", "A"]
RANK_ORDER = {r: i for i, r in enumerate(RANKS)}

RED_SUITS = {"H", "D"}
BLACK_SUITS = {"S", "C"}

SAME_COLOR_SUIT = {
    "S": "C", "C": "S",
    "H": "D", "D": "H",
}


def build_deck() -> list[str]:
    return [rank + suit for suit in SUITS for rank in RANKS]


def deal(deck: list[str] | None = None) -> dict:
    """Shuffle (unless a deck is provided, e.g. for deterministic tests) and
    deal 5 cards to each of 4 seats, with 4 cards left in the kitty."""
    cards = list(deck) if deck is not None else build_deck()
    if deck is None:
        random.shuffle(cards)
    if len(cards) != 24:
        raise ValueError("deck must contain exactly 24 cards")

    hands = {seat: sorted(cards[seat * 5:(seat + 1) * 5]) for seat in range(4)}
    kitty = cards[20:24]
    return {"hands": hands, "kitty": kitty}


def left_bower_suit(trump: str) -> str:
    return SAME_COLOR_SUIT[trump]


def is_right_bower(card: str, trump: str) -> bool:
    return card == "J" + trump


def is_left_bower(card: str, trump: str) -> bool:
    return card == "J" + left_bower_suit(trump)


def effective_suit(card: str, trump: str | None) -> str:
    """The suit a card counts as for follow-suit/trick purposes. The left
    bower counts as trump, not its printed suit."""
    if trump and is_left_bower(card, trump):
        return trump
    return card[1]


def card_strength(card: str, trump: str, led_suit: str) -> int:
    """Higher is stronger. Only meaningful for comparing cards within the
    same trick; a card that doesn't follow suit and isn't trump is weakest
    and never wins (handled by determine_trick_winner filtering)."""
    suit = effective_suit(card, trump)
    rank = card[0]

    if is_right_bower(card, trump):
        return 1000
    if is_left_bower(card, trump):
        return 999
    if suit == trump:
        return 500 + RANK_ORDER[rank]
    if suit == led_suit:
        return 100 + RANK_ORDER[rank]
    return RANK_ORDER[rank]


def legal_plays(hand: list[str], trump: str, led_suit: str | None) -> list[str]:
    """Cards from `hand` that are legal to play. Must follow the led suit
    (using effective_suit, so the left bower counts as trump) if able."""
    if led_suit is None:
        return list(hand)
    followers = [c for c in hand if effective_suit(c, trump) == led_suit]
    return followers if followers else list(hand)


def determine_trick_winner(plays: list[tuple[int, str]], trump: str, led_suit: str) -> int:
    """plays: list of (seat, card) in play order. Returns the winning seat."""
    return max(plays, key=lambda p: card_strength(p[1], trump, led_suit))[0]


def score_hand(maker_team: int, team_tricks: dict[int, int], going_alone: bool) -> dict:
    """team_tricks: {0: tricks_won_by_team0, 1: tricks_won_by_team1}."""
    defending_team = 1 - maker_team
    maker_tricks = team_tricks[maker_team]

    if maker_tricks >= 3:
        march = maker_tricks == 5
        if march:
            points = 4 if going_alone else 2
        else:
            points = 1
        return {
            "points_team0": points if maker_team == 0 else 0,
            "points_team1": points if maker_team == 1 else 0,
            "euchred": False,
            "march": march,
        }

    return {
        "points_team0": 2 if defending_team == 0 else 0,
        "points_team1": 2 if defending_team == 1 else 0,
        "euchred": True,
        "march": False,
    }


@dataclass
class HandState:
    dealer_seat: int
    hands: dict[int, list[str]]
    kitty: list[str]
    phase: str = "bidding_round1"
    turned_up_card: str | None = None
    upcard_turned_down: bool = False
    trump_suit: str | None = None
    maker_seat: int | None = None
    going_alone: bool = False
    alone_sitting_out_seat: int | None = None
    current_turn_seat: int | None = None
    current_trick_num: int = 0
    current_trick_leader_seat: int | None = None
    current_trick_plays: list[dict] = field(default_factory=list)
    team_tricks_won: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0})
    bid_round1_passes: int = 0
    bid_round2_passes: int = 0
    result: dict | None = None
    last_completed_trick: dict | None = None

    def __post_init__(self) -> None:
        if self.turned_up_card is None:
            self.turned_up_card = self.kitty[0]
        if self.current_turn_seat is None:
            self.current_turn_seat = (self.dealer_seat + 1) % 4


def _next_seat(seat: int) -> int:
    return (seat + 1) % 4


def apply_bid_round1(state: HandState, seat: int, action: str, alone: bool = False) -> HandState:
    if state.phase != "bidding_round1":
        raise ValueError("not in round 1 bidding")
    if seat != state.current_turn_seat:
        raise ValueError("not your turn")
    if action not in ("pass", "order_up"):
        raise ValueError("invalid action for round 1")

    if action == "order_up":
        assert state.turned_up_card is not None
        trump = state.turned_up_card[1]
        state.trump_suit = trump
        state.maker_seat = seat
        state.going_alone = alone
        state.alone_sitting_out_seat = _partner_seat(seat) if alone else None

        dealer = state.dealer_seat
        state.hands[dealer] = state.hands[dealer] + [state.turned_up_card]
        state.phase = "dealer_discard"
        state.current_turn_seat = dealer
        return state

    state.bid_round1_passes += 1
    if state.bid_round1_passes == 4:
        state.phase = "bidding_round2"
        state.upcard_turned_down = True
        state.current_turn_seat = _next_seat(state.dealer_seat)
        state.bid_round2_passes = 0
    else:
        state.current_turn_seat = _next_seat(seat)
    return state


def apply_bid_round2(state: HandState, seat: int, action: str, suit: str | None = None, alone: bool = False) -> HandState:
    if state.phase != "bidding_round2":
        raise ValueError("not in round 2 bidding")
    if seat != state.current_turn_seat:
        raise ValueError("not your turn")
    if action not in ("pass", "call"):
        raise ValueError("invalid action for round 2")

    assert state.turned_up_card is not None
    turned_down_suit = state.turned_up_card[1]
    is_dealer = seat == state.dealer_seat
    dealer_forced = is_dealer and state.bid_round2_passes == 3

    if action == "pass":
        if dealer_forced:
            raise ValueError("dealer must call (screw the dealer)")
        state.bid_round2_passes += 1
        state.current_turn_seat = _next_seat(seat)
        return state

    if suit is None or suit not in SUITS:
        raise ValueError("must specify a valid suit to call")
    if suit == turned_down_suit:
        raise ValueError("cannot call the turned-down suit")

    state.trump_suit = suit
    state.maker_seat = seat
    state.going_alone = alone
    state.alone_sitting_out_seat = _partner_seat(seat) if alone else None
    state.phase = "playing"
    state.current_turn_seat = _next_seat(state.dealer_seat)
    if state.alone_sitting_out_seat is not None and state.current_turn_seat == state.alone_sitting_out_seat:
        state.current_turn_seat = _next_seat(state.current_turn_seat)
    state.current_trick_leader_seat = state.current_turn_seat
    return state


def apply_dealer_discard(state: HandState, seat: int, card: str) -> HandState:
    if state.phase != "dealer_discard":
        raise ValueError("not in dealer discard phase")
    if seat != state.dealer_seat:
        raise ValueError("only the dealer may discard here")
    if card not in state.hands[seat]:
        raise ValueError("card not in hand")

    state.hands[seat] = [c for c in state.hands[seat] if c != card]
    state.phase = "playing"
    state.current_turn_seat = _next_seat(state.dealer_seat)
    if state.alone_sitting_out_seat is not None and state.current_turn_seat == state.alone_sitting_out_seat:
        state.current_turn_seat = _next_seat(state.current_turn_seat)
    state.current_trick_leader_seat = state.current_turn_seat
    return state


def _partner_seat(seat: int) -> int:
    return (seat + 2) % 4


def apply_play_card(state: HandState, seat: int, card: str) -> HandState:
    if state.phase != "playing":
        raise ValueError("not in playing phase")
    if seat != state.current_turn_seat:
        raise ValueError("not your turn")
    if state.alone_sitting_out_seat is not None and seat == state.alone_sitting_out_seat:
        raise ValueError("this seat is sitting out (going alone)")
    if card not in state.hands[seat]:
        raise ValueError("card not in hand")

    assert state.trump_suit is not None
    trump = state.trump_suit

    led_suit = None
    if state.current_trick_plays:
        led_card = state.current_trick_plays[0]["card"]
        led_suit = effective_suit(led_card, trump)

    legal = legal_plays(state.hands[seat], trump, led_suit)
    if card not in legal:
        raise ValueError("must follow suit")

    state.last_completed_trick = None
    state.hands[seat] = [c for c in state.hands[seat] if c != card]
    state.current_trick_plays.append({"seat": seat, "card": card})

    active_seats = [s for s in range(4) if s != state.alone_sitting_out_seat]
    if len(state.current_trick_plays) < len(active_seats):
        state.current_turn_seat = _next_active_seat(seat, state.alone_sitting_out_seat)
        return state

    led_suit = effective_suit(state.current_trick_plays[0]["card"], trump)
    plays = [(p["seat"], p["card"]) for p in state.current_trick_plays]
    winner = determine_trick_winner(plays, trump, led_suit)
    winning_team = winner % 2
    state.team_tricks_won[winning_team] += 1

    state.last_completed_trick = {
        "trick_num": state.current_trick_num,
        "leader_seat": state.current_trick_leader_seat,
        "plays": list(state.current_trick_plays),
        "winner_seat": winner,
    }

    state.current_trick_num += 1
    state.current_trick_plays = []
    state.current_trick_leader_seat = winner
    state.current_turn_seat = winner

    if state.current_trick_num == 5:
        assert state.maker_seat is not None
        result = score_hand(state.maker_seat % 2, state.team_tricks_won, state.going_alone)
        state.result = result
        state.phase = "hand_review"
        state.current_turn_seat = None

    return state


def _next_active_seat(seat: int, sitting_out: int | None) -> int:
    nxt = _next_seat(seat)
    if sitting_out is not None and nxt == sitting_out:
        nxt = _next_seat(nxt)
    return nxt
