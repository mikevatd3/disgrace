from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reply_to_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(nullable=True)

    room: Mapped["Room"] = relationship()
    user: Mapped["User"] = relationship()
    reply_msg: Mapped["Message | None"] = relationship("Message", foreign_keys="Message.reply_to_id", remote_side="Message.id", uselist=False)
    reactions: Mapped[list["Reaction"]] = relationship(cascade="all, delete-orphan")


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("message_id", "user_id", "emoji", name="uq_reactions"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    emoji: Mapped[str] = mapped_column(String(32), nullable=False)

    user: Mapped["User"] = relationship()


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="lobby")
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    dealer_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team0_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    team1_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winning_team: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    room: Mapped["Room"] = relationship()
    players: Mapped[list["GamePlayer"]] = relationship(cascade="all, delete-orphan", order_by="GamePlayer.seat")
    hands: Mapped[list["GameHand"]] = relationship(cascade="all, delete-orphan", order_by="GameHand.hand_num")


class GamePlayer(Base):
    __tablename__ = "game_players"
    __table_args__ = (
        UniqueConstraint("game_id", "seat", name="uq_game_players_game_seat"),
        UniqueConstraint("game_id", "user_id", name="uq_game_players_game_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    team: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship()


class GameHand(Base):
    __tablename__ = "game_hands"
    __table_args__ = (
        UniqueConstraint("game_id", "hand_num", name="uq_game_hands_game_hand_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    hand_num: Mapped[int] = mapped_column(Integer, nullable=False)
    dealer_seat: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="bidding_round1")

    deal_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    kitty_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    turned_up_card: Mapped[str] = mapped_column(String(2), nullable=False)
    upcard_turned_down: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    trump_suit: Mapped[str | None] = mapped_column(String(1), nullable=True)
    maker_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    going_alone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alone_sitting_out_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)

    current_turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_trick_num: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_trick_leader_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_trick_plays: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    team0_tricks_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    team1_tricks_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    result_maker_team: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_points_team0: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_points_team1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_euchred: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    result_march: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    bids: Mapped[list["GameBid"]] = relationship(cascade="all, delete-orphan", order_by="GameBid.id")
    tricks: Mapped[list["GameTrick"]] = relationship(cascade="all, delete-orphan", order_by="GameTrick.trick_num")


class GameBid(Base):
    __tablename__ = "game_bids"

    id: Mapped[int] = mapped_column(primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("game_hands.id", ondelete="CASCADE"), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    suit: Mapped[str | None] = mapped_column(String(1), nullable=True)
    alone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class GameTrick(Base):
    __tablename__ = "game_tricks"
    __table_args__ = (
        UniqueConstraint("hand_id", "trick_num", name="uq_game_tricks_hand_trick_num"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("game_hands.id", ondelete="CASCADE"), nullable=False)
    trick_num: Mapped[int] = mapped_column(Integer, nullable=False)
    leader_seat: Mapped[int] = mapped_column(Integer, nullable=False)
    plays_json: Mapped[list] = mapped_column(JSONB, nullable=False)
    winner_seat: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
