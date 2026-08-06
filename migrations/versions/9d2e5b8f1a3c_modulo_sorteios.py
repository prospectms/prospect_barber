"""adiciona modulo 'sorteios' aos planos pro/ilimitado

Migração de dados só — sem mudança de schema. Decisão explícita do
usuário (Fase 1-B, ver combinado): Raffle ganha @requer_modulo('sorteios')
em vez de ficar liberado pra todos os planos quando
SATELLITE_FEATURES_ENABLED virar True.

Revision ID: 9d2e5b8f1a3c
Revises: 7a3f9c1d2b4e
Create Date: 2026-08-06 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9d2e5b8f1a3c'
down_revision = '7a3f9c1d2b4e'
branch_labels = None
depends_on = None

_PLANOS_TBL = sa.table(
    'planos',
    sa.column('id', sa.Integer),
    sa.column('nome', sa.String),
    sa.column('modulos_incluidos', sa.JSON),
)
_PLANOS_COM_SORTEIOS = ('pro', 'ilimitado')


def upgrade():
    conn = op.get_bind()
    for nome in _PLANOS_COM_SORTEIOS:
        row = conn.execute(
            sa.select(_PLANOS_TBL.c.id, _PLANOS_TBL.c.modulos_incluidos)
            .where(_PLANOS_TBL.c.nome == nome)
        ).first()
        if row is None:
            continue
        modulos = list(row.modulos_incluidos or [])
        if 'sorteios' not in modulos:
            modulos.append('sorteios')
            conn.execute(
                _PLANOS_TBL.update()
                .where(_PLANOS_TBL.c.id == row.id)
                .values(modulos_incluidos=modulos)
            )


def downgrade():
    conn = op.get_bind()
    for nome in _PLANOS_COM_SORTEIOS:
        row = conn.execute(
            sa.select(_PLANOS_TBL.c.id, _PLANOS_TBL.c.modulos_incluidos)
            .where(_PLANOS_TBL.c.nome == nome)
        ).first()
        if row is None:
            continue
        modulos = [m for m in (row.modulos_incluidos or []) if m != 'sorteios']
        conn.execute(
            _PLANOS_TBL.update()
            .where(_PLANOS_TBL.c.id == row.id)
            .values(modulos_incluidos=modulos)
        )
