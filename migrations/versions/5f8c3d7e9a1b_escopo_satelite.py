"""escopo de tenant nos 9 models satelite (Fase 1-B)

Adiciona empresa_id (todos) e unidade_id (service_kit/service_kit_item/
subscription_plan/subscription_plan_credit) aos 9 models que ficaram de
fora da Fase 1-A por decisão explícita. Backfill em duas camadas:

  1. Derivação real via join, quando existe caminho natural:
     - service_kit_item / subscription_plan_credit -> services (via
       service_id, que já é empresa_id/unidade_id)
     - customer_subscription -> customers (via customer_id, empresa_id)
     - subscription_credit_balance / subscription_credit_usage ->
       customer_subscription (via subscription_id, já backfillado no
       passo anterior)
     - raffle_winners -> customers (via customer_id, quando não-nulo)
     - service_kit -> primeiro item do próprio kit (subquery correlata)
     - subscription_plan -> primeiro credit do próprio plano (idem)

  2. Fallback pra Empresa/Unidade "seed" (mesma criada na migração
     45c96fce867f, slugs empresa-padrao-migracao/unidade-padrao-migracao)
     pra qualquer linha que sobre sem derivação possível (ex.: ServiceKit
     sem nenhum item, Raffle sem nenhum vencedor ainda) — mesmo padrão já
     usado e testado na Fase 1-A, não um mecanismo novo.

Confirmado por query direta antes de escrever esta migração: as 9
tabelas estão vazias no banco de produção hoje (nunca puderam receber
dado, bloqueadas desde a Fase 1-A) — o backfill abaixo não move nenhuma
linha real agora, mas a lógica é escrita e testada como se movesse,
inserindo dado fake no dry-run antes de aplicar.

appointment_id em subscription_credit_usage ganha ondelete='SET NULL'
(era NO ACTION) — decisão confirmada separada desta migração de schema.

Revision ID: 5f8c3d7e9a1b
Revises: 9d2e5b8f1a3c
Create Date: 2026-08-06 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '5f8c3d7e9a1b'
down_revision = '9d2e5b8f1a3c'
branch_labels = None
depends_on = None

SEED_EMPRESA_ID = 1
SEED_UNIDADE_ID = 1


def upgrade():
    conn = op.get_bind()

    # ════════════════════════════════════════════════════════════════
    # 1. Colunas novas (nullable por enquanto — backfill vem antes do
    #    NOT NULL)
    # ════════════════════════════════════════════════════════════════
    op.add_column('service_kit', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('service_kit', sa.Column('unidade_id', sa.Integer(), nullable=True))
    op.add_column('service_kit_item', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('service_kit_item', sa.Column('unidade_id', sa.Integer(), nullable=True))
    op.add_column('subscription_plan', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('subscription_plan', sa.Column('unidade_id', sa.Integer(), nullable=True))
    op.add_column('subscription_plan_credit', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('subscription_plan_credit', sa.Column('unidade_id', sa.Integer(), nullable=True))
    op.add_column('customer_subscription', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('subscription_credit_balance', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('subscription_credit_usage', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('raffles', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('raffle_winners', sa.Column('empresa_id', sa.Integer(), nullable=True))

    # ════════════════════════════════════════════════════════════════
    # 2. Backfill via derivação real (join)
    # ════════════════════════════════════════════════════════════════

    # service_kit_item <- services (via service_id)
    conn.execute(sa.text("""
        UPDATE service_kit_item ski
        SET empresa_id = s.empresa_id, unidade_id = s.unidade_id
        FROM services s
        WHERE ski.service_id = s.id
    """))

    # subscription_plan_credit <- services (via service_id)
    conn.execute(sa.text("""
        UPDATE subscription_plan_credit spc
        SET empresa_id = s.empresa_id, unidade_id = s.unidade_id
        FROM services s
        WHERE spc.service_id = s.id
    """))

    # service_kit <- primeiro item do próprio kit (já backfillado acima)
    conn.execute(sa.text("""
        UPDATE service_kit sk
        SET empresa_id = sub.empresa_id, unidade_id = sub.unidade_id
        FROM (
            SELECT DISTINCT ON (kit_id) kit_id, empresa_id, unidade_id
            FROM service_kit_item
            WHERE empresa_id IS NOT NULL
            ORDER BY kit_id, id
        ) sub
        WHERE sk.id = sub.kit_id
    """))

    # subscription_plan <- primeiro credit do próprio plano
    conn.execute(sa.text("""
        UPDATE subscription_plan sp
        SET empresa_id = sub.empresa_id, unidade_id = sub.unidade_id
        FROM (
            SELECT DISTINCT ON (plan_id) plan_id, empresa_id, unidade_id
            FROM subscription_plan_credit
            WHERE empresa_id IS NOT NULL
            ORDER BY plan_id, id
        ) sub
        WHERE sp.id = sub.plan_id
    """))

    # customer_subscription <- customers (via customer_id)
    conn.execute(sa.text("""
        UPDATE customer_subscription cs
        SET empresa_id = c.empresa_id
        FROM customers c
        WHERE cs.customer_id = c.id
    """))

    # subscription_credit_balance <- customer_subscription (já backfillado)
    conn.execute(sa.text("""
        UPDATE subscription_credit_balance scb
        SET empresa_id = cs.empresa_id
        FROM customer_subscription cs
        WHERE scb.subscription_id = cs.id
    """))

    # subscription_credit_usage <- customer_subscription (já backfillado)
    conn.execute(sa.text("""
        UPDATE subscription_credit_usage scu
        SET empresa_id = cs.empresa_id
        FROM customer_subscription cs
        WHERE scu.subscription_id = cs.id
    """))

    # raffle_winners <- customers (via customer_id, nullable — pode não bater)
    conn.execute(sa.text("""
        UPDATE raffle_winners rw
        SET empresa_id = c.empresa_id
        FROM customers c
        WHERE rw.customer_id = c.id
    """))

    # raffle_winners restantes (customer_id nulo ou cliente já não existe)
    # <- raffles pai, mas raffles ainda não foi backfillado — resolvido no
    # passo de fallback abaixo junto com raffles em si.

    # ════════════════════════════════════════════════════════════════
    # 3. Fallback pra seed — qualquer linha que sobrou sem derivação
    #    (ex.: ServiceKit sem item, SubscriptionPlan sem credit, Raffle
    #    sem winner ainda). Nunca fica NULL antes do NOT NULL.
    # ════════════════════════════════════════════════════════════════
    for tabela, tem_unidade in [
        ('service_kit', True), ('service_kit_item', True),
        ('subscription_plan', True), ('subscription_plan_credit', True),
        ('customer_subscription', False), ('subscription_credit_balance', False),
        ('subscription_credit_usage', False),
    ]:
        set_clause = "empresa_id = :empresa_id"
        if tem_unidade:
            set_clause += ", unidade_id = :unidade_id"
        conn.execute(
            sa.text(f"UPDATE {tabela} SET {set_clause} WHERE empresa_id IS NULL"),
            {"empresa_id": SEED_EMPRESA_ID, "unidade_id": SEED_UNIDADE_ID},
        )

    # raffles não tem derivação própria (é definido antes de ter
    # vencedores) — sempre seed se ainda não tiver empresa_id.
    conn.execute(sa.text(
        "UPDATE raffles SET empresa_id = :empresa_id WHERE empresa_id IS NULL"
    ), {"empresa_id": SEED_EMPRESA_ID})

    # raffle_winners: agora que raffles está com empresa_id garantido,
    # fecha qualquer winner que não bateu via customer_id.
    conn.execute(sa.text("""
        UPDATE raffle_winners rw
        SET empresa_id = r.empresa_id
        FROM raffles r
        WHERE rw.raffle_id = r.id AND rw.empresa_id IS NULL
    """))

    # ════════════════════════════════════════════════════════════════
    # 4. NOT NULL + índices + FKs
    # ════════════════════════════════════════════════════════════════
    for tabela in [
        'service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit',
        'customer_subscription', 'subscription_credit_balance', 'subscription_credit_usage',
        'raffles', 'raffle_winners',
    ]:
        op.alter_column(tabela, 'empresa_id', nullable=False)
        op.create_index(f'ix_{tabela}_empresa_id', tabela, ['empresa_id'])
        op.create_foreign_key(f'{tabela}_empresa_id_fkey', tabela, 'empresas', ['empresa_id'], ['id'])

    for tabela in ['service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit']:
        op.alter_column(tabela, 'unidade_id', nullable=False)
        op.create_index(f'ix_{tabela}_unidade_id', tabela, ['unidade_id'])
        op.create_foreign_key(f'{tabela}_unidade_id_fkey', tabela, 'unidades', ['unidade_id'], ['id'])

    # ════════════════════════════════════════════════════════════════
    # 5. subscription_credit_usage.appointment_id: NO ACTION -> SET NULL
    # ════════════════════════════════════════════════════════════════
    op.drop_constraint(
        'subscription_credit_usage_appointment_id_fkey',
        'subscription_credit_usage', type_='foreignkey',
    )
    op.create_foreign_key(
        'subscription_credit_usage_appointment_id_fkey',
        'subscription_credit_usage', 'appointments', ['appointment_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint(
        'subscription_credit_usage_appointment_id_fkey',
        'subscription_credit_usage', type_='foreignkey',
    )
    op.create_foreign_key(
        'subscription_credit_usage_appointment_id_fkey',
        'subscription_credit_usage', 'appointments', ['appointment_id'], ['id'],
    )

    for tabela in ['service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit']:
        op.drop_constraint(f'{tabela}_unidade_id_fkey', tabela, type_='foreignkey')
        op.drop_index(f'ix_{tabela}_unidade_id', table_name=tabela)
        op.drop_column(tabela, 'unidade_id')

    for tabela in [
        'service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit',
        'customer_subscription', 'subscription_credit_balance', 'subscription_credit_usage',
        'raffles', 'raffle_winners',
    ]:
        op.drop_constraint(f'{tabela}_empresa_id_fkey', tabela, type_='foreignkey')
        op.drop_index(f'ix_{tabela}_empresa_id', table_name=tabela)
        op.drop_column(tabela, 'empresa_id')
