"""fotos_pizarra: texto leido de las fotos de la pizarra de una clase

Revision ID: f1b7d3a9c5e2
Revises: e9c4b6d2a8f3
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b7d3a9c5e2'
down_revision: Union[str, Sequence[str], None] = 'e9c4b6d2a8f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fotos_pizarra',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('grabacion_id', sa.Integer(), nullable=False),
        sa.Column('segundo', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('texto', sa.String(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('creada_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['grabacion_id'], ['grabaciones.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fotos_pizarra_grabacion_id'), 'fotos_pizarra', ['grabacion_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_fotos_pizarra_grabacion_id'), table_name='fotos_pizarra')
    op.drop_table('fotos_pizarra')
