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
    #
    # Subquery correlata (SET col = (SELECT ... WHERE ...)) em vez de
    # UPDATE...FROM ou SELECT DISTINCT ON (ambos Postgres-only) -- SQLite
    # não suporta nenhum dos dois. ORDER BY + LIMIT 1 substitui DISTINCT ON
    # pra achar "o primeiro item" de forma portável entre os dois bancos.
    # ════════════════════════════════════════════════════════════════

    # service_kit_item <- services (via service_id)
    conn.execute(sa.text("""
        UPDATE service_kit_item
        SET empresa_id = (SELECT s.empresa_id FROM services s WHERE s.id = service_kit_item.service_id),
            unidade_id = (SELECT s.unidade_id FROM services s WHERE s.id = service_kit_item.service_id)
    """))

    # subscription_plan_credit <- services (via service_id)
    conn.execute(sa.text("""
        UPDATE subscription_plan_credit
        SET empresa_id = (SELECT s.empresa_id FROM services s WHERE s.id = subscription_plan_credit.service_id),
            unidade_id = (SELECT s.unidade_id FROM services s WHERE s.id = subscription_plan_credit.service_id)
    """))

    # service_kit <- primeiro item do próprio kit (já backfillado acima)
    conn.execute(sa.text("""
        UPDATE service_kit
        SET empresa_id = (
                SELECT ski.empresa_id FROM service_kit_item ski
                WHERE ski.kit_id = service_kit.id AND ski.empresa_id IS NOT NULL
                ORDER BY ski.id LIMIT 1
            ),
            unidade_id = (
                SELECT ski.unidade_id FROM service_kit_item ski
                WHERE ski.kit_id = service_kit.id AND ski.empresa_id IS NOT NULL
                ORDER BY ski.id LIMIT 1
            )
    """))

    # subscription_plan <- primeiro credit do próprio plano
    conn.execute(sa.text("""
        UPDATE subscription_plan
        SET empresa_id = (
                SELECT spc.empresa_id FROM subscription_plan_credit spc
                WHERE spc.plan_id = subscription_plan.id AND spc.empresa_id IS NOT NULL
                ORDER BY spc.id LIMIT 1
            ),
            unidade_id = (
                SELECT spc.unidade_id FROM subscription_plan_credit spc
                WHERE spc.plan_id = subscription_plan.id AND spc.empresa_id IS NOT NULL
                ORDER BY spc.id LIMIT 1
            )
    """))

    # customer_subscription <- customers (via customer_id)
    conn.execute(sa.text("""
        UPDATE customer_subscription
        SET empresa_id = (SELECT c.empresa_id FROM customers c WHERE c.id = customer_subscription.customer_id)
    """))

    # subscription_credit_balance <- customer_subscription (já backfillado)
    conn.execute(sa.text("""
        UPDATE subscription_credit_balance
        SET empresa_id = (
            SELECT cs.empresa_id FROM customer_subscription cs WHERE cs.id = subscription_credit_balance.subscription_id
        )
    """))

    # subscription_credit_usage <- customer_subscription (já backfillado)
    conn.execute(sa.text("""
        UPDATE subscription_credit_usage
        SET empresa_id = (
            SELECT cs.empresa_id FROM customer_subscription cs WHERE cs.id = subscription_credit_usage.subscription_id
        )
    """))

    # raffle_winners <- customers (via customer_id, nullable — pode não bater)
    conn.execute(sa.text("""
        UPDATE raffle_winners
        SET empresa_id = (SELECT c.empresa_id FROM customers c WHERE c.id = raffle_winners.customer_id)
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
        UPDATE raffle_winners
        SET empresa_id = (SELECT r.empresa_id FROM raffles r WHERE r.id = raffle_winners.raffle_id)
        WHERE raffle_winners.empresa_id IS NULL
    """))

    # ════════════════════════════════════════════════════════════════
    # 4. NOT NULL + índices + FKs
    #
    # batch_alter_table: SQLite não suporta ALTER COLUMN / ADD CONSTRAINT
    # nativamente -- Alembic recria a tabela por baixo dos panos com o
    # schema final. Transparente no Postgres (roda como ALTER TABLE
    # direto, sem recriar nada).
    # ════════════════════════════════════════════════════════════════
    for tabela in [
        'service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit',
        'customer_subscription', 'subscription_credit_balance', 'subscription_credit_usage',
        'raffles', 'raffle_winners',
    ]:
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.alter_column('empresa_id', nullable=False)
            batch_op.create_foreign_key(f'{tabela}_empresa_id_fkey', 'empresas', ['empresa_id'], ['id'])
        op.create_index(f'ix_{tabela}_empresa_id', tabela, ['empresa_id'])

    for tabela in ['service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit']:
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.alter_column('unidade_id', nullable=False)
            batch_op.create_foreign_key(f'{tabela}_unidade_id_fkey', 'unidades', ['unidade_id'], ['id'])
        op.create_index(f'ix_{tabela}_unidade_id', tabela, ['unidade_id'])

    # ════════════════════════════════════════════════════════════════
    # 5. subscription_credit_usage.appointment_id: NO ACTION -> SET NULL
    # ════════════════════════════════════════════════════════════════
    with op.batch_alter_table('subscription_credit_usage') as batch_op:
        batch_op.drop_constraint('subscription_credit_usage_appointment_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'subscription_credit_usage_appointment_id_fkey', 'appointments', ['appointment_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('subscription_credit_usage') as batch_op:
        batch_op.drop_constraint('subscription_credit_usage_appointment_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'subscription_credit_usage_appointment_id_fkey', 'appointments', ['appointment_id'], ['id'],
        )

    # drop_index precisa acontecer DENTRO do batch, antes do drop_column
    # correspondente -- ver comentário equivalente na migração
    # 45c96fce867f (mesmo motivo: modo batch do SQLite tenta recriar o
    # índice ao reconstruir a tabela e quebra se a coluna já sumiu).
    for tabela in ['service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit']:
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.drop_constraint(f'{tabela}_unidade_id_fkey', type_='foreignkey')
            batch_op.drop_index(f'ix_{tabela}_unidade_id')
            batch_op.drop_column('unidade_id')

    for tabela in [
        'service_kit', 'service_kit_item', 'subscription_plan', 'subscription_plan_credit',
        'customer_subscription', 'subscription_credit_balance', 'subscription_credit_usage',
        'raffles', 'raffle_winners',
    ]:
        with op.batch_alter_table(tabela) as batch_op:
            batch_op.drop_constraint(f'{tabela}_empresa_id_fkey', type_='foreignkey')
            batch_op.drop_index(f'ix_{tabela}_empresa_id')
            batch_op.drop_column('empresa_id')
