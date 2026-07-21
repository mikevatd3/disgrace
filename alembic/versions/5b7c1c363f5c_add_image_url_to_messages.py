"""add image_url to messages

Revision ID: 5b7c1c363f5c
Revises: d4e5f6a7b8c9
Create Date: 2026-07-21 12:37:23.178400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b7c1c363f5c'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('messages', sa.Column('image_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('messages', 'image_url')
