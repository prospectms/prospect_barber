"""Fase 1-B — isolamento cross-tenant nos 9 models satélite.

SATELLITE_FEATURES_ENABLED continua False no código real (só vira True
depois que esta suíte passar). Aqui ela é ligada temporariamente via
monkeypatch (fixture `satelite_ligado`), revertida automaticamente ao
fim de cada teste — sem isso as rotas de raffle/subscriptions
redirecionam antes de qualquer coisa
(@bloqueado_enquanto_satelite_desativado).

ServiceKit e SubscriptionPlan não têm nenhuma rota de criação no app
hoje (só via shell/seed, mesma limitação documentada em run.py) —
testados no nível de model/query direto via test_request_context, não
via HTTP.
"""
import itertools
from datetime import date, time, timedelta

import pytest

# Vários testes deste arquivo MUTAM dado satélite (consumir crédito, sortear)
# -- diferente de empresa_a/empresa_b (Fase 1-A), este fixture não pode ser
# module-scoped/reaproveitado. Sendo function-scoped, cada teste precisa de
# uma tag única (slug único) já que _clean_db só limpa no fim do MÓDULO, não
# por função -- sem isso, a 2ª chamada dentro do mesmo arquivo colide no
# slug da 1ª (erro real encontrado rodando este arquivo, não hipotético).
_tag_counter = itertools.count()


@pytest.fixture
def satelite_ligado(monkeypatch):
    """Liga SATELLITE_FEATURES_ENABLED=True só pra este teste. Precisa
    patchear cada binding importado via `from ... import
    SATELLITE_FEATURES_ENABLED` separadamente — Python copia o valor pro
    namespace de quem importou, patchear só o módulo original não
    alcança essas cópias."""
    import app.utils.feature_flags as ff
    import app.booking.routes as booking_routes
    import app.appointments.routes as appt_routes
    import app.client.routes as client_routes
    import app.subscriptions.routes as sub_routes
    for mod in (ff, booking_routes, appt_routes, client_routes, sub_routes):
        monkeypatch.setattr(mod, "SATELLITE_FEATURES_ENABLED", True)


def _empresa_com_satelite(db, tag, cpf, saas_plano_id):
    """Empresa mínima com dado satélite completo: kit (com item), plano de
    assinatura (com credit), assinatura ativa com saldo de crédito,
    agendamento concluído (pro pool do sorteio) e um sorteio pendente."""
    from app.models.empresa import Empresa
    from app.models.unidade import Unidade
    from app.models.usuario import Usuario
    from app.models.servico import Servico
    from app.models.cliente import Cliente
    from app.models.profissional import Profissional
    from app.models.agendamento import Agendamento
    from app.models.service_kit import ServiceKit, ServiceKitItem
    from app.models.subscription_plan import SubscriptionPlan, SubscriptionPlanCredit
    from app.models.subscription import CustomerSubscription, SubscriptionCreditBalance
    from app.models.raffle import Raffle

    empresa = Empresa(nome=f"Empresa Sat {tag}", slug=f"empresa-sat-{tag}", plano_id=saas_plano_id, status_assinatura="ativa")
    db.session.add(empresa)
    db.session.flush()

    unidade = Unidade(empresa_id=empresa.id, nome=f"Unidade Sat {tag}", slug=f"unidade-sat-{tag}", ativa=True)
    db.session.add(unidade)
    db.session.flush()

    dono = Usuario(empresa_id=empresa.id, nome=f"Dono Sat {tag}", email=f"dono@sat-{tag}.example.com", papel="dono")
    dono.set_password("senha123")
    db.session.add(dono)

    servico = Servico(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Corte {tag}", price=30, duration_minutes=30, is_active=True)
    db.session.add(servico)
    prof = Profissional(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Prof Sat {tag}", is_active=True)
    db.session.add(prof)
    cliente = Cliente(empresa_id=empresa.id, name=f"Cliente Sat {tag}", phone=f"11888{tag}0000", cpf=cpf)
    db.session.add(cliente)
    db.session.flush()

    kit = ServiceKit(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Kit {tag}", active=True)
    db.session.add(kit)
    db.session.flush()
    db.session.add(ServiceKitItem(
        empresa_id=empresa.id, unidade_id=unidade.id,
        kit_id=kit.id, service_id=servico.id, order=1,
    ))

    sub_plan = SubscriptionPlan(empresa_id=empresa.id, unidade_id=unidade.id, name=f"Clube {tag}", price=99, active=True)
    db.session.add(sub_plan)
    db.session.flush()
    db.session.add(SubscriptionPlanCredit(
        empresa_id=empresa.id, unidade_id=unidade.id,
        plan_id=sub_plan.id, service_id=servico.id, quantity=4,
    ))
    db.session.flush()

    subscription = CustomerSubscription(
        empresa_id=empresa.id, customer_id=cliente.id, plan_id=sub_plan.id,
        start_date=date.today(), end_date=date.today() + timedelta(days=30), status="active",
    )
    db.session.add(subscription)
    db.session.flush()
    balance = SubscriptionCreditBalance(
        empresa_id=empresa.id, subscription_id=subscription.id,
        service_id=servico.id, total_credits=4, used_credits=0,
    )
    db.session.add(balance)

    agendamento = Agendamento(
        empresa_id=empresa.id, unidade_id=unidade.id,
        customer_id=cliente.id, barber_id=prof.id, service_id=servico.id,
        scheduled_date=date.today(), scheduled_time=time(10, 0), status="completed",
    )
    db.session.add(agendamento)

    raffle = Raffle(
        empresa_id=empresa.id, name=f"Sorteio {tag}",
        start_date=date.today() - timedelta(days=1), end_date=date.today() + timedelta(days=1),
        winner_count=5, status="pending",
    )
    db.session.add(raffle)

    db.session.commit()
    return {
        "empresa_id": empresa.id, "unidade_id": unidade.id,
        "dono_email": dono.email, "senha": "senha123",
        "servico_id": servico.id, "cliente_id": cliente.id, "cliente_nome": cliente.name,
        "kit_id": kit.id, "sub_plan_id": sub_plan.id,
        "subscription_id": subscription.id, "balance_id": balance.id,
        "agendamento_id": agendamento.id, "raffle_id": raffle.id, "raffle_nome": raffle.name,
    }


@pytest.fixture
def empresas_satelite(app, db, planos):
    n = next(_tag_counter)
    with app.app_context():
        a = _empresa_com_satelite(db, f"a{n}", cpf="111.444.777-35", saas_plano_id=planos["pro"])
        b = _empresa_com_satelite(db, f"b{n}", cpf="111.444.777-35", saas_plano_id=planos["pro"])
        return a, b


# ── 1. ServiceKit / SubscriptionPlan — isolamento por query direta ───────────
def test_servicekit_isolamento_por_query(app, empresas_satelite):
    from flask import g
    from app.models.service_kit import ServiceKit
    a, b = empresas_satelite
    with app.test_request_context():
        g.empresa_id = a["empresa_id"]
        kits = ServiceKit.query.all()
        assert [k.id for k in kits] == [a["kit_id"]]
        assert ServiceKit.query.get(b["kit_id"]) is None  # get_or_404-style, IDOR direto


def test_subscriptionplan_isolamento_por_query(app, empresas_satelite):
    from flask import g
    from app.models.subscription_plan import SubscriptionPlan
    a, b = empresas_satelite
    with app.test_request_context():
        g.empresa_id = b["empresa_id"]
        planos = SubscriptionPlan.query.all()
        assert [p.id for p in planos] == [b["sub_plan_id"]]
        assert SubscriptionPlan.query.get(a["sub_plan_id"]) is None


# ── 2. Raffle — isolamento cross-tenant + IDOR ────────────────────────────────
def test_raffle_index_nao_vaza_sorteio_de_outra_empresa(app, client, login, satelite_ligado, empresas_satelite):
    a, b = empresas_satelite
    login(a["dono_email"], a["senha"])
    client.post("/auth/unidade", data={"unidade_id": a["unidade_id"]}, follow_redirects=True)
    r = client.get("/raffle/")
    assert r.status_code == 200
    assert a["raffle_nome"] in r.text
    assert b["raffle_nome"] not in r.text


def test_raffle_idor_detail_da_404(app, client, login, satelite_ligado, empresas_satelite):
    a, b = empresas_satelite
    login(a["dono_email"], a["senha"])
    client.post("/auth/unidade", data={"unidade_id": a["unidade_id"]}, follow_redirects=True)
    r = client.get(f"/raffle/{b['raffle_id']}")
    assert r.status_code == 404


def test_raffle_pool_nao_inclui_cliente_de_outra_empresa(app, db, client, login, satelite_ligado, empresas_satelite):
    """O risco apontado no relatório original: o pool do sorteio agregava
    Agendamento sem filtro nenhum. Empresa B também tem um agendamento
    'completed' dentro da mesma janela de datas -- se o isolamento
    falhar, o cliente de B pode acabar sorteado no draw de A."""
    a, b = empresas_satelite
    login(a["dono_email"], a["senha"])
    client.post("/auth/unidade", data={"unidade_id": a["unidade_id"]}, follow_redirects=True)

    r = client.post(f"/raffle/{a['raffle_id']}/draw", follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        from app.models.raffle import RaffleWinner
        winners = RaffleWinner.query.filter_by(raffle_id=a["raffle_id"]).all()
        assert len(winners) == 1
        assert winners[0].customer_id == a["cliente_id"]
        assert winners[0].customer_name == a["cliente_nome"]
        assert winners[0].empresa_id == a["empresa_id"]


# ── 3. Subscriptions — isolamento cross-tenant + IDOR ─────────────────────────
def test_subscriptions_index_nao_vaza_assinatura_de_outra_empresa(app, client, login, satelite_ligado, empresas_satelite):
    a, b = empresas_satelite
    login(a["dono_email"], a["senha"])
    client.post("/auth/unidade", data={"unidade_id": a["unidade_id"]}, follow_redirects=True)
    r = client.get("/subscriptions/")
    assert r.status_code == 200
    assert a["cliente_nome"] in r.text
    assert b["cliente_nome"] not in r.text


def test_subscriptions_idor_detail_da_404(app, client, login, satelite_ligado, empresas_satelite):
    a, b = empresas_satelite
    login(a["dono_email"], a["senha"])
    client.post("/auth/unidade", data={"unidade_id": a["unidade_id"]}, follow_redirects=True)
    r = client.get(f"/subscriptions/{b['subscription_id']}")
    assert r.status_code == 404


# ── 4. Crédito de assinatura — o cenário "mais arriscado" do relatório ────────
def test_consume_credit_nao_atravessa_empresa(app, db, empresas_satelite):
    """Tenta consumir crédito passando empresa_id de A mas customer_id de
    B (simula um ataque que burlou a camada de rota) -- tem que falhar
    sem tocar no saldo real de B."""
    from app.subscriptions.service import consume_credit
    a, b = empresas_satelite
    with app.app_context():
        from app.models.subscription import SubscriptionCreditBalance
        consumiu = consume_credit(a["empresa_id"], b["cliente_id"], b["servico_id"], b["agendamento_id"])
        assert consumiu is False

        saldo_b = SubscriptionCreditBalance.query.get(b["balance_id"])
        assert saldo_b.used_credits == 0  # nao mudou


def test_refund_credit_nao_atravessa_empresa(app, db, empresas_satelite):
    """Cria um uso real em B, tenta estornar informando empresa_id de A --
    tem que falhar sem apagar o uso nem alterar o saldo de B."""
    from app.subscriptions.service import consume_credit, refund_credit
    a, b = empresas_satelite
    with app.app_context():
        from app.models.subscription import SubscriptionCreditBalance, SubscriptionCreditUsage
        ok = consume_credit(b["empresa_id"], b["cliente_id"], b["servico_id"], b["agendamento_id"])
        assert ok is True
        saldo_b = SubscriptionCreditBalance.query.get(b["balance_id"])
        assert saldo_b.used_credits == 1

        estornou = refund_credit(a["empresa_id"], b["agendamento_id"])
        assert estornou is False

        db.session.refresh(saldo_b)
        assert saldo_b.used_credits == 1  # continua consumido, nao foi estornado por A
        assert SubscriptionCreditUsage.query.filter_by(
            empresa_id=b["empresa_id"], appointment_id=b["agendamento_id"]
        ).count() == 1  # uso de B continua existindo


def test_check_credit_nao_vaza_saldo_de_outra_empresa(app, empresas_satelite):
    from app.subscriptions.service import check_credit
    a, b = empresas_satelite
    with app.app_context():
        resultado = check_credit(a["empresa_id"], b["cliente_id"], b["servico_id"])
        assert resultado == {"has_credit": False}

        resultado_certo = check_credit(b["empresa_id"], b["cliente_id"], b["servico_id"])
        assert resultado_certo["has_credit"] is True
