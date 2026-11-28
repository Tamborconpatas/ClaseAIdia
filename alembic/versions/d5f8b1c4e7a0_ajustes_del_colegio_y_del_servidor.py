# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""ajustes_del_colegio_y_del_servidor: lo que antes solo se cambiaba con variables de entorno, ahora lo decide el UTP en «Ajustes»

Revision ID: d5f8b1c4e7a0
Revises: c4e7a0d3f6b9
Create Date: 2026-11-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5f8b1c4e7a0'
down_revision: Union[str, Sequence[str], None] = 'c4e7a0d3f6b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nulos = «el valor predeterminado» (el de las variables de entorno), así que un colegio que ya existe no cambia de comportamiento.
    op.add_column('colegios', sa.Column('horas_revision', sa.Integer(), nullable=True))
    op.add_column('colegios', sa.Column('minutos_corte', sa.Integer(), nullable=True))
    op.create_table(
        'ajustes_servidor',
        sa.Column('clave', sa.String(), nullable=False),
        sa.Column('valor', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('clave'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('ajustes_servidor')
    with op.batch_alter_table('colegios') as batch:
        batch.drop_column('minutos_corte')
        batch.drop_column('horas_revision')
