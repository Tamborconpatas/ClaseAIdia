"""usuarios.version_sesion: revocar las sesiones abiertas de una cuenta

Revision ID: d8b3e5f7a9c2
Revises: c5f7a9b1d3e6
Create Date: 2026-10-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8b3e5f7a9c2'
down_revision: Union[str, Sequence[str], None] = 'c5f7a9b1d3e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default constante: SQLite no deja agregar una columna NOT NULL sin default a una tabla con filas.
    op.add_column('usuarios', sa.Column('version_sesion', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usuarios', 'version_sesion')
