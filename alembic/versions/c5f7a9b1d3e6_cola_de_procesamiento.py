# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""grabaciones: cuando el trabajador tomó la clase (cola de procesamiento con prioridad)

Una clase PROCESANDO sin `iniciada_en` está en la cola esperando su turno; con `iniciada_en`, ya la tomó un trabajador.

Revision ID: c5f7a9b1d3e6
Revises: b4e6a8c0d2f5
Create Date: 2026-10-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5f7a9b1d3e6'
down_revision: Union[str, Sequence[str], None] = 'b4e6a8c0d2f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('grabaciones', sa.Column('iniciada_en', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('grabaciones', 'iniciada_en')
