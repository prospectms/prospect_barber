"""tabelas assinaturas e asaas_webhook_events (Fase 3 - gateway Asaas)

Cria as duas tabelas novas da Fase 3. Tabelas novas e vazias -- sem
backfill, sem dado pré-existente pra migrar.

`assinaturas` é TenantMixin (empresa_id, FK+index+NOT NULL, seguindo o
padrão de qualquer outro model TenantMixin desde a Fase 1-A).
asaas_subscription_id é único: é a chave que o endpoint de webhook usa
pra achar a linha, rodando fora de tenant context.

`asaas_webhook_events` não tem empresa_id (não é TenantMixin) -- é
registro de idempotência do webhook público, resolvido por
asaas_event_id (vem do próprio Asaas, já globalmente único).

Revision ID: 2b7e4f9c6a1d
Revises: 5f8c3d7e9a1b
Create Date: 2026-08-06 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '2b7e4f9c6a1d'
down_revision = '5f8c3d7e9a1b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'assinaturas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('asaas_customer_id', sa.String(length=50), nullable=False),
        sa.Column('asaas_subscription_id', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('plano_id', sa.Integer(), nullable=False),
        sa.Column('valor', sa.Numeric(10, 2), nullable=False),
        sa.Column('periodicidade', sa.String(length=10), nullable=False),
        sa.Column('forma_pagamento', sa.String(length=10), nullable=False),
        sa.Column('inadimplente_desde', sa.DateTime(), nullable=True),
        sa.Column('proximo_vencimento', sa.Date(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id']),
        sa.ForeignKeyConstraint(['plano_id'], ['planos.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asaas_subscription_id', name='assinaturas_asaas_subscription_id_key'),
    )
    op.create_index('ix_assinaturas_empresa_id', 'assinaturas', ['empresa_id'])
    op.create_index('ix_assinaturas_asaas_subscription_id', 'assinaturas', ['asaas_subscription_id'])

    op.create_table(
        'asaas_webhook_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asaas_event_id', sa.String(length=60), nullable=False),
        sa.Column('evento', sa.String(length=40), nullable=False),
        sa.Column('recebido_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asaas_event_id', name='asaas_webhook_events_asaas_event_id_key'),
    )
    op.create_index('ix_asaas_webhook_events_asaas_event_id', 'asaas_webhook_events', ['asaas_event_id'])


def downgrade():
    op.drop_index('ix_asaas_webhook_events_asaas_event_id', table_name='asaas_webhook_events')
    op.drop_table('asaas_webhook_events')

    op.drop_index('ix_assinaturas_asaas_subscription_id', table_name='assinaturas')
    op.drop_index('ix_assinaturas_empresa_id', table_name='assinaturas')
    op.drop_table('assinaturas')
