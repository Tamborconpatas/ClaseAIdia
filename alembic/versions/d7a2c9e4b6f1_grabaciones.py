"""grabaciones: sesion de grabacion de una clase (control en vivo)

Revision ID: d7a2c9e4b6f1
Revises: c5e8a2f4d9b1
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a2c9e4b6f1'
down_revision: Union[str, Sequence[str], None] = 'c5e8a2f4d9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'grabaciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clase_id', sa.Integer(), nullable=False),
        sa.Column('estado', sa.Enum('ESPERANDO', 'GRABANDO', 'PAUSADA', 'TERMINANDO', 'PROCESANDO', 'TERMINADA', 'ERROR', name='estadograbacion'), nullable=False),
        sa.Column('silenciada', sa.Boolean(), nullable=False),
        sa.Column('corte_en', sa.DateTime(), nullable=False),
        sa.Column('grabador_id', sa.String(), nullable=True),
        sa.Column('latido_en', sa.DateTime(), nullable=True),
        sa.Column('segundos_grabados', sa.Integer(), nullable=False),
        sa.Column('nivel', sa.Float(), nullable=False),
        sa.Column('trozos', sa.Integer(), nullable=False),
        sa.Column('bytes_recibidos', sa.Integer(), nullable=False),
        sa.Column('mime', sa.String(), nullable=True),
        sa.Column('creada_en', sa.DateTime(), nullable=False),
        sa.Column('terminando_desde', sa.DateTime(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['clase_id'], ['clases.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clase_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('grabaciones')
