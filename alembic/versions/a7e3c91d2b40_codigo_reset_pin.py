# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""codigo de un solo uso para reseteo de PIN

Revision ID: a7e3c91d2b40
Revises: cd247e1feda5
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e3c91d2b40'
down_revision: Union[str, Sequence[str], None] = 'cd247e1feda5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usuarios', sa.Column('codigo_reset_hash', sa.String(), nullable=True))
    op.add_column('usuarios', sa.Column('codigo_reset_vence', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usuarios', 'codigo_reset_vence')
    op.drop_column('usuarios', 'codigo_reset_hash')
