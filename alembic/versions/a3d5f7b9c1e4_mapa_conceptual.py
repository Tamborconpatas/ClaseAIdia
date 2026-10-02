"""contenido_clases: mapa conceptual (relaciones entre conceptos)

Revision ID: a3d5f7b9c1e4
Revises: f1b7d3a9c5e2
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3d5f7b9c1e4'
down_revision: Union[str, Sequence[str], None] = 'f1b7d3a9c5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('contenido_clases', sa.Column('mapa_conceptual', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('contenido_clases', 'mapa_conceptual')
