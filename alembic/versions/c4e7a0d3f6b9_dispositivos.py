# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""dispositivos: qué equipos usan la aplicación (sin IP), para el panel de estado y para ubicar el origen de un nombre indebido

Revision ID: c4e7a0d3f6b9
Revises: b3d6f9c2e5a8
Create Date: 2026-11-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e7a0d3f6b9'
down_revision: Union[str, Sequence[str], None] = 'b3d6f9c2e5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'dispositivos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('colegio_id', sa.Integer(), sa.ForeignKey('colegios.id'), nullable=False),
        sa.Column('codigo', sa.String(), nullable=False),
        sa.Column('resumen', sa.String(), nullable=False),
        sa.Column('ultima_vez', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('colegio_id', 'codigo', name='uq_dispositivo_codigo'),
    )
    with op.batch_alter_table('usuarios') as batch:
        batch.add_column(sa.Column('visto_en', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('dispositivo_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('registro_dispositivo_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_usuario_dispositivo', 'dispositivos', ['dispositivo_id'], ['id'])
        batch.create_foreign_key('fk_usuario_registro_dispositivo', 'dispositivos', ['registro_dispositivo_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('usuarios') as batch:
        batch.drop_constraint('fk_usuario_registro_dispositivo', type_='foreignkey')
        batch.drop_constraint('fk_usuario_dispositivo', type_='foreignkey')
        batch.drop_column('registro_dispositivo_id')
        batch.drop_column('dispositivo_id')
        batch.drop_column('visto_en')
    op.drop_table('dispositivos')
