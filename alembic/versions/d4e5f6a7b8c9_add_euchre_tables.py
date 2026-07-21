"""add euchre tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'games',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('room_id', sa.Integer(), sa.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='lobby'),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('dealer_seat', sa.Integer(), nullable=True),
        sa.Column('team0_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('team1_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('winning_team', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_games_room_id', 'games', ['room_id'])

    op.create_table(
        'game_players',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_id', sa.Integer(), sa.ForeignKey('games.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('seat', sa.Integer(), nullable=False),
        sa.Column('team', sa.Integer(), nullable=False),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('game_id', 'seat', name='uq_game_players_game_seat'),
        sa.UniqueConstraint('game_id', 'user_id', name='uq_game_players_game_user'),
    )

    op.create_table(
        'game_hands',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_id', sa.Integer(), sa.ForeignKey('games.id', ondelete='CASCADE'), nullable=False),
        sa.Column('hand_num', sa.Integer(), nullable=False),
        sa.Column('dealer_seat', sa.Integer(), nullable=False),
        sa.Column('phase', sa.String(20), nullable=False, server_default='bidding_round1'),
        sa.Column('deal_json', postgresql.JSONB(), nullable=False),
        sa.Column('kitty_json', postgresql.JSONB(), nullable=False),
        sa.Column('turned_up_card', sa.String(2), nullable=False),
        sa.Column('upcard_turned_down', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('trump_suit', sa.String(1), nullable=True),
        sa.Column('maker_seat', sa.Integer(), nullable=True),
        sa.Column('going_alone', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('alone_sitting_out_seat', sa.Integer(), nullable=True),
        sa.Column('current_turn_seat', sa.Integer(), nullable=True),
        sa.Column('current_trick_num', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_trick_leader_seat', sa.Integer(), nullable=True),
        sa.Column('current_trick_plays', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('team0_tricks_won', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('team1_tricks_won', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('result_maker_team', sa.Integer(), nullable=True),
        sa.Column('result_points_team0', sa.Integer(), nullable=True),
        sa.Column('result_points_team1', sa.Integer(), nullable=True),
        sa.Column('result_euchred', sa.Boolean(), nullable=True),
        sa.Column('result_march', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('game_id', 'hand_num', name='uq_game_hands_game_hand_num'),
    )

    op.create_table(
        'game_bids',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('hand_id', sa.Integer(), sa.ForeignKey('game_hands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round', sa.Integer(), nullable=False),
        sa.Column('seat', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('suit', sa.String(1), nullable=True),
        sa.Column('alone', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'game_tricks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('hand_id', sa.Integer(), sa.ForeignKey('game_hands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('trick_num', sa.Integer(), nullable=False),
        sa.Column('leader_seat', sa.Integer(), nullable=False),
        sa.Column('plays_json', postgresql.JSONB(), nullable=False),
        sa.Column('winner_seat', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('hand_id', 'trick_num', name='uq_game_tricks_hand_trick_num'),
    )


def downgrade() -> None:
    op.drop_table('game_tricks')
    op.drop_table('game_bids')
    op.drop_table('game_hands')
    op.drop_table('game_players')
    op.drop_index('ix_games_room_id', table_name='games')
    op.drop_table('games')
