"""
Fixtures da suíte de testes da Fase 1-A.

Roda contra SQLite local em arquivo (scratchpad), não contra o Neon. Uma
primeira tentativa usou um banco Postgres dedicado (prospect_barber_test)
no mesmo projeto Neon do dev — funcionalmente correto, mas cada teste
monta 2 empresas completas (~10 INSERTs cada) e o volume de conexões
curtas abertas/fechadas em sequência (uma por fixture, via `with
app.app_context()`) esgotava o pool do lado do Neon meio da suíte, travando
sem erro claro em vez de falhar rápido. SQLite elimina a variável de rede
por completo — o que este arquivo testa é isolamento por empresa_id/
unidade_id na camada de aplicação (Python/SQLAlchemy), que não depende de
nenhum recurso específico do Postgres. A migração/schema real já foi
validada à parte contra o Neon (dry-run + aplicação documentados nos
commits anteriores desta fase); aqui o alvo é o comportamento das rotas.

`empresa_a`/`empresa_b` criam duas empresas completas e independentes
(Usuario dono + gerente + funcionário, Profissional, Cliente, Servico,
Agendamento) como linhas reais no banco — não mocks — pra que os testes
de isolamento tenham dado de verdade pra tentar vazar.
"""
import os
from datetime import date, time

_TEST_DB_PATH = os.path.join(
    r"C:\Users\NB-ALEX\AppData\Local\Temp\claude\d--Facul-barber-barber-prospect"
    r"\28317b5c-a259-4515-8ca4-71232707d571\scratchpad",
    "prospect_barber_test.db",
)
if os.path.exists(_TEST_DB_PATH):
    os.remove(_TEST_DB_PATH)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["FLASK_CONFIG"] = "development"

import pytest

from app import create_app
from app.extensions import db as _db

# Ordem de dependência (filhos antes dos pais) — mesma usada no downgrade
# da migração Alembic.
_TABLES = [
    "audit_log", "usuario_unidade",
    "subscription_credit_usage", "subscription_credit_balance", "customer_subscription",
    "subscription_plan_credit", "subscription_plan",
    "raffle_winners", "raffles",
    "service_kit_item", "service_kit",
    "appointments", "barber_schedule_exception",
    "services", "barbers", "customers",
    "users", "unidades", "empresas",
]


@pytest.fixture(scope="session")
def app():
    application = create_app("development")
    application.config.update(WTF_CSRF_ENABLED=False, TESTING=True, SERVER_NAME="localhost")
    with application.app_context():
        _db.drop_all()
        _db.create_all()
    yield application


@pytest.fixture(scope="session")
def db(app):
    return _db


@pytest.fixture(autouse=True)
def _clean_db(app, db):
    """Apaga tudo depois de CADA teste — cada teste começa com o banco vazio
    e monta suas próprias empresa_a/empresa_b, sem vazamento entre testes.
    DELETE tabela a tabela (não TRUNCATE, que é sintaxe só de Postgres) na
    ordem filhos->pais pra respeitar FK."""
    yield
    with app.app_context():
        for table in _TABLES:
            db.session.execute(db.text(f"DELETE FROM {table}"))
        db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    def _login(email: str, password: str):
        return client.post(
            "/auth/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )
    return _login


def _build_empresa(db, tag: str, cpf: str):
    """Monta uma empresa completa (2 unidades, dono, gerente, funcionário
    vinculado só à 1ª unidade, profissional, cliente, serviço, agendamento).
    Retorna só valores primitivos (ids/strings) — os objetos ORM ficam
    detached assim que a app-context fecha, então não são reaproveitáveis
    fora daqui."""
    from app.models.empresa import Empresa
    from app.models.unidade import Unidade
    from app.models.usuario import Usuario
    from app.models.usuario_unidade import UsuarioUnidade
    from app.models.profissional import Profissional
    from app.models.cliente import Cliente
    from app.models.servico import Servico
    from app.models.agendamento import Agendamento

    empresa = Empresa(nome=f"Empresa {tag}", slug=f"empresa-{tag}", plano_id=1, status_assinatura="ativa")
    db.session.add(empresa)
    db.session.flush()

    unidade = Unidade(empresa_id=empresa.id, nome=f"Unidade {tag} 1", slug=f"unidade-{tag}-1", ativa=True)
    db.session.add(unidade)
    unidade2 = Unidade(empresa_id=empresa.id, nome=f"Unidade {tag} 2", slug=f"unidade-{tag}-2", ativa=True)
    db.session.add(unidade2)
    unidade_inativa = Unidade(empresa_id=empresa.id, nome=f"Unidade {tag} Inativa", slug=f"unidade-{tag}-inativa", ativa=False)
    db.session.add(unidade_inativa)
    db.session.flush()

    dono = Usuario(empresa_id=empresa.id, nome=f"Dono {tag}", email=f"dono@empresa-{tag}.example.com", papel="dono")
    dono.set_password("senha123")
    db.session.add(dono)

    gerente = Usuario(empresa_id=empresa.id, nome=f"Gerente {tag}", email=f"gerente@empresa-{tag}.example.com", papel="gerente")
    gerente.set_password("senha123")
    db.session.add(gerente)

    func = Usuario(empresa_id=empresa.id, nome=f"Func {tag}", email=f"func@empresa-{tag}.example.com", papel="funcionario")
    func.set_password("senha123")
    db.session.add(func)
    db.session.flush()

    # Funcionário só vinculado à unidade 1 — usado no teste de categoria 5
    db.session.add(UsuarioUnidade(empresa_id=empresa.id, usuario_id=func.id, unidade_id=unidade.id))

    prof = Profissional(
        empresa_id=empresa.id, unidade_id=unidade.id, usuario_id=func.id,
        name=f"Profissional {tag}", is_active=True,
    )
    db.session.add(prof)

    servico = Servico(
        empresa_id=empresa.id, unidade_id=unidade.id,
        name=f"Corte {tag}", price=30, duration_minutes=30, is_active=True,
    )
    db.session.add(servico)
    db.session.flush()

    cliente = Cliente(empresa_id=empresa.id, name=f"Cliente {tag}", phone=f"1199999{tag[-4:].zfill(4)}", cpf=cpf)
    db.session.add(cliente)
    db.session.flush()

    appt = Agendamento(
        empresa_id=empresa.id, unidade_id=unidade.id,
        customer_id=cliente.id, barber_id=prof.id, service_id=servico.id,
        scheduled_date=date.today(), scheduled_time=time(10, 0),
        status="pending",
    )
    db.session.add(appt)
    db.session.commit()

    return {
        "empresa_id": empresa.id, "empresa_slug": empresa.slug, "empresa_nome": empresa.nome,
        "unidade_id": unidade.id, "unidade_slug": unidade.slug,
        "unidade2_id": unidade2.id, "unidade2_slug": unidade2.slug,
        "unidade_inativa_id": unidade_inativa.id, "unidade_inativa_slug": unidade_inativa.slug,
        "dono_email": dono.email, "dono_id": dono.id, "senha": "senha123",
        "gerente_email": gerente.email, "gerente_id": gerente.id,
        "func_email": func.email, "func_id": func.id,
        "prof_id": prof.id, "prof_nome": prof.name,
        "servico_id": servico.id, "servico_nome": servico.name,
        "cliente_id": cliente.id, "cliente_nome": cliente.name, "cliente_cpf": cliente.cpf,
        "agendamento_id": appt.id,
    }


@pytest.fixture
def empresa_a(app, db):
    with app.app_context():
        return _build_empresa(db, "a", cpf="111.444.777-35")


@pytest.fixture
def empresa_b(app, db):
    with app.app_context():
        return _build_empresa(db, "b", cpf="111.444.777-35")  # MESMO CPF de propósito (categoria 3)
