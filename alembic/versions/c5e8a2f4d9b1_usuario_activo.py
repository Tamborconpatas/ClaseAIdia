# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""usuarios.activo: desactivar personal sin borrar su historial

Revision ID: c5e8a2f4d9b1
Revises: b4d2f81c6e17
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e8a2f4d9b1'
down_revision: Union[str, Sequence[str], None] = 'b4d2f81c6e17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default constante: SQLite no deja agregar una columna NOT NULL sin default a una tabla con filas.
    op.add_column('usuarios', sa.Column('activo', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usuarios', 'activo')
