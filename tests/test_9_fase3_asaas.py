"""Categoria 9 — Fase 3 (gateway Asaas): checkout, webhook autenticado +
idempotente, downgrade automático por inadimplência.

Fixtures próprias (não empresa_a/empresa_b — essas são module-scoped e
reaproveitadas por outras categorias; Fase 3 muta plano_id/status_
assinatura constantemente, o que colidiria). asaas_client é sempre
monkeypatchado — nenhum teste chama a Asaas de verdade.
"""
import itertools
from datetime import datetime, timedelta, timezone

import pytest

from app.billing import service as billing_service
from app.models.assinatura import AsaasWebhookEvent, Assinatura
from app.models.empresa import Empresa
from app.models.plano import Plano
from app.models.unidade import Unidade
from app.utils.limites import pode_criar

_contador = itertools.count()
_WEBHOOK_TOKEN = "test-webhook-token-fase3"
_INTERNAL_TOKEN = "test-internal-token-fase3"


@pytest.fixture(autouse=True)
def _configura_token_webhook(app):
    app.config["ASAAS_WEBHOOK_TOKEN"] = _WEBHOOK_TOKEN
    app.config["INTERNAL_JOB_TOKEN"] = _INTERNAL_TOKEN


def _criar_empresa(db, plano_id, n_unidades_extra=0, documento="11144477735", email=None):
    n = next(_contador)
    empresa = Empresa(
        nome=f"Empresa Fase3 {n}", slug=f"empresa-fase3-{n}",
        plano_id=plano_id, status_assinatura="ativa",
        documento=documento, email=email or f"fase3-{n}@example.com",
    )
    db.session.add(empresa)
    db.session.flush()

    unidade = Unidade(empresa_id=empresa.id, nome=f"Unidade Fase3 {n}", slug=f"unidade-fase3-{n}", ativa=True)
    db.session.add(unidade)
    for i in range(n_unidades_extra):
        db.session.add(Unidade(
            empresa_id=empresa.id, nome=f"Unidade Fase3 {n} extra {i}",
            slug=f"unidade-fase3-{n}-extra-{i}", ativa=True,
        ))
    db.session.commit()
    return empresa.id


def _nova_assinatura(db, empresa_id, plano_id, status="pendente", inadimplente_desde=None,
                      forma_pagamento="pix", invoice_url=None):
    n = next(_contador)
    assinatura = Assinatura(
        empresa_id=empresa_id,
        asaas_customer_id=f"cus_test_{n}",
        asaas_subscription_id=f"sub_test_{n}",
        status=status,
        plano_id=plano_id,
        valor=79.99,
        periodicidade="mensal",
        forma_pagamento=forma_pagamento,
        inadimplente_desde=inadimplente_desde,
        invoice_url=invoice_url,
    )
    db.session.add(assinatura)
    db.session.commit()
    return assinatura


def _webhook_payload(event: str, event_id: str, subscription_id: str) -> dict:
    return {
        "id": event_id,
        "event": event,
        "dateCreated": "2026-08-06 10:00:00",
        "payment": {"object": "payment", "id": f"pay_{event_id}", "subscription": subscription_id},
    }


# ── 1. token do webhook ─────────────────────────────────────────────────────
def test_webhook_rejeita_sem_token(client):
    r = client.post("/webhooks/asaas", json=_webhook_payload("PAYMENT_CONFIRMED", "evt_sem_token", "sub_x"))
    assert r.status_code == 401


def test_webhook_rejeita_token_errado(client):
    r = client.post(
        "/webhooks/asaas",
        json=_webhook_payload("PAYMENT_CONFIRMED", "evt_token_errado", "sub_x"),
        headers={"asaas-access-token": "token-invalido"},
    )
    assert r.status_code == 401


def test_webhook_rejeita_quando_token_nao_configurado(client, app):
    app.config["ASAAS_WEBHOOK_TOKEN"] = ""
    r = client.post(
        "/webhooks/asaas",
        json=_webhook_payload("PAYMENT_CONFIRMED", "evt_sem_config", "sub_x"),
        headers={"asaas-access-token": ""},
    )
    assert r.status_code == 401


# ── 2. confirmação libera o plano ───────────────────────────────────────────
def test_webhook_confirmado_ativa_e_libera_plano(app, db, client, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["free"])
        assinatura = _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="pendente")
        sub_id = assinatura.asaas_subscription_id

    r = client.post(
        "/webhooks/asaas",
        json=_webhook_payload("PAYMENT_CONFIRMED", "evt_confirma_1", sub_id),
        headers={"asaas-access-token": _WEBHOOK_TOKEN},
    )
    assert r.status_code == 200

    with app.app_context():
        assinatura = Assinatura.query.filter_by(asaas_subscription_id=sub_id).first()
        assert assinatura.status == "ativa"
        assert assinatura.inadimplente_desde is None
        empresa = Empresa.query.get(empresa_id)
        assert empresa.plano_id == planos["pro"]
        assert empresa.status_assinatura == "ativa"


def test_webhook_received_tambem_ativa(app, db, client, planos):
    """PAYMENT_RECEIVED confirma igual PAYMENT_CONFIRMED (decisão Fase 3 item 1)."""
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["free"])
        assinatura = _nova_assinatura(db, empresa_id, plano_id=planos["essencial"], status="pendente")
        sub_id = assinatura.asaas_subscription_id

    r = client.post(
        "/webhooks/asaas",
        json=_webhook_payload("PAYMENT_RECEIVED", "evt_received_1", sub_id),
        headers={"asaas-access-token": _WEBHOOK_TOKEN},
    )
    assert r.status_code == 200
    with app.app_context():
        empresa = Empresa.query.get(empresa_id)
        assert empresa.plano_id == planos["essencial"]


# ── 3. overdue marca inadimplente sem mudar plano_id ────────────────────────
def test_webhook_overdue_marca_inadimplente_sem_derrubar_plano(app, db, client, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["pro"])
        assinatura = _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="ativa")
        sub_id = assinatura.asaas_subscription_id

    r = client.post(
        "/webhooks/asaas",
        json=_webhook_payload("PAYMENT_OVERDUE", "evt_overdue_1", sub_id),
        headers={"asaas-access-token": _WEBHOOK_TOKEN},
    )
    assert r.status_code == 200

    with app.app_context():
        assinatura = Assinatura.query.filter_by(asaas_subscription_id=sub_id).first()
        assert assinatura.status == "inadimplente"
        assert assinatura.inadimplente_desde is not None
        empresa = Empresa.query.get(empresa_id)
        assert empresa.plano_id == planos["pro"]  # downgrade só no job diário, não no webhook
        assert empresa.status_assinatura == "inadimplente"


# ── 4. idempotência ──────────────────────────────────────────────────────────
def test_webhook_duplicado_nao_reaplica(app, db, client, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["pro"])
        assinatura = _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="ativa")
        sub_id = assinatura.asaas_subscription_id

    payload = _webhook_payload("PAYMENT_OVERDUE", "evt_duplicado_1", sub_id)
    headers = {"asaas-access-token": _WEBHOOK_TOKEN}

    r1 = client.post("/webhooks/asaas", json=payload, headers=headers)
    assert r1.status_code == 200
    with app.app_context():
        marcado_em = Assinatura.query.filter_by(asaas_subscription_id=sub_id).first().inadimplente_desde
        assert AsaasWebhookEvent.query.filter_by(asaas_event_id="evt_duplicado_1").count() == 1

    r2 = client.post("/webhooks/asaas", json=payload, headers=headers)
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "duplicado_ignorado"

    with app.app_context():
        assinatura = Assinatura.query.filter_by(asaas_subscription_id=sub_id).first()
        assert assinatura.inadimplente_desde == marcado_em
        assert AsaasWebhookEvent.query.filter_by(asaas_event_id="evt_duplicado_1").count() == 1


def test_webhook_assinatura_nao_encontrada_nao_derruba(client):
    r = client.post(
        "/webhooks/asaas",
        json=_webhook_payload("PAYMENT_CONFIRMED", "evt_orfao_1", "sub_que_nao_existe"),
        headers={"asaas-access-token": _WEBHOOK_TOKEN},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "assinatura_nao_encontrada"


# ── 5. downgrade automático (dia 8) ─────────────────────────────────────────
def test_downgrade_rebaixa_inadimplente_ha_mais_de_8_dias(app, db, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["pro"])
        ha_9_dias = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=9)
        assinatura = _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="inadimplente", inadimplente_desde=ha_9_dias)

        rebaixadas = billing_service.downgrade_inadimplentes()
        assert rebaixadas == 1

        empresa = Empresa.query.get(empresa_id)
        assert empresa.plano_id == planos["free"]
        # sem estado 'suspensa', sem plano_anterior_id -- Assinatura.status
        # continua 'inadimplente' (decisão explícita do usuário, Fase 3).
        assert Assinatura.query.get(assinatura.id).status == "inadimplente"


def test_downgrade_nao_mexe_em_inadimplente_recente(app, db, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["pro"])
        ha_3_dias = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
        _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="inadimplente", inadimplente_desde=ha_3_dias)

        rebaixadas = billing_service.downgrade_inadimplentes()
        assert rebaixadas == 0
        assert Empresa.query.get(empresa_id).plano_id == planos["pro"]


def test_downgrade_e_idempotente(app, db, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["pro"])
        ha_10_dias = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
        _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="inadimplente", inadimplente_desde=ha_10_dias)

        assert billing_service.downgrade_inadimplentes() == 1
        assert billing_service.downgrade_inadimplentes() == 0  # já está free, roda de novo sem efeito
        assert Empresa.query.get(empresa_id).plano_id == planos["free"]


def test_downgrade_preserva_recursos_excedentes_mas_bloqueia_criacao(app, db, planos):
    """Regra de negócio central da Fase 3: recurso acima do limite do Free
    nunca é deletado/desativado, só pode_criar() passa a bloquear
    crescimento. Free tem max_unidades=1 (ver _seed_planos)."""
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["pro"], n_unidades_extra=1)  # nasce com 2 unidades
        ha_10_dias = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
        _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="inadimplente", inadimplente_desde=ha_10_dias)

        billing_service.downgrade_inadimplentes()

        assert Empresa.query.get(empresa_id).plano_id == planos["free"]
        assert Unidade.query.filter_by(empresa_id=empresa_id).count() == 2  # nenhuma apagada

        pode, motivo = pode_criar(empresa_id, "unidade")
        assert pode is False
        assert motivo == "upgrade_necessario"


# ── 5b. endpoint interno do job (cron do SO, substitui APScheduler) ─────────
def test_internal_downgrade_rejeita_sem_token(client):
    r = client.post("/internal/downgrade-inadimplentes")
    assert r.status_code == 401


def test_internal_downgrade_rejeita_token_errado(client):
    r = client.post("/internal/downgrade-inadimplentes", headers={"X-Internal-Token": "errado"})
    assert r.status_code == 401


def test_internal_downgrade_rejeita_quando_token_nao_configurado(client, app):
    app.config["INTERNAL_JOB_TOKEN"] = ""
    r = client.post("/internal/downgrade-inadimplentes", headers={"X-Internal-Token": ""})
    assert r.status_code == 401


def test_internal_downgrade_com_token_valido_roda_o_job(app, db, client, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["pro"])
        ha_9_dias = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=9)
        _nova_assinatura(db, empresa_id, plano_id=planos["pro"], status="inadimplente", inadimplente_desde=ha_9_dias)

    r = client.post("/internal/downgrade-inadimplentes", headers={"X-Internal-Token": _INTERNAL_TOKEN})
    assert r.status_code == 200
    assert r.get_json() == {"rebaixadas": 1}

    with app.app_context():
        assert Empresa.query.get(empresa_id).plano_id == planos["free"]


# ── 6. checkout não libera plano antes do webhook ───────────────────────────
def test_iniciar_checkout_nao_libera_plano_antes_da_confirmacao(app, db, planos, monkeypatch):
    monkeypatch.setattr(
        billing_service.asaas_client, "create_customer",
        lambda **kwargs: {"id": "cus_fake_1"},
    )
    monkeypatch.setattr(
        billing_service.asaas_client, "create_subscription_pix",
        lambda **kwargs: {"id": "sub_fake_1"},
    )

    with app.app_context():
        empresa_id = _criar_empresa(db, planos["free"])
        empresa = Empresa.query.get(empresa_id)
        plano_pro = Plano.query.filter_by(nome="pro").first()

        assinatura = billing_service.iniciar_checkout(
            empresa=empresa, plano=plano_pro, periodicidade="mensal", forma_pagamento="pix",
            documento="11144477735", email="dono@fase3.example.com", telefone=None,
            remote_ip="127.0.0.1",
        )

        assert assinatura.status == "pendente"
        assert assinatura.asaas_customer_id == "cus_fake_1"
        assert assinatura.asaas_subscription_id == "sub_fake_1"
        empresa = Empresa.query.get(empresa_id)
        assert empresa.plano_id == planos["free"]  # inalterado -- só o webhook libera
        assert empresa.status_assinatura == "pendente"


def test_iniciar_checkout_captura_invoice_url_da_primeira_cobranca(app, db, planos, monkeypatch):
    """Achado do smoke test contra o sandbox real (2026-08-12): a resposta
    de criação da assinatura não traz link de pagamento nenhum -- só o
    invoiceUrl da primeira cobrança (GET /v3/payments?subscription=<id>)
    dá pro cliente um jeito real de pagar. Sem capturar isso, a tela de
    status não tem o que mostrar no botão "Pagar agora"."""
    monkeypatch.setattr(billing_service.asaas_client, "create_customer", lambda **kwargs: {"id": "cus_inv_1"})
    monkeypatch.setattr(billing_service.asaas_client, "create_subscription_pix", lambda **kwargs: {"id": "sub_inv_1"})
    monkeypatch.setattr(
        billing_service.asaas_client, "get_first_payment_invoice_url",
        lambda subscription_id: f"https://sandbox.asaas.com/i/fake-{subscription_id}",
    )

    with app.app_context():
        empresa_id = _criar_empresa(db, planos["free"])
        empresa = Empresa.query.get(empresa_id)
        plano_pro = Plano.query.filter_by(nome="pro").first()

        assinatura = billing_service.iniciar_checkout(
            empresa=empresa, plano=plano_pro, periodicidade="mensal", forma_pagamento="pix",
            documento="11144477735", email="dono@fase3.example.com", telefone=None, remote_ip="127.0.0.1",
        )
        assert assinatura.invoice_url == "https://sandbox.asaas.com/i/fake-sub_inv_1"


def test_iniciar_checkout_sobrevive_falha_ao_buscar_invoice_url(app, db, planos, monkeypatch):
    """get_first_payment_invoice_url falhando não pode derrubar o checkout
    inteiro -- a Assinatura já existe de verdade na Asaas nesse ponto, só
    o botão "Pagar agora" fica ausente na tela de status."""
    monkeypatch.setattr(billing_service.asaas_client, "create_customer", lambda **kwargs: {"id": "cus_inv_2"})
    monkeypatch.setattr(billing_service.asaas_client, "create_subscription_pix", lambda **kwargs: {"id": "sub_inv_2"})

    def _falha(subscription_id):
        raise billing_service.asaas_client.AsaasError("timeout simulado")
    monkeypatch.setattr(billing_service.asaas_client, "get_first_payment_invoice_url", _falha)

    with app.app_context():
        empresa_id = _criar_empresa(db, planos["free"])
        empresa = Empresa.query.get(empresa_id)
        plano_pro = Plano.query.filter_by(nome="pro").first()

        assinatura = billing_service.iniciar_checkout(
            empresa=empresa, plano=plano_pro, periodicidade="mensal", forma_pagamento="pix",
            documento="11144477735", email="dono@fase3.example.com", telefone=None, remote_ip="127.0.0.1",
        )
        assert assinatura.status == "pendente"  # checkout completou normalmente
        assert assinatura.invoice_url is None


def test_iniciar_checkout_reaproveita_cliente_asaas_existente(app, db, planos, monkeypatch):
    chamadas_create_customer = []
    monkeypatch.setattr(
        billing_service.asaas_client, "create_customer",
        lambda **kwargs: chamadas_create_customer.append(1) or {"id": "cus_unico"},
    )
    monkeypatch.setattr(
        billing_service.asaas_client, "create_subscription_pix",
        lambda **kwargs: {"id": f"sub_{len(chamadas_create_customer)}_{kwargs['value']}"},
    )

    with app.app_context():
        empresa_id = _criar_empresa(db, planos["free"])
        empresa = Empresa.query.get(empresa_id)
        plano_essencial = Plano.query.filter_by(nome="essencial").first()
        plano_pro = Plano.query.filter_by(nome="pro").first()

        billing_service.iniciar_checkout(
            empresa=empresa, plano=plano_essencial, periodicidade="mensal", forma_pagamento="pix",
            documento="11144477735", email="dono@fase3.example.com", telefone=None, remote_ip="127.0.0.1",
        )
        billing_service.iniciar_checkout(
            empresa=empresa, plano=plano_pro, periodicidade="mensal", forma_pagamento="pix",
            documento="11144477735", email="dono@fase3.example.com", telefone=None, remote_ip="127.0.0.1",
        )

        assert len(chamadas_create_customer) == 1  # 2º checkout reaproveita o cliente Asaas


def test_iniciar_checkout_cartao_sem_dados_do_cartao_falha(app, db, planos):
    with app.app_context():
        empresa_id = _criar_empresa(db, planos["free"])
        empresa = Empresa.query.get(empresa_id)
        plano_pro = Plano.query.filter_by(nome="pro").first()

        with pytest.raises(billing_service.CheckoutError):
            billing_service.iniciar_checkout(
                empresa=empresa, plano=plano_pro, periodicidade="mensal", forma_pagamento="cartao",
                documento="11144477735", email="dono@fase3.example.com", telefone=None, remote_ip="127.0.0.1",
            )


# ── 7. rotas HTTP (checkout + status) ───────────────────────────────────────
@pytest.fixture
def login_dono_a(client, login, empresa_a):
    login(empresa_a["dono_email"], empresa_a["senha"])
    client.post("/auth/unidade", data={"unidade_id": empresa_a["unidade_id"]}, follow_redirects=True)
    return empresa_a


@pytest.fixture
def login_dono_b(client, login, empresa_b):
    login(empresa_b["dono_email"], empresa_b["senha"])
    client.post("/auth/unidade", data={"unidade_id": empresa_b["unidade_id"]}, follow_redirects=True)
    return empresa_b


def test_checkout_get_renderiza_formulario(client, login_dono_a, planos):
    r = client.get(f"/upgrade/checkout/{planos['pro']}")
    assert r.status_code == 200
    assert "Periodicidade" in r.text or "periodicidade" in r.text.lower()
    assert "Forma de pagamento" in r.text or "forma de pagamento" in r.text.lower()


def test_checkout_get_plano_free_redireciona_pro_index(client, login_dono_a, planos):
    r = client.get(f"/upgrade/checkout/{planos['free']}", follow_redirects=True)
    assert r.status_code == 200
    assert "não precisa de pagamento" in r.text.lower()


def test_checkout_post_telefone_malformado_rejeitado_sem_chamar_asaas(client, login_dono_a, planos, monkeypatch):
    chamado = []
    monkeypatch.setattr(billing_service.asaas_client, "create_customer", lambda **kwargs: chamado.append(1) or {"id": "cus_x"})

    r = client.post(
        f"/upgrade/checkout/{planos['pro']}",
        data={
            "periodicidade": "mensal", "forma_pagamento": "pix",
            "documento": "11144477735", "email": "dono@empresa-a.example.com",
            "telefone": "123",  # curto demais, formato invalido
        },
    )
    assert r.status_code == 200  # re-renderiza o form, não redireciona
    assert "celular inválido" in r.text.lower()
    assert chamado == []  # nem chegou a chamar a Asaas


def test_checkout_post_telefone_digito_repetido_rejeitado_com_mensagem_nossa(client, login_dono_a, planos, monkeypatch):
    """Caso exato que a própria Asaas rejeitou no smoke test contra o
    sandbox real (2026-08-12): "11999999999" -- 11 dígitos, DDD válido,
    começa com 9 (formato estruturalmente correto), mas claramente forjado
    (assinante todo em 9). Antes disso caía direto na Asaas e o dono via
    o erro cru dela ("O celular informado é inválido.") via CheckoutError;
    agora é barrado aqui, com mensagem nossa, antes de qualquer chamada."""
    chamado = []
    monkeypatch.setattr(billing_service.asaas_client, "create_customer", lambda **kwargs: chamado.append(1) or {"id": "cus_x"})

    r = client.post(
        f"/upgrade/checkout/{planos['pro']}",
        data={
            "periodicidade": "mensal", "forma_pagamento": "pix",
            "documento": "11144477735", "email": "dono@empresa-a.example.com",
            "telefone": "11999999999",
        },
    )
    assert r.status_code == 200
    assert "celular inválido" in r.text.lower()
    assert "o celular informado" not in r.text.lower()  # não é o erro cru da Asaas
    assert chamado == []


def test_status_page_sem_assinatura(client, login_dono_a):
    r = client.get("/upgrade/status")
    assert r.status_code == 200
    assert "nenhuma assinatura" in r.text.lower()


def test_checkout_post_pix_cria_assinatura_pendente_e_redireciona_pro_status(app, client, login_dono_a, planos, monkeypatch):
    """Roda depois de test_status_page_sem_assinatura de propósito -- essa
    é a única que grava uma Assinatura pra empresa_a nesta suíte, e a
    verificação de "sem assinatura ainda" precisa vir antes dela."""
    monkeypatch.setattr(billing_service.asaas_client, "create_customer", lambda **kwargs: {"id": "cus_http_1"})
    monkeypatch.setattr(billing_service.asaas_client, "create_subscription_pix", lambda **kwargs: {"id": "sub_http_1"})
    monkeypatch.setattr(
        billing_service.asaas_client, "get_first_payment_invoice_url",
        lambda subscription_id: "https://sandbox.asaas.com/i/fake-http-1",
    )

    r = client.post(
        f"/upgrade/checkout/{planos['pro']}",
        data={
            "periodicidade": "mensal", "forma_pagamento": "pix",
            "documento": "11144477735", "email": "dono@empresa-a.example.com", "telefone": "",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "/upgrade/status" in r.request.path
    assert "https://sandbox.asaas.com/i/fake-http-1" in r.text
    assert "pagar agora" in r.text.lower()

    with app.app_context():
        assinatura = Assinatura.query.filter_by(asaas_subscription_id="sub_http_1").first()
        assert assinatura is not None
        assert assinatura.invoice_url == "https://sandbox.asaas.com/i/fake-http-1"


def test_checkout_post_telefone_valido_passa_na_validacao(client, login_dono_a, planos, monkeypatch):
    """Roda por último de propósito -- também grava Assinatura pra
    empresa_a, então precisa vir depois de test_status_page_sem_assinatura."""
    monkeypatch.setattr(billing_service.asaas_client, "create_customer", lambda **kwargs: {"id": "cus_ok"})
    monkeypatch.setattr(billing_service.asaas_client, "create_subscription_pix", lambda **kwargs: {"id": "sub_ok_tel"})
    monkeypatch.setattr(billing_service.asaas_client, "get_first_payment_invoice_url", lambda subscription_id: None)

    r = client.post(
        f"/upgrade/checkout/{planos['pro']}",
        data={
            "periodicidade": "mensal", "forma_pagamento": "pix",
            "documento": "11144477735", "email": "dono@empresa-a.example.com",
            "telefone": "(11) 98765-4321",  # com formatação -- validador deve normalizar
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "celular inválido" not in r.text.lower()
    assert "/upgrade/status" in r.request.path


# ── 8. tela de status: aviso de Pix + link de pagamento sempre visível ──────
# Usa empresa_b (não empresa_a) de propósito -- isolado da longa cadeia de
# testes de checkout HTTP acima, que já depende de ordem de execução pra
# controlar qual é a Assinatura "mais recente" de empresa_a.
def test_status_pix_mostra_aviso_de_nao_e_debito_automatico(app, db, client, login_dono_b, planos):
    with app.app_context():
        _nova_assinatura(
            db, login_dono_b["empresa_id"], plano_id=planos["pro"], status="ativa",
            forma_pagamento="pix",
        )
    r = client.get("/upgrade/status")
    assert r.status_code == 200
    assert "não é débito automático" in r.text.lower()


def test_status_cartao_nao_mostra_aviso_de_pix(app, db, client, login_dono_b, planos):
    with app.app_context():
        _nova_assinatura(
            db, login_dono_b["empresa_id"], plano_id=planos["pro"], status="ativa",
            forma_pagamento="cartao",
        )
    r = client.get("/upgrade/status")
    assert r.status_code == 200
    assert "não é débito automático" not in r.text.lower()


def test_status_pagar_agora_visivel_durante_inadimplencia_nao_so_no_checkout(app, db, client, login_dono_b, planos):
    """Achado do Bloco 6: antes o botão "Pagar agora" só aparecia com
    status='pendente' (o momento do checkout) -- uma assinatura que ficou
    inadimplente em um ciclo já confirmado antes também tem uma cobrança em
    aberto real, mas o botão sumia."""
    with app.app_context():
        _nova_assinatura(
            db, login_dono_b["empresa_id"], plano_id=planos["pro"], status="inadimplente",
            forma_pagamento="pix", invoice_url="https://sandbox.asaas.com/i/inadimplente-1",
            inadimplente_desde=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    r = client.get("/upgrade/status")
    assert r.status_code == 200
    assert "https://sandbox.asaas.com/i/inadimplente-1" in r.text
    assert "pagar agora" in r.text.lower()


def test_status_pagar_agora_nao_aparece_quando_assinatura_ja_esta_ativa(app, db, client, login_dono_b, planos):
    """invoice_url não é atualizado a cada ciclo (ver comentário no model) --
    uma vez 'ativa', o link guardado é da cobrança já paga. Mostrar o botão
    aqui seria enganoso, então ele só aparece em pendente/inadimplente."""
    with app.app_context():
        _nova_assinatura(
            db, login_dono_b["empresa_id"], plano_id=planos["pro"], status="ativa",
            forma_pagamento="pix", invoice_url="https://sandbox.asaas.com/i/ja-paga",
        )
    r = client.get("/upgrade/status")
    assert r.status_code == 200
    assert "pagar agora" not in r.text.lower()
