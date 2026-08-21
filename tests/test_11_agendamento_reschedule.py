"""Categoria 11 — remarcação de Agendamento pelo painel do dono/gerente
(auditoria de completude pré-lançamento).

Agendamento só tinha mudança de status e exclusão — remarcar (trocar
data/horário/profissional/serviço sem apagar e recriar) só existia pelo
portal do cliente (Fase 2). Reaproveita o mesmo padrão de
agendamento_original_id: cancela o agendamento antigo, cria um novo
apontando pra ele, e NUNCA chama registrar_agendamento_criado() -- senão
UsoMensal contaria a remarcação como um agendamento novo.

Fixture própria (não empresa_a/b) porque o teste central precisa de um
UsoMensal com contagem conhecida antes/depois da remarcação.
"""
import itertools
from datetime import date, time, timedelta

import pytest

from app.models.agendamento import Agendamento
from app.utils.uso import registrar_agendamento_criado, uso_mensal_atual

_contador = itertools.count()


def _criar_empresa_com_agendamento(db):
    from app.models.empresa import Empresa
    from app.models.unidade import Unidade
    from app.models.usuario import Usuario
    from app.models.plano import Plano
    from app.models.profissional import Profissional
    from app.models.servico import Servico
    from app.models.cliente import Cliente

    n = next(_contador)
    plano_ilimitado = Plano.query.filter_by(nome="ilimitado").first()

    empresa = Empresa(nome=f"Empresa Reschedule {n}", slug=f"empresa-reschedule-{n}",
                       plano_id=plano_ilimitado.id, status_assinatura="ativa")
    db.session.add(empresa)
    db.session.flush()

    unidade = Unidade(empresa_id=empresa.id, nome=f"Unidade {n}", slug=f"unidade-reschedule-{n}", ativa=True)
    db.session.add(unidade)
    db.session.flush()

    dono = Usuario(empresa_id=empresa.id, nome=f"Dono {n}", email=f"dono@reschedule-{n}.example.com", papel="dono")
    dono.set_password("senha123")
    gerente = Usuario(empresa_id=empresa.id, nome=f"Gerente {n}", email=f"gerente@reschedule-{n}.example.com", papel="gerente")
    gerente.set_password("senha123")
    func = Usuario(empresa_id=empresa.id, nome=f"Func {n}", email=f"func@reschedule-{n}.example.com", papel="funcionario")
    func.set_password("senha123")
    db.session.add_all([dono, gerente, func])
    db.session.flush()

    prof1 = Profissional(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Prof1 {n}", is_active=True)
    prof2 = Profissional(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Prof2 {n}", is_active=True)
    db.session.add_all([prof1, prof2])

    servico1 = Servico(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Corte {n}",
                        price=30, duration_minutes=30, is_active=True)
    servico2 = Servico(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Barba {n}",
                        price=20, duration_minutes=20, is_active=True)
    db.session.add_all([servico1, servico2])

    cliente = Cliente(empresa_id=empresa.id, name=f"Cliente {n}", phone=f"1199{n:07d}"[:11])
    db.session.add(cliente)
    db.session.flush()

    amanha = date.today() + timedelta(days=1)
    appt = Agendamento(
        empresa_id=empresa.id, unidade_id=unidade.id,
        customer_id=cliente.id, barber_id=prof1.id, service_id=servico1.id,
        scheduled_date=amanha, scheduled_time=time(10, 0), status="pending",
    )
    db.session.add(appt)
    db.session.flush()
    # Simula o que a criação real (via rota) já teria feito -- fixture usa
    # ORM direto, não passa pela rota, então chama isso manualmente pra ter
    # um UsoMensal com contagem conhecida (1) antes do teste de remarcação.
    registrar_agendamento_criado(empresa.id)
    db.session.commit()

    return {
        "empresa_id": empresa.id, "unidade_id": unidade.id,
        "dono_email": dono.email, "gerente_email": gerente.email, "func_email": func.email,
        "senha": "senha123",
        "prof1_id": prof1.id, "prof2_id": prof2.id,
        "servico1_id": servico1.id, "servico2_id": servico2.id,
        "cliente_id": cliente.id, "appt_id": appt.id,
        "amanha": amanha,
    }


@pytest.fixture
def empresa(app, db, planos, login, client):
    with app.app_context():
        dados = _criar_empresa_com_agendamento(db)
    login(dados["dono_email"], dados["senha"])
    client.post("/auth/unidade", data={"unidade_id": dados["unidade_id"]}, follow_redirects=True)
    return dados


def _reschedule(client, e, **overrides):
    data = {
        "customer_id": e["cliente_id"],  # normalmente escondido no template (ver reschedule.html)
        "barber_id": e["prof2_id"], "service_id": e["servico2_id"],
        "scheduled_date": str(e["amanha"] + timedelta(days=1)),
        "scheduled_time": "14:00", "notes": "",
    }
    data.update(overrides)
    return client.post(f"/appointments/{e['appt_id']}/reschedule", data=data, follow_redirects=True)


# ── comportamento principal ──────────────────────────────────────────────────
def test_reschedule_cancela_original_e_cria_novo_com_original_id(app, db, client, empresa):
    e = empresa
    r = _reschedule(client, e)
    assert r.status_code == 200
    assert "remarcado com sucesso" in r.text.lower()

    with app.app_context():
        original = Agendamento.query.get(e["appt_id"])
        assert original.status == "cancelled"

        novo = Agendamento.query.filter_by(agendamento_original_id=e["appt_id"]).first()
        assert novo is not None
        assert novo.customer_id == e["cliente_id"]  # cliente não muda
        assert novo.barber_id == e["prof2_id"]
        assert novo.service_id == e["servico2_id"]
        assert novo.scheduled_time == time(14, 0)
        assert novo.status == "pending"


def test_reschedule_nao_infla_uso_mensal(app, db, client, empresa):
    """O teste central deste bloco: remarcar NÃO pode contar como um
    agendamento novo pro limite real da plataforma (500/mês)."""
    e = empresa
    with app.app_context():
        antes = uso_mensal_atual(e["empresa_id"])
    assert antes == 1  # setado na fixture, simulando a criação original

    _reschedule(client, e)

    with app.app_context():
        depois = uso_mensal_atual(e["empresa_id"])
    assert depois == 1, f"UsoMensal deveria continuar 1 (só a criação original conta), veio {depois}"


def test_reschedule_rejeita_customer_id_forjado_no_post(app, db, client, empresa):
    """form.customer_id.choices só tem a própria opção (o cliente real do
    agendamento) -- um customer_id forjado no POST nem passa da validação
    do form (erro "not a valid choice"), mais seguro ainda do que só
    ignorar silenciosamente: a remarcação inteira falha, nada é criado."""
    from app.models.cliente import Cliente
    with app.app_context():
        outro_cliente = Cliente(empresa_id=empresa["empresa_id"], name="Outro Cliente", phone="11900000000")
        db.session.add(outro_cliente)
        db.session.commit()
        outro_cliente_id = outro_cliente.id

    r = _reschedule(client, empresa, customer_id=outro_cliente_id)
    assert r.status_code == 200  # re-renderiza o form, não redireciona

    with app.app_context():
        original = Agendamento.query.get(empresa["appt_id"])
        assert original.status == "pending"  # não foi cancelado
        novo = Agendamento.query.filter_by(agendamento_original_id=empresa["appt_id"]).first()
        assert novo is None  # nenhuma remarcação foi criada


# ── validação/guardas ────────────────────────────────────────────────────────
def test_reschedule_bloqueia_status_ja_finalizado(app, db, client, empresa):
    e = empresa
    with app.app_context():
        appt = Agendamento.query.get(e["appt_id"])
        appt.status = "completed"
        db.session.commit()

    r = _reschedule(client, e)
    assert "não pode ser remarcado" in r.text.lower()
    with app.app_context():
        assert Agendamento.query.filter_by(agendamento_original_id=e["appt_id"]).first() is None


def test_reschedule_bloqueia_horario_conflitante(app, db, client, empresa):
    e = empresa
    # cria um segundo agendamento real ocupando o profissional 2 no horário
    # que o teste vai tentar usar pra remarcar
    with app.app_context():
        conflito = Agendamento(
            empresa_id=e["empresa_id"], unidade_id=e["unidade_id"],
            customer_id=e["cliente_id"], barber_id=e["prof2_id"], service_id=e["servico2_id"],
            scheduled_date=e["amanha"] + timedelta(days=1), scheduled_time=time(14, 0),
            status="pending",
        )
        db.session.add(conflito)
        db.session.commit()

    r = _reschedule(client, e)
    assert "horário indisponível" in r.text.lower()
    with app.app_context():
        assert Agendamento.query.filter_by(agendamento_original_id=e["appt_id"]).first() is None


def test_reschedule_permite_manter_o_mesmo_horario_original(app, db, client, empresa):
    """exclude_appointment_id precisa excluir o próprio agendamento antigo
    da checagem de conflito -- senão nem manter o mesmo horário seria
    possível (o profissional 'já' teria esse slot ocupado por ele mesmo)."""
    e = empresa
    r = _reschedule(client, e, barber_id=e["prof1_id"], service_id=e["servico1_id"],
                     scheduled_date=str(e["amanha"]), scheduled_time="10:00")
    assert "remarcado com sucesso" in r.text.lower()


# ── permissão ────────────────────────────────────────────────────────────────
def test_funcionario_nao_acessa_reschedule(client, login, empresa):
    # a fixture `empresa` já loga como dono no mesmo client -- /auth/login
    # redireciona direto se já autenticado (ver app/auth/routes.py), então
    # sem logout aqui a sessão continuaria como dono, não funcionário.
    client.get("/auth/logout")
    login(empresa["func_email"], empresa["senha"])
    client.post("/auth/unidade", data={"unidade_id": empresa["unidade_id"]}, follow_redirects=True)

    r = client.get(f"/appointments/{empresa['appt_id']}/reschedule", follow_redirects=False)
    assert r.status_code == 302


def test_gerente_pode_remarcar(client, login, empresa):
    client.get("/auth/logout")
    login(empresa["gerente_email"], empresa["senha"])
    client.post("/auth/unidade", data={"unidade_id": empresa["unidade_id"]}, follow_redirects=True)

    r = _reschedule(client, empresa)
    assert "remarcado com sucesso" in r.text.lower()
