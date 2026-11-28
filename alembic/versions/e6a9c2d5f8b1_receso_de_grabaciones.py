"""receso de grabaciones (con fecha de regreso opcional), plazo de conservación del material y año cerrado

Revision ID: e6a9c2d5f8b1
Revises: d5f8b1c4e7a0
Create Date: 2026-11-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a9c2d5f8b1'
down_revision: Union[str, Sequence[str], None] = 'd5f8b1c4e7a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Encendido en los colegios que ya existen: nada cambia hasta que el UTP lo apague.
    op.add_column('colegios', sa.Column('grabaciones_activas', sa.Boolean(), server_default='1', nullable=False))
    op.add_column('colegios', sa.Column('grabaciones_hasta', sa.Date(), nullable=True))
    op.add_column('colegios', sa.Column('dias_conservacion', sa.Integer(), nullable=True))
    op.add_column('colegios', sa.Column('anio_cerrado', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('colegios') as batch:
        batch.drop_column('anio_cerrado')
        batch.drop_column('dias_conservacion')
        batch.drop_column('grabaciones_hasta')
        batch.drop_column('grabaciones_activas')
