"""codigo de un solo uso para reseteo de PIN

Revision ID: a7e3c91d2b40
Revises: cd247e1feda5
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e3c91d2b40'
down_revision: Union[str, Sequence[str], None] = 'cd247e1feda5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usuarios', sa.Column('codigo_reset_hash', sa.String(), nullable=True))
    op.add_column('usuarios', sa.Column('codigo_reset_vence', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usuarios', 'codigo_reset_vence')
    op.drop_column('usuarios', 'codigo_reset_hash')
