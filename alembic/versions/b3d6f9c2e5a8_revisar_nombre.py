# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""revisar_nombre: marca los nombres de alumnos que sonaron a broma, para que el profesor los revise

Revision ID: b3d6f9c2e5a8
Revises: a2c5e8b1d4f7
Create Date: 2026-11-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d6f9c2e5a8'
down_revision: Union[str, Sequence[str], None] = 'a2c5e8b1d4f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usuarios', sa.Column('revisar_nombre', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('usuarios') as batch:
        batch.drop_column('revisar_nombre')
