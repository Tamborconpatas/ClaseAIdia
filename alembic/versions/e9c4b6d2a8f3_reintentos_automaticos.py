# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""grabaciones: reintentos automaticos del procesamiento

Revision ID: e9c4b6d2a8f3
Revises: d7a2c9e4b6f1
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9c4b6d2a8f3'
down_revision: Union[str, Sequence[str], None] = 'd7a2c9e4b6f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default constante: SQLite no deja agregar una columna NOT NULL sin default a una tabla con filas.
    op.add_column('grabaciones', sa.Column('intentos', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('grabaciones', sa.Column('reintento_en', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('grabaciones', 'reintento_en')
    op.drop_column('grabaciones', 'intentos')
