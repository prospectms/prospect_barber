import os
from app import create_app
from app.extensions import db

app = create_app(os.environ.get("FLASK_CONFIG", "development"))


@app.cli.command("init-db")
def init_db():
    """Cria todas as tabelas no banco de dados."""
    with app.app_context():
        db.create_all()
        print("Banco de dados inicializado.")


@app.cli.command("reset-db")
def reset_db():
    """APAGA e recria todas as tabelas (use apenas em desenvolvimento)."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("Banco de dados resetado.")


@app.cli.command("seed")
def seed():
    """Popula o banco com dados iniciais (admin + exemplos)."""
    with app.app_context():
        from app.models.user import User
        from app.models.barber import Barber
        from app.models.service import Service

        if User.query.filter_by(username="admin").first():
            print("Seed já aplicado.")
            return

        admin = User(username="admin", email="admin@prospectbarber.local", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        barber_user = User(username="joao", email="joao@prospectbarber.local", role="barber")
        barber_user.set_password("barber123")
        db.session.add(barber_user)
        db.session.flush()

        barber = Barber(user_id=barber_user.id, name="João Silva",
                        phone="(11) 99999-0001", specialty="Degradê e Navalhado")
        db.session.add(barber)

        services = [
            Service(name="Corte Tradicional", price=35.00, duration_minutes=30,
                    description="Corte clássico com tesoura e máquina."),
            Service(name="Degradê", price=45.00, duration_minutes=45,
                    description="Corte moderno com degradê nas laterais."),
            Service(name="Barba Completa", price=30.00, duration_minutes=30,
                    description="Barba feita com navalha e acabamento perfeito."),
            Service(name="Corte + Barba", price=65.00, duration_minutes=60,
                    description="Combo completo com desconto."),
        ]
        for s in services:
            db.session.add(s)

        db.session.commit()
        print("Seed aplicado com sucesso!")
        print("  Admin:  admin / admin123")
        print("  Barber: joao  / barber123")


@app.cli.command("seed-admin")
def seed_admin():
    """Cria o usuário admin de desenvolvimento (idempotente)."""
    with app.app_context():
        from app.models.user import User

        if User.query.filter_by(username="admin").first():
            print("Usuário 'admin' já existe.")
        else:
            admin = User(username="admin", email="admin@prospectbarber.local", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            print("Admin criado: admin / admin123")


@app.cli.command("seed-kits")
def seed_kits():
    """
    Cria kits de serviço de exemplo. Não insere se já houver kits.
    Edite este seed com os kits do seu cliente antes de usar em produção.
    """
    with app.app_context():
        from app.models.service_kit import ServiceKit, ServiceKitItem
        from app.models.service import Service

        if ServiceKit.query.count() > 0:
            print("Kits já existem. Nenhum kit inserido.")
            return

        print("Nenhum kit de exemplo definido. Edite 'seed-kits' em run.py para adicionar os kits do cliente.")


@app.cli.command("seed-subscription-plans")
def seed_subscription_plans():
    """
    Cria planos de assinatura de exemplo. Não insere se já houver planos.
    Edite este seed com os planos do seu cliente antes de usar em produção.
    """
    with app.app_context():
        from app.models.subscription_plan import SubscriptionPlan

        if SubscriptionPlan.query.count() > 0:
            print("Planos de assinatura já existem. Nenhum plano inserido.")
            return

        print("Nenhum plano de exemplo definido. Edite 'seed-subscription-plans' em run.py para adicionar os planos do cliente.")


@app.cli.command("seed-services")
def seed_services():
    """
    Popula serviços de exemplo. Não insere se já houver serviços.
    Edite este seed com os serviços reais do cliente antes de usar em produção.
    """
    with app.app_context():
        from app.models.service import Service

        if Service.query.count() > 0:
            print("Tabela de serviços já possui dados. Nenhum serviço inserido.")
            return

        print("Nenhum serviço de exemplo definido. Edite 'seed-services' em run.py para adicionar os serviços do cliente.")


@app.cli.command("seed-prospect")
def seed_prospect():
    """Cria o usuário admin principal do cliente Prospect (idempotente)."""
    with app.app_context():
        from app.models.user import User

        email = "administrativo@theprospect.com.br"
        if User.query.filter_by(email=email).first():
            print(f"Usuário com e-mail '{email}' já existe.")
            return

        user = User(username="prospect", email=email, role="admin")
        user.set_password("Prospect@2025!")
        db.session.add(user)
        db.session.commit()
        print(f"Admin criado: prospect / Prospect@2025! ({email})")
        print("Altere a senha após o primeiro login!")


if __name__ == "__main__":
    app.run(debug=app.debug, host="0.0.0.0", port=5000)
