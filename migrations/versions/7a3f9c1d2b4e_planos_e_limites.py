"""planos e limites (Fase 2)

Cria a tabela `planos` (tiers da plataforma — free/essencial/pro/
ilimitado) com seed dos 4 planos, transforma `empresas.plano_id` (Integer
solto desde a Fase 1-A) numa FK real, adiciona `empresas.periodicidade`/
`preco_congelado`, `appointments.agendamento_original_id` (self-FK,
marca remarcação) e a tabela `uso_mensal` (contador de agendamentos por
empresa/mês, só para aviso — nunca bloqueio).

Revision ID: 7a3f9c1d2b4e
Revises: 45c96fce867f
Create Date: 2026-08-04 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7a3f9c1d2b4e'
down_revision = '45c96fce867f'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ════════════════════════════════════════════════════════════════
    # 1. Tabela planos + seed
    # ════════════════════════════════════════════════════════════════
    op.create_table(
        'planos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=20), nullable=False),
        sa.Column('max_unidades', sa.Integer(), nullable=True),
        sa.Column('max_usuarios', sa.Integer(), nullable=True),
        sa.Column('max_servicos', sa.Integer(), nullable=True),
        sa.Column('preco_mensal', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('preco_anual', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('modulos_incluidos', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='planos_pkey'),
        sa.UniqueConstraint('nome', name='planos_nome_key'),
    )

    planos_tbl = sa.table(
        'planos',
        sa.column('id', sa.Integer),
        sa.column('nome', sa.String),
        sa.column('max_unidades', sa.Integer),
        sa.column('max_usuarios', sa.Integer),
        sa.column('max_servicos', sa.Integer),
        sa.column('preco_mensal', sa.Numeric),
        sa.column('preco_anual', sa.Numeric),
        sa.column('modulos_incluidos', sa.JSON),
    )
    # Ordem importa: free precisa sair com id=1 — é o default de
    # empresas.plano_id desde a Fase 1-A (era Integer solto, sem FK
    # apontando pra lugar nenhum; a partir desta migração passa a apontar
    # de verdade pra esta linha).
    conn.execute(
        planos_tbl.insert(),
        [
            {
                "nome": "free", "max_unidades": 1, "max_usuarios": 2, "max_servicos": 6,
                "preco_mensal": 0, "preco_anual": 0, "modulos_incluidos": [],
            },
            {
                "nome": "essencial", "max_unidades": 3, "max_usuarios": None, "max_servicos": None,
                "preco_mensal": 49.99, "preco_anual": 569.89, "modulos_incluidos": [],
            },
            {
                "nome": "pro", "max_unidades": 5, "max_usuarios": None, "max_servicos": None,
                "preco_mensal": 79.99, "preco_anual": 883.09,
                "modulos_incluidos": ["relatorios", "clube_recorrencia"],
            },
            {
                "nome": "ilimitado", "max_unidades": None, "max_usuarios": None, "max_servicos": None,
                "preco_mensal": 199.99, "preco_anual": 2159.89,
                "modulos_incluidos": ["relatorios", "clube_recorrencia"],
            },
        ],
    )

    # ════════════════════════════════════════════════════════════════
    # 2. empresas: plano_id vira FK real + periodicidade/preco_congelado
    # ════════════════════════════════════════════════════════════════
    op.create_foreign_key('empresas_plano_id_fkey', 'empresas', 'planos', ['plano_id'], ['id'])
    op.add_column('empresas', sa.Column('periodicidade', sa.String(length=10), nullable=True))
    op.add_column('empresas', sa.Column('preco_congelado', sa.Numeric(precision=10, scale=2), nullable=True))

    # ════════════════════════════════════════════════════════════════
    # 3. appointments: agendamento_original_id (marca remarcação, NULL =
    #    criação real — é o que UsoMensal usa pra decidir se incrementa)
    # ════════════════════════════════════════════════════════════════
    op.add_column('appointments', sa.Column('agendamento_original_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'appointments_agendamento_original_id_fkey',
        'appointments', 'appointments', ['agendamento_original_id'], ['id'],
    )

    # ════════════════════════════════════════════════════════════════
    # 4. uso_mensal
    # ════════════════════════════════════════════════════════════════
    op.create_table(
        'uso_mensal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('ano_mes', sa.String(length=7), nullable=False),
        sa.Column('agendamentos_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name='uso_mensal_empresa_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='uso_mensal_pkey'),
        sa.UniqueConstraint('empresa_id', 'ano_mes', name='uq_uso_mensal_empresa_mes'),
    )
    op.create_index('ix_uso_mensal_empresa_id', 'uso_mensal', ['empresa_id'], unique=False)


def downgrade():
    op.drop_index('ix_uso_mensal_empresa_id', table_name='uso_mensal')
    op.drop_table('uso_mensal')

    op.drop_constraint(
        'appointments_agendamento_original_id_fkey', 'appointments', type_='foreignkey',
    )
    op.drop_column('appointments', 'agendamento_original_id')

    op.drop_column('empresas', 'preco_congelado')
    op.drop_column('empresas', 'periodicidade')
    op.drop_constraint('empresas_plano_id_fkey', 'empresas', type_='foreignkey')

    op.drop_table('planos')
