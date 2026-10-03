"""colegios: ajuste de las fotos de la pizarra (lo decide el UTP en la aplicacion)

Revision ID: b4e6a8c0d2f5
Revises: a3d5f7b9c1e4
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e6a8c0d2f5'
down_revision: Union[str, Sequence[str], None] = 'a3d5f7b9c1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('colegios', sa.Column('fotos_pizarra', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('colegios', 'fotos_pizarra')
