import os
import click
from app import create_app
from app.extensions import db

app = create_app(os.environ.get("FLASK_CONFIG", "development"))


def _bloquear_em_producao(nome_comando: str) -> None:
    """Trava dura, sem flag de bypass -- os comandos abaixo ou apagam o
    schema inteiro (reset-db) ou criam empresa/usuário de demonstração com
    credenciais fracas e públicas no código-fonte (admin123, barber123).
    Nenhum dos dois tem motivo legítimo pra rodar contra produção.

    Aconteceu de verdade uma vez: alguém rodou `flask seed` contra o
    neondb real em 2026-08-04 (achado e corrigido só em 2026-08-21, ver
    STATUS.md) -- as duas contas de demo ficaram sentadas em produção por
    mais de duas semanas com senha pública no repositório. Checa
    FLASK_CONFIG diretamente (mesma variável que create_app() usa aqui
    embaixo pra decidir development/production) em vez de app.debug --
    é o sinal mais direto de "isto é o deploy real", sem depender de
    nenhuma outra configuração ter sido setada certo.
    """
    if os.environ.get("FLASK_CONFIG", "development") == "production":
        raise click.ClickException(
            f"'{nome_comando}' não roda com FLASK_CONFIG=production -- ele "
            "apaga dado real ou cria conta de demonstração com senha pública "
            "no código-fonte. Rode isso só em desenvolvimento local."
        )


def _get_or_create_demo_empresa_unidade():
    """Empresa/Unidade próprias para dado de demo/dev — deliberadamente
    SEPARADAS da Empresa/Unidade "seed" que a migração cria (slug
    empresa-padrao-migracao, ver migrations/versions/45c96fce867f_*.py).

    Aquela é reservada para acomodar dado órfão de uma migração real (seu
    propósito documentado); não deve acumular usuário/serviço fake de
    desenvolvimento por cima. Os comandos de seed abaixo usam esta empresa
    de demo em vez daquela."""
    from app.models.empresa import Empresa
    from app.models.unidade import Unidade

    empresa = Empresa.query.filter_by(slug="empresa-demo-dev").first()
    if not empresa:
        empresa = Empresa(
            nome="Empresa Demo (dev)", slug="empresa-demo-dev",
            plano_id=1, status_assinatura="ativa",
        )
        db.session.add(empresa)
        db.session.flush()

    unidade = Unidade.query.filter_by(slug="unidade-demo-dev").first()
    if not unidade:
        unidade = Unidade(
            empresa_id=empresa.id, nome="Unidade Demo",
            slug="unidade-demo-dev", ativa=True,
        )
        db.session.add(unidade)
        db.session.flush()

    return empresa, unidade


@app.cli.command("init-db")
def init_db():
    """[Descontinuado] Schema agora é gerenciado por Alembic. Use `flask db upgrade`."""
    print("Este comando foi substituído por Alembic (Fase 1-A).")
    print("Use: flask db upgrade")


@app.cli.command("reset-db")
def reset_db():
    """APAGA e recria todo o schema via Alembic (use apenas em desenvolvimento).

    Fica dentro do próprio Alembic (downgrade até base + upgrade até head) em
    vez de db.drop_all()/db.create_all() cru — isso mantém alembic_version
    consistente. Um drop_all()/create_all() direto derruba as tabelas mas
    deixa alembic_version apontando pra uma revisão que não bate mais com o
    schema real, quebrando o próximo `flask db upgrade`.
    """
    _bloquear_em_producao("reset-db")
    from flask_migrate import downgrade, upgrade
    with app.app_context():
        downgrade(revision="base")
        upgrade()
        print("Banco de dados resetado via Alembic (base -> head).")


@app.cli.command("seed")
def seed():
    """Popula a empresa/unidade de demo com dados de exemplo: dono, funcionário
    (também profissional) e serviços. Idempotente."""
    _bloquear_em_producao("seed")
    with app.app_context():
        from app.models.usuario import Usuario
        from app.models.usuario_unidade import UsuarioUnidade
        from app.models.profissional import Profissional
        from app.models.servico import Servico

        empresa, unidade = _get_or_create_demo_empresa_unidade()

        if Usuario.query.filter_by(empresa_id=empresa.id, email="admin@prospectbarber.dev").first():
            print("Seed já aplicado.")
            return

        dono = Usuario(
            empresa_id=empresa.id, nome="Admin", email="admin@prospectbarber.dev",
            papel="dono",
        )
        dono.set_password("admin123")
        db.session.add(dono)

        func_user = Usuario(
            empresa_id=empresa.id, nome="João Silva", email="joao@prospectbarber.dev",
            papel="funcionario",
        )
        func_user.set_password("barber123")
        db.session.add(func_user)
        db.session.flush()  # obtém func_user.id

        db.session.add(UsuarioUnidade(
            empresa_id=empresa.id, usuario_id=func_user.id, unidade_id=unidade.id,
        ))

        profissional = Profissional(
            empresa_id=empresa.id, unidade_id=unidade.id, usuario_id=func_user.id,
            name="João Silva", phone="(11) 99999-0001", specialty="Degradê e Navalhado",
        )
        db.session.add(profissional)

        services = [
            Servico(empresa_id=empresa.id, unidade_id=unidade.id,
                    name="Corte Tradicional", price=35.00, duration_minutes=30,
                    description="Corte clássico com tesoura e máquina."),
            Servico(empresa_id=empresa.id, unidade_id=unidade.id,
                    name="Degradê", price=45.00, duration_minutes=45,
                    description="Corte moderno com degradê nas laterais."),
            Servico(empresa_id=empresa.id, unidade_id=unidade.id,
                    name="Barba Completa", price=30.00, duration_minutes=30,
                    description="Barba feita com navalha e acabamento perfeito."),
            Servico(empresa_id=empresa.id, unidade_id=unidade.id,
                    name="Corte + Barba", price=65.00, duration_minutes=60,
                    description="Combo completo com desconto."),
        ]
        for s in services:
            db.session.add(s)

        db.session.commit()
        print("Seed aplicado com sucesso!")
        print(f"  Empresa: {empresa.nome} ({empresa.slug})")
        print(f"  Unidade: {unidade.nome} ({unidade.slug}) — agenda pública em /agendar/{unidade.slug}")
        print("  Dono:        admin@prospectbarber.dev / admin123")
        print("  Funcionário: joao@prospectbarber.dev  / barber123")


@app.cli.command("seed-admin")
def seed_admin():
    """Cria o usuário dono de desenvolvimento na empresa/unidade de demo (idempotente)."""
    _bloquear_em_producao("seed-admin")
    with app.app_context():
        from app.models.usuario import Usuario

        empresa, _ = _get_or_create_demo_empresa_unidade()

        if Usuario.query.filter_by(empresa_id=empresa.id, email="admin@prospectbarber.dev").first():
            print("Usuário 'admin' já existe.")
            return

        dono = Usuario(
            empresa_id=empresa.id, nome="Admin", email="admin@prospectbarber.dev",
            papel="dono",
        )
        dono.set_password("admin123")
        db.session.add(dono)
        db.session.commit()
        print("Dono criado: admin@prospectbarber.dev / admin123")


@app.cli.command("seed-kits")
def seed_kits():
    """[Fase 1-B] ServiceKit ainda não tem empresa_id/unidade_id.

    Bloqueado enquanto app.utils.feature_flags.SATELLITE_FEATURES_ENABLED for
    False — rodar este seed hoje criaria linhas sem escopo de tenant,
    visíveis pra qualquer empresa (o mesmo problema que o decorator
    bloqueado_enquanto_satelite_desativado evita nas rotas).
    """
    _bloquear_em_producao("seed-kits")
    from app.utils.feature_flags import SATELLITE_FEATURES_ENABLED
    if not SATELLITE_FEATURES_ENABLED:
        print("ServiceKit é um model satélite sem escopo de tenant ainda (Fase 1-B). Seed desativado.")
        return

    with app.app_context():
        from app.models.service_kit import ServiceKit, ServiceKitItem
        from app.models.servico import Servico

        if ServiceKit.query.count() > 0:
            print("Kits já existem. Nenhum kit inserido.")
            return

        print("Nenhum kit de exemplo definido. Edite 'seed-kits' em run.py para adicionar os kits do cliente.")


@app.cli.command("seed-subscription-plans")
def seed_subscription_plans():
    """[Fase 1-B] SubscriptionPlan ainda não tem empresa_id.

    Bloqueado enquanto SATELLITE_FEATURES_ENABLED for False — mesma razão de
    seed-kits.
    """
    _bloquear_em_producao("seed-subscription-plans")
    from app.utils.feature_flags import SATELLITE_FEATURES_ENABLED
    if not SATELLITE_FEATURES_ENABLED:
        print("SubscriptionPlan é um model satélite sem escopo de tenant ainda (Fase 1-B). Seed desativado.")
        return

    with app.app_context():
        from app.models.subscription_plan import SubscriptionPlan

        if SubscriptionPlan.query.count() > 0:
            print("Planos de assinatura já existem. Nenhum plano inserido.")
            return

        print("Nenhum plano de exemplo definido. Edite 'seed-subscription-plans' em run.py para adicionar os planos do cliente.")


@app.cli.command("seed-services")
def seed_services():
    """
    Popula serviços de exemplo na empresa/unidade de demo. Não insere se essa
    unidade já tiver serviços. Edite este seed com os serviços reais do
    cliente antes de usar em produção.
    """
    _bloquear_em_producao("seed-services")
    with app.app_context():
        from app.models.servico import Servico

        empresa, unidade = _get_or_create_demo_empresa_unidade()

        if Servico.query.filter_by(unidade_id=unidade.id).count() > 0:
            print("Unidade seed já possui serviços. Nenhum serviço inserido.")
            return

        print("Nenhum serviço de exemplo definido. Edite 'seed-services' em run.py para adicionar os serviços do cliente.")


@app.cli.command("seed-prospect")
def seed_prospect():
    """Cria a empresa interna da equipe Prospect + o usuário superadmin (idempotente).

    Diferente de `seed`/`seed-admin` (que populam a empresa/unidade de
    demo), este comando cria uma empresa própria só pra equipe Prospect —
    o superadmin não deveria morar dentro da empresa placeholder de
    migração. is_superadmin=True dá acesso a /superadmin (todas as
    empresas + auditoria) independente do papel dentro da própria empresa.
    """
    with app.app_context():
        from app.models.empresa import Empresa
        from app.models.unidade import Unidade
        from app.models.usuario import Usuario

        email = "administrativo@theprospect.com.br"
        existing = Usuario.query.filter_by(email=email).first()
        if existing:
            print(f"Usuário com e-mail '{email}' já existe (empresa_id={existing.empresa_id}).")
            return

        empresa = Empresa.query.filter_by(slug="prospect-interno").first()
        if not empresa:
            empresa = Empresa(
                nome="Prospect Barber (equipe interna)", slug="prospect-interno",
                email=email, plano_id=1, status_assinatura="ativa",
            )
            db.session.add(empresa)
            db.session.flush()

        unidade = Unidade.query.filter_by(slug="prospect-interno-sede").first()
        if not unidade:
            unidade = Unidade(
                empresa_id=empresa.id, nome="Sede", slug="prospect-interno-sede", ativa=True,
            )
            db.session.add(unidade)
            db.session.flush()

        user = Usuario(
            empresa_id=empresa.id, nome="Administrativo Prospect", email=email,
            papel="dono", is_superadmin=True,
        )
        user.set_password("Prospect@2025!")
        db.session.add(user)
        db.session.commit()
        print(f"Superadmin criado: {email} / Prospect@2025!")
        print("Altere a senha após o primeiro login! Acesso a todas as empresas em /superadmin")


if __name__ == "__main__":
    app.run(debug=app.debug, host="0.0.0.0", port=5000)
