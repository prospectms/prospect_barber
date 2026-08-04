"""multi-tenant: empresas, unidades e escopo

Fase 1-A. Cria a hierarquia Empresa/Unidade, adiciona empresa_id/unidade_id
em todo model de tenant existente, e migra os dois pontos de unicidade que
eram globais (users.email, customers.cpf) para compostos por empresa.

Estratégia em cada tabela existente: adicionar coluna NULLABLE, popular
(backfill) com a Empresa+Unidade "seed" criada aqui mesmo, só então marcar
NOT NULL. Isso funciona tanto para o banco vazio de hoje quanto para uma
base populada — o seed existe justamente para não deixar nenhuma linha
pré-multi-tenant órfã quando a coluna passa a ser obrigatória.

barbers.user_id (usuario_id a partir daqui) muda de ondelete='CASCADE'
para ondelete='SET NULL': antes, apagar um User apagava o Barber junto;
agora usuario_id é opcional, então apagar um Usuario deve só desvincular o
Profissional, nunca apagar o registro nem o histórico de Agendamento preso
a ele.

Revision ID: 45c96fce867f
Revises: 6cb81713bdc3
Create Date: 2026-08-03 18:12:44.988728

"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = '45c96fce867f'
down_revision = '6cb81713bdc3'
branch_labels = None
depends_on = None

SEED_EMPRESA_SLUG = 'empresa-padrao-migracao'
SEED_UNIDADE_SLUG = 'unidade-padrao-migracao'


def upgrade():
    conn = op.get_bind()

    # ════════════════════════════════════════════════════════════════
    # 1. Tabelas novas
    # ════════════════════════════════════════════════════════════════
    op.create_table(
        'empresas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=150), nullable=False),
        sa.Column('documento', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('telefone', sa.String(length=20), nullable=True),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('plano_id', sa.Integer(), nullable=False),
        sa.Column('status_assinatura', sa.String(length=20), nullable=False),
        sa.Column('logo_url', sa.String(length=255), nullable=True),
        sa.Column('cor_primaria', sa.String(length=7), nullable=True),
        sa.Column('criada_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='empresas_pkey'),
    )
    op.create_index('ix_empresas_slug', 'empresas', ['slug'], unique=True)

    op.create_table(
        'unidades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(length=150), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('endereco', sa.String(length=255), nullable=True),
        sa.Column('telefone', sa.String(length=20), nullable=True),
        sa.Column('ativa', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name='unidades_empresa_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='unidades_pkey'),
    )
    op.create_index('ix_unidades_empresa_id', 'unidades', ['empresa_id'], unique=False)
    op.create_index('ix_unidades_slug', 'unidades', ['slug'], unique=True)

    op.create_table(
        'usuario_unidade',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('unidade_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name='usuario_unidade_empresa_id_fkey'),
        sa.ForeignKeyConstraint(['usuario_id'], ['users.id'], name='usuario_unidade_usuario_id_fkey'),
        sa.ForeignKeyConstraint(['unidade_id'], ['unidades.id'], name='usuario_unidade_unidade_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='usuario_unidade_pkey'),
        sa.UniqueConstraint('usuario_id', 'unidade_id', name='uq_usuario_unidade'),
    )
    op.create_index('ix_usuario_unidade_empresa_id', 'usuario_unidade', ['empresa_id'], unique=False)
    op.create_index('ix_usuario_unidade_usuario_id', 'usuario_unidade', ['usuario_id'], unique=False)
    op.create_index('ix_usuario_unidade_unidade_id', 'usuario_unidade', ['unidade_id'], unique=False)

    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('acao', sa.String(length=120), nullable=False),
        sa.Column('detalhe', sa.String(length=255), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['users.id'], name='audit_log_usuario_id_fkey'),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name='audit_log_empresa_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='audit_log_pkey'),
    )
    op.create_index('ix_audit_log_usuario_id', 'audit_log', ['usuario_id'], unique=False)
    op.create_index('ix_audit_log_empresa_id', 'audit_log', ['empresa_id'], unique=False)
    op.create_index('ix_audit_log_criado_em', 'audit_log', ['criado_em'], unique=False)

    # ════════════════════════════════════════════════════════════════
    # 2. Seed de Empresa + Unidade padrão — acomoda qualquer linha
    #    pré-multi-tenant (mesmo com o banco vazio hoje, este caminho
    #    precisa existir e rodar de verdade, não só ficar pronto no papel)
    # ════════════════════════════════════════════════════════════════
    empresas_tbl = sa.table(
        'empresas',
        sa.column('id', sa.Integer),
        sa.column('nome', sa.String),
        sa.column('slug', sa.String),
        sa.column('plano_id', sa.Integer),
        sa.column('status_assinatura', sa.String),
        sa.column('criada_em', sa.DateTime),
    )
    unidades_tbl = sa.table(
        'unidades',
        sa.column('id', sa.Integer),
        sa.column('empresa_id', sa.Integer),
        sa.column('nome', sa.String),
        sa.column('slug', sa.String),
        sa.column('ativa', sa.Boolean),
    )

    seed_empresa_id = conn.execute(
        empresas_tbl.insert().values(
            nome='Empresa Padrão (migração)',
            slug=SEED_EMPRESA_SLUG,
            plano_id=1,
            status_assinatura='ativa',
            criada_em=datetime.now(timezone.utc),
        ).returning(empresas_tbl.c.id)
    ).scalar()

    seed_unidade_id = conn.execute(
        unidades_tbl.insert().values(
            empresa_id=seed_empresa_id,
            nome='Unidade Padrão',
            slug=SEED_UNIDADE_SLUG,
            ativa=True,
        ).returning(unidades_tbl.c.id)
    ).scalar()

    # ════════════════════════════════════════════════════════════════
    # 3. users -> Usuario (nome/senha_hash/papel/is_superadmin/ativo/
    #    criado_em/empresa_id; username sai, email vira único por empresa)
    # ════════════════════════════════════════════════════════════════
    op.add_column('users', sa.Column('nome', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('papel', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('senha_hash', sa.String(length=256), nullable=True))
    op.add_column('users', sa.Column('ativo', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('criado_em', sa.DateTime(), nullable=True))

    users_tbl = sa.table(
        'users',
        sa.column('username', sa.String),
        sa.column('role', sa.String),
        sa.column('is_active', sa.Boolean),
        sa.column('created_at', sa.DateTime),
        sa.column('password_hash', sa.String),
        sa.column('nome', sa.String),
        sa.column('papel', sa.String),
        sa.column('empresa_id', sa.Integer),
        sa.column('senha_hash', sa.String),
        sa.column('ativo', sa.Boolean),
        sa.column('criado_em', sa.DateTime),
    )
    conn.execute(
        users_tbl.update().values(
            nome=users_tbl.c.username,
            papel=sa.case((users_tbl.c.role == 'admin', 'dono'), else_='funcionario'),
            empresa_id=seed_empresa_id,
            senha_hash=users_tbl.c.password_hash,
            ativo=users_tbl.c.is_active,
            criado_em=users_tbl.c.created_at,
        )
    )

    op.alter_column('users', 'nome', nullable=False)
    op.alter_column('users', 'papel', nullable=False)
    op.alter_column('users', 'empresa_id', nullable=False)
    op.alter_column('users', 'senha_hash', nullable=False)
    op.alter_column('users', 'ativo', nullable=False)

    op.drop_index('ix_users_username', table_name='users')
    op.drop_index('ix_users_email', table_name='users')  # era unique global
    op.drop_column('users', 'username')
    op.drop_column('users', 'role')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'password_hash')

    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_index('ix_users_empresa_id', 'users', ['empresa_id'], unique=False)
    op.create_foreign_key('users_empresa_id_fkey', 'users', 'empresas', ['empresa_id'], ['id'])
    op.create_unique_constraint('uq_usuario_empresa_email', 'users', ['empresa_id', 'email'])

    # ════════════════════════════════════════════════════════════════
    # 4. barbers -> Profissional (usuario_id nullable + ondelete=SET NULL,
    #    empresa_id/unidade_id)
    # ════════════════════════════════════════════════════════════════
    op.add_column('barbers', sa.Column('usuario_id', sa.Integer(), nullable=True))
    op.add_column('barbers', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('barbers', sa.Column('unidade_id', sa.Integer(), nullable=True))

    barbers_tbl = sa.table(
        'barbers',
        sa.column('user_id', sa.Integer),
        sa.column('usuario_id', sa.Integer),
        sa.column('empresa_id', sa.Integer),
        sa.column('unidade_id', sa.Integer),
    )
    conn.execute(
        barbers_tbl.update().values(
            usuario_id=barbers_tbl.c.user_id,
            empresa_id=seed_empresa_id,
            unidade_id=seed_unidade_id,
        )
    )

    op.alter_column('barbers', 'empresa_id', nullable=False)
    op.alter_column('barbers', 'unidade_id', nullable=False)

    op.drop_constraint('barbers_user_id_fkey', 'barbers', type_='foreignkey')
    op.drop_constraint('barbers_user_id_key', 'barbers', type_='unique')
    op.drop_column('barbers', 'user_id')

    op.create_unique_constraint('barbers_usuario_id_key', 'barbers', ['usuario_id'])
    op.create_foreign_key(
        'barbers_usuario_id_fkey', 'barbers', 'users', ['usuario_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_barbers_empresa_id', 'barbers', ['empresa_id'], unique=False)
    op.create_index('ix_barbers_unidade_id', 'barbers', ['unidade_id'], unique=False)
    op.create_foreign_key('barbers_empresa_id_fkey', 'barbers', 'empresas', ['empresa_id'], ['id'])
    op.create_foreign_key('barbers_unidade_id_fkey', 'barbers', 'unidades', ['unidade_id'], ['id'])

    # ════════════════════════════════════════════════════════════════
    # 5. customers -> Cliente (empresa_id, unidade_origem_id de referência,
    #    cpf único por empresa em vez de global)
    # ════════════════════════════════════════════════════════════════
    op.add_column('customers', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('customers', sa.Column('unidade_origem_id', sa.Integer(), nullable=True))

    customers_tbl = sa.table(
        'customers',
        sa.column('empresa_id', sa.Integer),
        sa.column('unidade_origem_id', sa.Integer),
    )
    conn.execute(
        customers_tbl.update().values(
            empresa_id=seed_empresa_id,
            unidade_origem_id=seed_unidade_id,
        )
    )

    op.alter_column('customers', 'empresa_id', nullable=False)

    op.drop_index('ix_customers_cpf', table_name='customers')  # era unique global
    op.create_index('ix_customers_cpf', 'customers', ['cpf'], unique=False)
    op.create_index('ix_customers_empresa_id', 'customers', ['empresa_id'], unique=False)
    op.create_foreign_key('customers_empresa_id_fkey', 'customers', 'empresas', ['empresa_id'], ['id'])
    op.create_foreign_key(
        'customers_unidade_origem_id_fkey', 'customers', 'unidades', ['unidade_origem_id'], ['id'],
    )
    op.create_unique_constraint('uq_cliente_empresa_cpf', 'customers', ['empresa_id', 'cpf'])

    # ════════════════════════════════════════════════════════════════
    # 6. services -> Servico (empresa_id, unidade_id)
    # ════════════════════════════════════════════════════════════════
    op.add_column('services', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('services', sa.Column('unidade_id', sa.Integer(), nullable=True))

    services_tbl = sa.table(
        'services', sa.column('empresa_id', sa.Integer), sa.column('unidade_id', sa.Integer),
    )
    conn.execute(services_tbl.update().values(empresa_id=seed_empresa_id, unidade_id=seed_unidade_id))

    op.alter_column('services', 'empresa_id', nullable=False)
    op.alter_column('services', 'unidade_id', nullable=False)
    op.create_index('ix_services_empresa_id', 'services', ['empresa_id'], unique=False)
    op.create_index('ix_services_unidade_id', 'services', ['unidade_id'], unique=False)
    op.create_foreign_key('services_empresa_id_fkey', 'services', 'empresas', ['empresa_id'], ['id'])
    op.create_foreign_key('services_unidade_id_fkey', 'services', 'unidades', ['unidade_id'], ['id'])

    # ════════════════════════════════════════════════════════════════
    # 7. appointments -> Agendamento (empresa_id, unidade_id)
    # ════════════════════════════════════════════════════════════════
    op.add_column('appointments', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('appointments', sa.Column('unidade_id', sa.Integer(), nullable=True))

    appointments_tbl = sa.table(
        'appointments', sa.column('empresa_id', sa.Integer), sa.column('unidade_id', sa.Integer),
    )
    conn.execute(
        appointments_tbl.update().values(empresa_id=seed_empresa_id, unidade_id=seed_unidade_id)
    )

    op.alter_column('appointments', 'empresa_id', nullable=False)
    op.alter_column('appointments', 'unidade_id', nullable=False)
    op.create_index('ix_appointments_empresa_id', 'appointments', ['empresa_id'], unique=False)
    op.create_index('ix_appointments_unidade_id', 'appointments', ['unidade_id'], unique=False)
    op.create_foreign_key('appointments_empresa_id_fkey', 'appointments', 'empresas', ['empresa_id'], ['id'])
    op.create_foreign_key('appointments_unidade_id_fkey', 'appointments', 'unidades', ['unidade_id'], ['id'])

    # ════════════════════════════════════════════════════════════════
    # 8. barber_schedule_exception (empresa_id, unidade_id)
    # ════════════════════════════════════════════════════════════════
    op.add_column('barber_schedule_exception', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('barber_schedule_exception', sa.Column('unidade_id', sa.Integer(), nullable=True))

    bse_tbl = sa.table(
        'barber_schedule_exception', sa.column('empresa_id', sa.Integer), sa.column('unidade_id', sa.Integer),
    )
    conn.execute(bse_tbl.update().values(empresa_id=seed_empresa_id, unidade_id=seed_unidade_id))

    op.alter_column('barber_schedule_exception', 'empresa_id', nullable=False)
    op.alter_column('barber_schedule_exception', 'unidade_id', nullable=False)
    op.create_index(
        'ix_barber_schedule_exception_empresa_id', 'barber_schedule_exception', ['empresa_id'], unique=False,
    )
    op.create_index(
        'ix_barber_schedule_exception_unidade_id', 'barber_schedule_exception', ['unidade_id'], unique=False,
    )
    op.create_foreign_key(
        'barber_schedule_exception_empresa_id_fkey',
        'barber_schedule_exception', 'empresas', ['empresa_id'], ['id'],
    )
    op.create_foreign_key(
        'barber_schedule_exception_unidade_id_fkey',
        'barber_schedule_exception', 'unidades', ['unidade_id'], ['id'],
    )


def downgrade():
    """
    Reversão estrutural best-effort. Uma ressalva importante: se esta
    migração já rodou com mais de uma empresa cadastrada, o downgrade
    devolve o schema a um mundo single-tenant, mas os dados de empresas
    diferentes (ex: dois clientes com o mesmo CPF em empresas distintas)
    não podem conviver sob a constraint global antiga — o downgrade
    restaura a ESTRUTURA, não resolve esse tipo de conflito de dado.
    """
    conn = op.get_bind()

    # ── barber_schedule_exception ──────────────────────────────────────
    op.drop_constraint('barber_schedule_exception_unidade_id_fkey', 'barber_schedule_exception', type_='foreignkey')
    op.drop_constraint('barber_schedule_exception_empresa_id_fkey', 'barber_schedule_exception', type_='foreignkey')
    op.drop_index('ix_barber_schedule_exception_unidade_id', table_name='barber_schedule_exception')
    op.drop_index('ix_barber_schedule_exception_empresa_id', table_name='barber_schedule_exception')
    op.drop_column('barber_schedule_exception', 'unidade_id')
    op.drop_column('barber_schedule_exception', 'empresa_id')

    # ── appointments ────────────────────────────────────────────────────
    op.drop_constraint('appointments_unidade_id_fkey', 'appointments', type_='foreignkey')
    op.drop_constraint('appointments_empresa_id_fkey', 'appointments', type_='foreignkey')
    op.drop_index('ix_appointments_unidade_id', table_name='appointments')
    op.drop_index('ix_appointments_empresa_id', table_name='appointments')
    op.drop_column('appointments', 'unidade_id')
    op.drop_column('appointments', 'empresa_id')

    # ── services ────────────────────────────────────────────────────────
    op.drop_constraint('services_unidade_id_fkey', 'services', type_='foreignkey')
    op.drop_constraint('services_empresa_id_fkey', 'services', type_='foreignkey')
    op.drop_index('ix_services_unidade_id', table_name='services')
    op.drop_index('ix_services_empresa_id', table_name='services')
    op.drop_column('services', 'unidade_id')
    op.drop_column('services', 'empresa_id')

    # ── customers ───────────────────────────────────────────────────────
    op.drop_constraint('uq_cliente_empresa_cpf', 'customers', type_='unique')
    op.drop_constraint('customers_unidade_origem_id_fkey', 'customers', type_='foreignkey')
    op.drop_constraint('customers_empresa_id_fkey', 'customers', type_='foreignkey')
    op.drop_index('ix_customers_empresa_id', table_name='customers')
    op.drop_index('ix_customers_cpf', table_name='customers')
    op.create_index('ix_customers_cpf', 'customers', ['cpf'], unique=True)
    op.drop_column('customers', 'unidade_origem_id')
    op.drop_column('customers', 'empresa_id')

    # ── barbers ─────────────────────────────────────────────────────────
    op.drop_constraint('barbers_unidade_id_fkey', 'barbers', type_='foreignkey')
    op.drop_constraint('barbers_empresa_id_fkey', 'barbers', type_='foreignkey')
    op.drop_index('ix_barbers_unidade_id', table_name='barbers')
    op.drop_index('ix_barbers_empresa_id', table_name='barbers')
    op.drop_constraint('barbers_usuario_id_fkey', 'barbers', type_='foreignkey')
    op.drop_constraint('barbers_usuario_id_key', 'barbers', type_='unique')

    op.add_column('barbers', sa.Column('user_id', sa.Integer(), nullable=True))
    barbers_tbl = sa.table('barbers', sa.column('user_id', sa.Integer), sa.column('usuario_id', sa.Integer))
    conn.execute(barbers_tbl.update().values(user_id=barbers_tbl.c.usuario_id))
    # Profissional sem usuario_id (relaxado nesta fase) não tem para onde
    # voltar num schema que exige user_id NOT NULL — downgrade só é seguro
    # se não houver nenhuma linha nessa situação.
    op.alter_column('barbers', 'user_id', nullable=False)
    op.create_unique_constraint('barbers_user_id_key', 'barbers', ['user_id'])
    op.create_foreign_key(
        'barbers_user_id_fkey', 'barbers', 'users', ['user_id'], ['id'], ondelete='CASCADE',
    )
    op.drop_column('barbers', 'unidade_id')
    op.drop_column('barbers', 'empresa_id')
    op.drop_column('barbers', 'usuario_id')

    # ── users ───────────────────────────────────────────────────────────
    op.drop_constraint('uq_usuario_empresa_email', 'users', type_='unique')
    op.drop_constraint('users_empresa_id_fkey', 'users', type_='foreignkey')
    op.drop_index('ix_users_empresa_id', table_name='users')
    op.drop_index('ix_users_email', table_name='users')

    op.add_column('users', sa.Column('username', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('role', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('password_hash', sa.String(length=256), nullable=True))

    users_tbl = sa.table(
        'users',
        sa.column('username', sa.String),
        sa.column('role', sa.String),
        sa.column('is_active', sa.Boolean),
        sa.column('created_at', sa.DateTime),
        sa.column('password_hash', sa.String),
        sa.column('nome', sa.String),
        sa.column('papel', sa.String),
        sa.column('senha_hash', sa.String),
        sa.column('ativo', sa.Boolean),
        sa.column('criado_em', sa.DateTime),
    )
    conn.execute(
        users_tbl.update().values(
            username=users_tbl.c.nome,
            role=sa.case((users_tbl.c.papel == 'dono', 'admin'), else_='barber'),
            is_active=users_tbl.c.ativo,
            created_at=users_tbl.c.criado_em,
            password_hash=users_tbl.c.senha_hash,
        )
    )

    op.alter_column('users', 'username', nullable=False)
    op.alter_column('users', 'role', nullable=False)
    op.alter_column('users', 'is_active', nullable=False)
    op.alter_column('users', 'password_hash', nullable=False)

    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.drop_column('users', 'criado_em')
    op.drop_column('users', 'ativo')
    op.drop_column('users', 'senha_hash')
    op.drop_column('users', 'empresa_id')
    op.drop_column('users', 'is_superadmin')
    op.drop_column('users', 'papel')
    op.drop_column('users', 'nome')

    # ── tabelas novas ───────────────────────────────────────────────────
    op.drop_table('audit_log')
    op.drop_table('usuario_unidade')
    op.drop_table('unidades')
    op.drop_table('empresas')
