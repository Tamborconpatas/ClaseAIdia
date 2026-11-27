# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""cupo_por_curso: máximo de alumnos de cada curso, que fija el UTP

Revision ID: a2c5e8b1d4f7
Revises: d8b3e5f7a9c2
Create Date: 2026-11-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2c5e8b1d4f7'
down_revision: Union[str, Sequence[str], None] = 'd8b3e5f7a9c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 45 = máximo legal por sala en Chile; los cursos que ya existen lo reciben tal cual.
    op.add_column('cursos', sa.Column('cupo', sa.Integer(), nullable=False, server_default='45'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('cursos') as batch:
        batch.drop_column('cupo')
