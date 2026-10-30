# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""revision del material: retirado y generado_en (publicacion provisoria)

Revision ID: b4d2f81c6e17
Revises: a7e3c91d2b40
Create Date: 2026-10-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d2f81c6e17'
down_revision: Union[str, Sequence[str], None] = 'a7e3c91d2b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default constante: SQLite no deja agregar una columna NOT NULL sin default a una tabla con filas.
    op.add_column('contenido_clases', sa.Column('retirado', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('contenido_clases', sa.Column('generado_en', sa.DateTime(), nullable=True))
    # Las filas que ya existían empiezan su plazo de revisión ahora.
    op.execute("UPDATE contenido_clases SET generado_en = CURRENT_TIMESTAMP")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('contenido_clases', 'generado_en')
    op.drop_column('contenido_clases', 'retirado')
