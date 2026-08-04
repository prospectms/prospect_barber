"""baseline pre-multi-tenant schema

Reflete exatamente o schema que já existe no Neon hoje (introspectado via
information_schema/pg_constraint/pg_indexes em 2026-08-03) — não recria do
zero. Esta revisão NUNCA roda de verdade contra o Neon de dev: ele é
marcado como já aplicado via `flask db stamp` (as tabelas já existem lá).
Ela existe para (a) documentar o ponto de partida e (b) permitir montar um
banco novo (dev local, CI, testes) do zero até este ponto, antes da
migração de multi-tenant rodar por cima.

Revision ID: 6cb81713bdc3
Revises:
Create Date: 2026-08-03 17:59:12.760048

"""
from alembic import op
import sqlalchemy as sa


revision = '6cb81713bdc3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('login_count', sa.Integer(), nullable=False),
        sa.Column('failed_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='users_pkey'),
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'barbers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('whatsapp', sa.String(length=20), nullable=True),
        sa.Column('specialty', sa.String(length=100), nullable=True),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('photo', sa.String(length=200), nullable=True),
        sa.Column('work_start_time', sa.Time(), nullable=True),
        sa.Column('work_end_time', sa.Time(), nullable=True),
        sa.Column('lunch_start', sa.Time(), nullable=True),
        sa.Column('lunch_end', sa.Time(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='barbers_user_id_fkey', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='barbers_pkey'),
        sa.UniqueConstraint('user_id', name='barbers_user_id_key'),
    )
    op.create_index('ix_barbers_name', 'barbers', ['name'], unique=False)

    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('cpf', sa.String(length=14), nullable=True),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_visit', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='customers_pkey'),
    )
    op.create_index('ix_customers_cpf', 'customers', ['cpf'], unique=True)
    op.create_index('ix_customers_name', 'customers', ['name'], unique=False)
    op.create_index('ix_customers_email', 'customers', ['email'], unique=False)
    op.create_index('ix_customers_phone', 'customers', ['phone'], unique=False)

    op.create_table(
        'services',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='services_pkey'),
    )

    op.create_table(
        'service_kit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='service_kit_pkey'),
    )

    op.create_table(
        'service_kit_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kit_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['kit_id'], ['service_kit.id'], name='service_kit_item_kit_id_fkey'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='service_kit_item_service_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='service_kit_item_pkey'),
    )

    op.create_table(
        'appointments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('kit_id', sa.Integer(), nullable=True),
        sa.Column('scheduled_date', sa.Date(), nullable=False),
        sa.Column('scheduled_time', sa.Time(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name='appointments_customer_id_fkey'),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], name='appointments_barber_id_fkey'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='appointments_service_id_fkey'),
        sa.ForeignKeyConstraint(['kit_id'], ['service_kit.id'], name='appointments_kit_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='appointments_pkey'),
    )
    op.create_index('ix_appt_barber_date', 'appointments', ['barber_id', 'scheduled_date'], unique=False)

    op.create_table(
        'barber_schedule_exception',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('barber_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('exception_type', sa.String(length=20), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['barber_id'], ['barbers.id'], name='barber_schedule_exception_barber_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='barber_schedule_exception_pkey'),
        sa.UniqueConstraint('barber_id', 'date', name='uq_barber_exception_date'),
    )

    op.create_table(
        'subscription_plan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='subscription_plan_pkey'),
    )

    op.create_table(
        'subscription_plan_credit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plan.id'], name='subscription_plan_credit_plan_id_fkey'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='subscription_plan_credit_service_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='subscription_plan_credit_pkey'),
    )

    op.create_table(
        'customer_subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('renewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name='customer_subscription_customer_id_fkey'),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plan.id'], name='customer_subscription_plan_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='customer_subscription_pkey'),
    )

    op.create_table(
        'subscription_credit_balance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('total_credits', sa.Integer(), nullable=False),
        sa.Column('used_credits', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['subscription_id'], ['customer_subscription.id'], name='subscription_credit_balance_subscription_id_fkey'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='subscription_credit_balance_service_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='subscription_credit_balance_pkey'),
    )

    op.create_table(
        'subscription_credit_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['subscription_id'], ['customer_subscription.id'], name='subscription_credit_usage_subscription_id_fkey'),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name='subscription_credit_usage_appointment_id_fkey'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], name='subscription_credit_usage_service_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='subscription_credit_usage_pkey'),
    )

    op.create_table(
        'raffles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('prize', sa.String(length=200), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('winner_count', sa.Integer(), nullable=False),
        sa.Column('pool_size', sa.Integer(), nullable=True),
        sa.Column('drawn_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='raffles_pkey'),
    )

    op.create_table(
        'raffle_winners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('raffle_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('customer_name', sa.String(length=100), nullable=False),
        sa.Column('customer_phone', sa.String(length=30), nullable=True),
        sa.Column('drawn_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['raffle_id'], ['raffles.id'], name='raffle_winners_raffle_id_fkey'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name='raffle_winners_customer_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='raffle_winners_pkey'),
    )


def downgrade():
    op.drop_table('raffle_winners')
    op.drop_table('raffles')
    op.drop_table('subscription_credit_usage')
    op.drop_table('subscription_credit_balance')
    op.drop_table('customer_subscription')
    op.drop_table('subscription_plan_credit')
    op.drop_table('subscription_plan')
    op.drop_table('barber_schedule_exception')
    op.drop_index('ix_appt_barber_date', table_name='appointments')
    op.drop_table('appointments')
    op.drop_table('service_kit_item')
    op.drop_table('service_kit')
    op.drop_table('services')
    op.drop_index('ix_customers_phone', table_name='customers')
    op.drop_index('ix_customers_email', table_name='customers')
    op.drop_index('ix_customers_name', table_name='customers')
    op.drop_index('ix_customers_cpf', table_name='customers')
    op.drop_table('customers')
    op.drop_index('ix_barbers_name', table_name='barbers')
    op.drop_table('barbers')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_username', table_name='users')
    op.drop_table('users')
