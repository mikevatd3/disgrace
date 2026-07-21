import re
from datetime import datetime

from pydantic import BaseModel, field_validator


def _validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one number")
    if not re.search(r"[^A-Za-z0-9]", v):
        raise ValueError("Password must contain at least one special character")
    return v


class UserOut(BaseModel):
    id: int
    name: str
    avatar_url: str | None = None

    model_config = {"from_attributes": True}


class AvatarUpdate(BaseModel):
    avatar_url: str | None = None


class RegisterCreate(BaseModel):
    name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password(v)


class LoginCreate(BaseModel):
    name: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password(v)


class RoomCreate(BaseModel):
    name: str


class RoomOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class ReactionOut(BaseModel):
    emoji: str
    user_id: int
    user_name: str | None = None

    model_config = {"from_attributes": True}


class ReplySnippet(BaseModel):
    id: int
    user_name: str | None = None
    body: str


class MessageOut(BaseModel):
    id: int
    room_id: int
    user_id: int
    user_name: str | None = None
    user_avatar: str | None = None
    reply_to: ReplySnippet | None = None
    body: str
    edited_at: datetime | None = None
    created_at: datetime
    reactions: list[ReactionOut] = []

    model_config = {"from_attributes": True}


class MessageEdit(BaseModel):
    body: str


class ReactionToggle(BaseModel):
    emoji: str


class GamePlayerOut(BaseModel):
    seat: int
    team: int
    user_id: int
    user_name: str | None = None
    user_avatar: str | None = None

    model_config = {"from_attributes": True}


class GameHandResultOut(BaseModel):
    maker_team: int | None = None
    euchred: bool | None = None
    march: bool | None = None
    points_team0: int | None = None
    points_team1: int | None = None


class GameHandPublicOut(BaseModel):
    hand_num: int
    dealer_seat: int
    phase: str
    turned_up_card: str | None = None
    upcard_turned_down: bool
    trump_suit: str | None = None
    maker_seat: int | None = None
    going_alone: bool
    alone_sitting_out_seat: int | None = None
    current_turn_seat: int | None = None
    current_trick_num: int
    current_trick_leader_seat: int | None = None
    current_trick_plays: list[dict]
    team0_tricks_won: int
    team1_tricks_won: int
    hand_sizes: dict[str, int]
    result: GameHandResultOut | None = None


class GameOut(BaseModel):
    id: int
    room_id: int
    status: str
    players: list[GamePlayerOut]
    team0_score: int
    team1_score: int
    winning_team: int | None = None
    my_seat: int | None = None
    my_hand: list[str] | None = None
    hand: GameHandPublicOut | None = None


class BidIn(BaseModel):
    action: str
    suit: str | None = None
    alone: bool = False


class DiscardIn(BaseModel):
    card: str


class PlayCardIn(BaseModel):
    card: str
