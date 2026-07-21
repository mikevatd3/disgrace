import random

import pytest

from app.euchre import (
    SUITS,
    HandState,
    apply_bid_round1,
    apply_bid_round2,
    apply_dealer_discard,
    apply_play_card,
    build_deck,
    deal,
    determine_trick_winner,
    effective_suit,
    legal_plays,
    score_hand,
)


def test_effective_suit_right_bower_is_trump():
    assert effective_suit("JS", "S") == "S"


def test_effective_suit_left_bower_counts_as_trump():
    # jack of clubs is the left bower when trump is spades (same color)
    assert effective_suit("JC", "S") == "S"
    # its printed suit is clubs, which only matters when trump isn't spades
    assert effective_suit("JC", "H") == "C"


def test_legal_plays_must_follow_led_suit():
    hand = ["9H", "TH", "AC"]
    assert legal_plays(hand, "S", "H") == ["9H", "TH"]


def test_legal_plays_left_bower_counts_as_trump_for_follow_suit():
    # trump spades, led suit is spades (trump led); hand holds the left
    # bower (JC, same color as spades) plus off-suit cards with no other
    # spades -- JC must be played since it counts as trump/spades here.
    hand = ["JC", "9H", "AD"]
    assert legal_plays(hand, "S", "S") == ["JC"]


def test_legal_plays_left_bower_does_not_follow_its_printed_suit():
    # trump spades; led suit is clubs (led by an actual club).
    # JC is the left bower, so it counts as spades here, NOT clubs --
    # it must not be forced to follow a club lead.
    hand = ["JC", "9C", "AD"]
    assert legal_plays(hand, "S", "C") == ["9C"]


def test_legal_plays_no_follow_allows_anything():
    hand = ["9H", "TC", "AC"]
    assert set(legal_plays(hand, "S", "D")) == {"9H", "TC", "AC"}


def test_trick_winner_right_bower_beats_left_bower_and_other_trump():
    plays = [(0, "JS"), (1, "JC"), (2, "AS"), (3, "9H")]
    assert determine_trick_winner(plays, "S", "H") == 0  # JS = right bower


def test_trick_winner_left_bower_beats_other_trump():
    plays = [(0, "AS"), (1, "JC"), (2, "9H")]
    assert determine_trick_winner(plays, "S", "H") == 1  # JC = left bower


def test_trick_winner_led_suit_beats_off_suit_non_trump():
    plays = [(0, "9H"), (1, "AC"), (2, "TH")]
    assert determine_trick_winner(plays, "S", "H") == 2  # TH highest of led suit


def test_trick_winner_off_suit_never_wins_over_led_suit():
    plays = [(0, "9H"), (1, "AC")]
    assert determine_trick_winner(plays, "S", "H") == 0


def test_score_hand_normal_make():
    result = score_hand(0, {0: 3, 1: 2}, going_alone=False)
    assert result == {"points_team0": 1, "points_team1": 0, "euchred": False, "march": False}


def test_score_hand_march():
    result = score_hand(1, {0: 0, 1: 5}, going_alone=False)
    assert result == {"points_team0": 0, "points_team1": 2, "euchred": False, "march": True}


def test_score_hand_alone_march():
    result = score_hand(0, {0: 5, 1: 0}, going_alone=True)
    assert result == {"points_team0": 4, "points_team1": 0, "euchred": False, "march": True}


def test_score_hand_euchred():
    result = score_hand(0, {0: 2, 1: 3}, going_alone=False)
    assert result == {"points_team0": 0, "points_team1": 2, "euchred": True, "march": False}


def _fresh_state(dealer_seat=0, hands=None, kitty=None):
    hands = hands or {s: ["9S", "TS", "9H", "TH", "9D"] for s in range(4)}
    kitty = kitty or ["JS", "9C", "AC", "KC"]
    return HandState(dealer_seat=dealer_seat, hands=hands, kitty=kitty)


def _bidding_order(dealer_seat):
    return [(dealer_seat + 1 + i) % 4 for i in range(4)]


def test_screw_the_dealer_forces_dealer_to_call():
    state = _fresh_state(dealer_seat=0)
    for seat in _bidding_order(0):
        apply_bid_round1(state, seat, "pass")
    assert state.phase == "bidding_round2"
    assert state.current_turn_seat == 1  # left of dealer

    apply_bid_round2(state, 1, "pass")
    apply_bid_round2(state, 2, "pass")
    apply_bid_round2(state, 3, "pass")
    assert state.current_turn_seat == 0

    with pytest.raises(ValueError, match="screw the dealer"):
        apply_bid_round2(state, 0, "pass")

    # dealer must call something other than the turned-down suit
    turned_down = state.turned_up_card[1]
    other_suit = next(s for s in ["S", "H", "D", "C"] if s != turned_down)
    apply_bid_round2(state, 0, "call", suit=other_suit)
    assert state.trump_suit == other_suit
    assert state.maker_seat == 0
    assert state.phase == "playing"


def test_bid_round2_cannot_call_turned_down_suit():
    state = _fresh_state(dealer_seat=0)
    for seat in _bidding_order(0):
        apply_bid_round1(state, seat, "pass")

    turned_down = state.turned_up_card[1]
    with pytest.raises(ValueError, match="turned-down"):
        apply_bid_round2(state, 1, "call", suit=turned_down)


def test_order_up_gives_dealer_the_upcard_then_discard():
    kitty = ["JS", "9C", "AC", "KC"]
    hands = {s: ["9S", "TS", "9H", "TH", "9D"] for s in range(4)}
    state = _fresh_state(dealer_seat=0, hands=hands, kitty=kitty)

    apply_bid_round1(state, 1, "order_up")
    assert state.trump_suit == "S"
    assert state.maker_seat == 1
    assert state.phase == "dealer_discard"
    assert "JS" in state.hands[0]
    assert len(state.hands[0]) == 6

    apply_dealer_discard(state, 0, "9D")
    assert len(state.hands[0]) == 5
    assert "9D" not in state.hands[0]
    assert state.phase == "playing"
    assert state.current_turn_seat == 1  # left of dealer leads


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_full_hand_simulation_end_to_end(seed):
    # Drives a real shuffled deal end-to-end through the state machine,
    # always choosing a legal card via legal_plays() at each turn so this
    # exercises dealing, round-2 bidding, and full trick play without
    # hand-authored legality assumptions.
    random.seed(seed)
    shuffled = build_deck()
    random.shuffle(shuffled)
    dealt = deal(shuffled)
    state = HandState(dealer_seat=0, hands=dealt["hands"], kitty=dealt["kitty"])

    for seat in _bidding_order(0):
        apply_bid_round1(state, seat, "pass")
    assert state.phase == "bidding_round2"

    turned_down = state.turned_up_card[1]
    other_suit = next(s for s in SUITS if s != turned_down)
    apply_bid_round2(state, state.current_turn_seat, "call", suit=other_suit)
    assert state.phase == "playing"
    trump = state.trump_suit

    for _ in range(20):
        if state.phase != "playing":
            break
        seat = state.current_turn_seat
        led_suit = None
        if state.current_trick_plays:
            led_card = state.current_trick_plays[0]["card"]
            led_suit = effective_suit(led_card, trump)
        legal = legal_plays(state.hands[seat], trump, led_suit)
        apply_play_card(state, seat, legal[0])

    assert state.phase == "hand_review"
    assert state.result is not None
    assert state.team_tricks_won[0] + state.team_tricks_won[1] == 5
    assert state.result["points_team0"] + state.result["points_team1"] in (1, 2, 4)
