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

    op.drop_index('ix_users_username', table_name='users')
    op.drop_index('ix_users_email', table_name='users')  # era unique global

    # batch_alter_table: SQLite não suporta ALTER COLUMN / ADD-DROP
    # CONSTRAINT / DROP COLUMN nativamente (só Postgres roda isso como
    # ALTER TABLE direto) -- em SQLite o Alembic recria a tabela inteira
    # por baixo dos panos com o schema final. Transparente no Postgres
    # (roda como ALTER TABLE normal, sem recriar nada).
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('nome', nullable=False)
        batch_op.alter_column('papel', nullable=False)
        batch_op.alter_column('empresa_id', nullable=False)
        batch_op.alter_column('senha_hash', nullable=False)
        batch_op.alter_column('ativo', nullable=False)
        batch_op.drop_column('username')
        batch_op.drop_column('role')
        batch_op.drop_column('is_active')
        batch_op.drop_column('created_at')
        batch_op.drop_column('password_hash')
        batch_op.create_foreign_key('users_empresa_id_fkey', 'empresas', ['empresa_id'], ['id'])
        batch_op.create_unique_constraint('uq_usuario_empresa_email', ['empresa_id', 'email'])

    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_index('ix_users_empresa_id', 'users', ['empresa_id'], unique=False)

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

    with op.batch_alter_table('barbers') as batch_op:
        batch_op.alter_column('empresa_id', nullable=False)
        batch_op.alter_column('unidade_id', nullable=False)
        batch_op.drop_constraint('barbers_user_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('barbers_user_id_key', type_='unique')
        batch_op.drop_column('user_id')
        batch_op.create_unique_constraint('barbers_usuario_id_key', ['usuario_id'])
        batch_op.create_foreign_key(
            'barbers_usuario_id_fkey', 'users', ['usuario_id'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key('barbers_empresa_id_fkey', 'empresas', ['empresa_id'], ['id'])
        batch_op.create_foreign_key('barbers_unidade_id_fkey', 'unidades', ['unidade_id'], ['id'])

    op.create_index('ix_barbers_empresa_id', 'barbers', ['empresa_id'], unique=False)
    op.create_index('ix_barbers_unidade_id', 'barbers', ['unidade_id'], unique=False)

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

    op.drop_index('ix_customers_cpf', table_name='customers')  # era unique global

    with op.batch_alter_table('customers') as batch_op:
        batch_op.alter_column('empresa_id', nullable=False)
        batch_op.create_foreign_key('customers_empresa_id_fkey', 'empresas', ['empresa_id'], ['id'])
        batch_op.create_foreign_key(
            'customers_unidade_origem_id_fkey', 'unidades', ['unidade_origem_id'], ['id'],
        )
        batch_op.create_unique_constraint('uq_cliente_empresa_cpf', ['empresa_id', 'cpf'])

    op.create_index('ix_customers_cpf', 'customers', ['cpf'], unique=False)
    op.create_index('ix_customers_empresa_id', 'customers', ['empresa_id'], unique=False)

    # ════════════════════════════════════════════════════════════════
    # 6. services -> Servico (empresa_id, unidade_id)
    # ════════════════════════════════════════════════════════════════
    op.add_column('services', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('services', sa.Column('unidade_id', sa.Integer(), nullable=True))

    services_tbl = sa.table(
        'services', sa.column('empresa_id', sa.Integer), sa.column('unidade_id', sa.Integer),
    )
    conn.execute(services_tbl.update().values(empresa_id=seed_empresa_id, unidade_id=seed_unidade_id))

    with op.batch_alter_table('services') as batch_op:
        batch_op.alter_column('empresa_id', nullable=False)
        batch_op.alter_column('unidade_id', nullable=False)
        batch_op.create_foreign_key('services_empresa_id_fkey', 'empresas', ['empresa_id'], ['id'])
        batch_op.create_foreign_key('services_unidade_id_fkey', 'unidades', ['unidade_id'], ['id'])

    op.create_index('ix_services_empresa_id', 'services', ['empresa_id'], unique=False)
    op.create_index('ix_services_unidade_id', 'services', ['unidade_id'], unique=False)

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

    with op.batch_alter_table('appointments') as batch_op:
        batch_op.alter_column('empresa_id', nullable=False)
        batch_op.alter_column('unidade_id', nullable=False)
        batch_op.create_foreign_key('appointments_empresa_id_fkey', 'empresas', ['empresa_id'], ['id'])
        batch_op.create_foreign_key('appointments_unidade_id_fkey', 'unidades', ['unidade_id'], ['id'])

    op.create_index('ix_appointments_empresa_id', 'appointments', ['empresa_id'], unique=False)
    op.create_index('ix_appointments_unidade_id', 'appointments', ['unidade_id'], unique=False)

    # ════════════════════════════════════════════════════════════════
    # 8. barber_schedule_exception (empresa_id, unidade_id)
    # ════════════════════════════════════════════════════════════════
    op.add_column('barber_schedule_exception', sa.Column('empresa_id', sa.Integer(), nullable=True))
    op.add_column('barber_schedule_exception', sa.Column('unidade_id', sa.Integer(), nullable=True))

    bse_tbl = sa.table(
        'barber_schedule_exception', sa.column('empresa_id', sa.Integer), sa.column('unidade_id', sa.Integer),
    )
    conn.execute(bse_tbl.update().values(empresa_id=seed_empresa_id, unidade_id=seed_unidade_id))

    with op.batch_alter_table('barber_schedule_exception') as batch_op:
        batch_op.alter_column('empresa_id', nullable=False)
        batch_op.alter_column('unidade_id', nullable=False)
        batch_op.create_foreign_key(
            'barber_schedule_exception_empresa_id_fkey', 'empresas', ['empresa_id'], ['id'],
        )
        batch_op.create_foreign_key(
            'barber_schedule_exception_unidade_id_fkey', 'unidades', ['unidade_id'], ['id'],
        )

    op.create_index(
        'ix_barber_schedule_exception_empresa_id', 'barber_schedule_exception', ['empresa_id'], unique=False,
    )
    op.create_index(
        'ix_barber_schedule_exception_unidade_id', 'barber_schedule_exception', ['unidade_id'], unique=False,
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
    # drop_index precisa acontecer DENTRO do mesmo batch, antes do
    # drop_column correspondente -- se rodar depois, o Alembic já tentou
    # recriar o índice ao reconstruir a tabela (modo batch do SQLite) e
    # quebra com "no such column" porque a coluna já não existe mais nesse
    # ponto. Transparente no Postgres de qualquer forma (ordem não importa
    # lá, é tudo ALTER TABLE direto).
    with op.batch_alter_table('barber_schedule_exception') as batch_op:
        batch_op.drop_constraint('barber_schedule_exception_unidade_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('barber_schedule_exception_empresa_id_fkey', type_='foreignkey')
        batch_op.drop_index('ix_barber_schedule_exception_unidade_id')
        batch_op.drop_index('ix_barber_schedule_exception_empresa_id')
        batch_op.drop_column('unidade_id')
        batch_op.drop_column('empresa_id')

    # ── appointments ────────────────────────────────────────────────────
    with op.batch_alter_table('appointments') as batch_op:
        batch_op.drop_constraint('appointments_unidade_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('appointments_empresa_id_fkey', type_='foreignkey')
        batch_op.drop_index('ix_appointments_unidade_id')
        batch_op.drop_index('ix_appointments_empresa_id')
        batch_op.drop_column('unidade_id')
        batch_op.drop_column('empresa_id')

    # ── services ────────────────────────────────────────────────────────
    with op.batch_alter_table('services') as batch_op:
        batch_op.drop_constraint('services_unidade_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('services_empresa_id_fkey', type_='foreignkey')
        batch_op.drop_index('ix_services_unidade_id')
        batch_op.drop_index('ix_services_empresa_id')
        batch_op.drop_column('unidade_id')
        batch_op.drop_column('empresa_id')

    # ── customers ───────────────────────────────────────────────────────
    with op.batch_alter_table('customers') as batch_op:
        batch_op.drop_constraint('uq_cliente_empresa_cpf', type_='unique')
        batch_op.drop_constraint('customers_unidade_origem_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('customers_empresa_id_fkey', type_='foreignkey')
        batch_op.drop_index('ix_customers_empresa_id')
        batch_op.drop_column('unidade_origem_id')
        batch_op.drop_column('empresa_id')
    op.drop_index('ix_customers_cpf', table_name='customers')
    op.create_index('ix_customers_cpf', 'customers', ['cpf'], unique=True)

    # ── barbers ─────────────────────────────────────────────────────────
    with op.batch_alter_table('barbers') as batch_op:
        batch_op.drop_constraint('barbers_unidade_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('barbers_empresa_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('barbers_usuario_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('barbers_usuario_id_key', type_='unique')
    op.drop_index('ix_barbers_unidade_id', table_name='barbers')
    op.drop_index('ix_barbers_empresa_id', table_name='barbers')

    op.add_column('barbers', sa.Column('user_id', sa.Integer(), nullable=True))
    barbers_tbl = sa.table('barbers', sa.column('user_id', sa.Integer), sa.column('usuario_id', sa.Integer))
    conn.execute(barbers_tbl.update().values(user_id=barbers_tbl.c.usuario_id))
    # Profissional sem usuario_id (relaxado nesta fase) não tem para onde
    # voltar num schema que exige user_id NOT NULL — downgrade só é seguro
    # se não houver nenhuma linha nessa situação.
    with op.batch_alter_table('barbers') as batch_op:
        batch_op.alter_column('user_id', nullable=False)
        batch_op.create_unique_constraint('barbers_user_id_key', ['user_id'])
        batch_op.create_foreign_key(
            'barbers_user_id_fkey', 'users', ['user_id'], ['id'], ondelete='CASCADE',
        )
        batch_op.drop_column('unidade_id')
        batch_op.drop_column('empresa_id')
        batch_op.drop_column('usuario_id')

    # ── users ───────────────────────────────────────────────────────────
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('uq_usuario_empresa_email', type_='unique')
        batch_op.drop_constraint('users_empresa_id_fkey', type_='foreignkey')
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

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('username', nullable=False)
        batch_op.alter_column('role', nullable=False)
        batch_op.alter_column('is_active', nullable=False)
        batch_op.alter_column('password_hash', nullable=False)
        batch_op.drop_column('criado_em')
        batch_op.drop_column('ativo')
        batch_op.drop_column('senha_hash')
        batch_op.drop_column('empresa_id')
        batch_op.drop_column('is_superadmin')
        batch_op.drop_column('papel')
        batch_op.drop_column('nome')

    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # ── tabelas novas ───────────────────────────────────────────────────
    op.drop_table('audit_log')
    op.drop_table('usuario_unidade')
    op.drop_table('unidades')
    op.drop_table('empresas')
