"""Lógica de negócio da Fase 3 (gateway Asaas): checkout, aplicação de
evento de webhook e downgrade automático por inadimplência.

Toda função aqui recebe os models já resolvidos (Empresa/Plano/Assinatura)
ou empresa_id explícito -- mesmo padrão de app/subscriptions/service.py e
app/utils/limites.py, nunca depende de g.empresa_id ambiente (o webhook
roda fora de request de tenant nenhum).
"""
from datetime import date, datetime, timedelta, timezone

from app.extensions import db
from app.models.assinatura import Assinatura, AsaasWebhookEvent
from app.models.empresa import Empresa
from app.models.plano import Plano
from app.utils import asaas_client

DIAS_INADIMPLENCIA_PARA_DOWNGRADE = 8

_CICLO_ASAAS = {"mensal": "MONTHLY", "anual": "YEARLY"}

# Eventos que confirmam pagamento -- ver app/billing/service.py:aplicar_evento_webhook.
# PAYMENT_RECEIVED = dinheiro já disponível; PAYMENT_CONFIRMED = pagamento
# concluído mas fundo ainda não liberado (cartão captura, boleto compensando)
# -- ambos liberam o plano por decisão do usuário (Fase 3, item 1).
_EVENTOS_CONFIRMACAO = {"PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"}
_EVENTOS_INADIMPLENCIA = {"PAYMENT_OVERDUE"}


class CheckoutError(Exception):
    """Erro de negócio no checkout (Asaas falhou, dado inválido) -- rota
    exibe self.args[0] como flash e mantém o dono na tela de checkout."""


def _agora_utc_naive() -> datetime:
    """Colunas DateTime deste projeto são 'timestamp without time zone'
    (mesmo padrão de Empresa.criada_em) -- comparação sempre em UTC naive."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sincronizar_status_empresa(assinatura: Assinatura) -> None:
    """Espelha Assinatura.status em Empresa.status_assinatura -- chamado
    sempre que Assinatura.status muda, na mesma transação (decisão
    explícita do usuário, Fase 3 item 2). Não comita -- quem chama comita."""
    empresa = Empresa.query.get(assinatura.empresa_id)
    if empresa is not None:
        empresa.status_assinatura = assinatura.status


def iniciar_checkout(
    *,
    empresa: Empresa,
    plano: Plano,
    periodicidade: str,
    forma_pagamento: str,
    documento: str,
    email: str,
    telefone: str | None,
    remote_ip: str,
    dados_cartao: asaas_client.CreditCard | None = None,
    dados_titular_cartao: asaas_client.CreditCardHolderInfo | None = None,
) -> Assinatura:
    """Cria cliente (se necessário) + assinatura na Asaas e persiste a
    Assinatura local com status='pendente'. NUNCA muda Empresa.plano_id
    aqui -- só o webhook de confirmação faz isso (decisão Fase 3 item 1:
    zero janela de acesso pago sem pagamento confirmado)."""
    if periodicidade not in _CICLO_ASAAS:
        raise CheckoutError("Periodicidade inválida.")
    if forma_pagamento not in ("pix", "cartao"):
        raise CheckoutError("Forma de pagamento inválida.")
    if forma_pagamento == "cartao" and (dados_cartao is None or dados_titular_cartao is None):
        raise CheckoutError("Dados do cartão são obrigatórios para pagamento com cartão.")

    empresa.documento = documento
    empresa.email = email
    empresa.telefone = telefone

    ultima = (
        Assinatura.query.filter_by(empresa_id=empresa.id)
        .order_by(Assinatura.criado_em.desc())
        .first()
    )
    if ultima is not None:
        asaas_customer_id = ultima.asaas_customer_id
    else:
        cliente = asaas_client.create_customer(
            name=empresa.nome, cpf_cnpj=documento, email=email,
            mobile_phone=telefone, external_reference=str(empresa.id),
        )
        asaas_customer_id = cliente["id"]

    valor = float(plano.preco_mensal if periodicidade == "mensal" else plano.preco_anual)
    ciclo = _CICLO_ASAAS[periodicidade]
    hoje = date.today().isoformat()
    descricao = f"Prospect Barber -- plano {plano.nome} ({periodicidade})"

    if forma_pagamento == "pix":
        resposta = asaas_client.create_subscription_pix(
            customer_id=asaas_customer_id, value=valor, cycle=ciclo, next_due_date=hoje,
            description=descricao, external_reference=str(empresa.id),
        )
    else:
        resposta = asaas_client.create_subscription_credit_card(
            customer_id=asaas_customer_id, value=valor, cycle=ciclo, next_due_date=hoje,
            credit_card=dados_cartao, holder_info=dados_titular_cartao, remote_ip=remote_ip,
            description=descricao, external_reference=str(empresa.id),
        )

    try:
        invoice_url = asaas_client.get_first_payment_invoice_url(resposta["id"])
    except asaas_client.AsaasError:
        # Não derruba o checkout por isso -- a Assinatura já foi criada de
        # verdade na Asaas. Só o botão "Pagar agora" fica ausente na tela
        # de status; o dono ainda pode achar a fatura pelo painel Asaas ou
        # pelo e-mail que a Asaas manda automaticamente.
        invoice_url = None

    assinatura = Assinatura(
        empresa_id=empresa.id,
        asaas_customer_id=asaas_customer_id,
        asaas_subscription_id=resposta["id"],
        status="pendente",
        plano_id=plano.id,
        valor=valor,
        periodicidade=periodicidade,
        forma_pagamento=forma_pagamento,
        proximo_vencimento=date.today(),
        invoice_url=invoice_url,
    )
    db.session.add(assinatura)
    sincronizar_status_empresa(assinatura)
    db.session.commit()
    return assinatura


def aplicar_evento_webhook(payload: dict) -> str:
    """Aplica um evento de webhook já autenticado (token validado na rota).
    Idempotente via AsaasWebhookEvent.asaas_event_id. Retorna uma string
    curta descrevendo o resultado (pra log), nunca lança em evento
    desconhecido ou assinatura não encontrada -- só ignora (evento de um
    tipo que não tratamos, ou de uma assinatura de outra instância/teste)."""
    event_id = payload.get("id")
    evento = payload.get("event")
    if not event_id or not evento:
        return "payload_invalido"

    if AsaasWebhookEvent.query.filter_by(asaas_event_id=event_id).first() is not None:
        return "duplicado_ignorado"

    db.session.add(AsaasWebhookEvent(asaas_event_id=event_id, evento=evento))

    subscription_id = (payload.get("payment") or {}).get("subscription")
    if not subscription_id:
        db.session.commit()
        return "sem_subscription_id"

    assinatura = Assinatura.query.filter_by(asaas_subscription_id=subscription_id).first()
    if assinatura is None:
        db.session.commit()
        return "assinatura_nao_encontrada"

    if evento in _EVENTOS_CONFIRMACAO:
        assinatura.status = "ativa"
        assinatura.inadimplente_desde = None
        empresa = Empresa.query.get(assinatura.empresa_id)
        if empresa is not None:
            empresa.plano_id = assinatura.plano_id
        sincronizar_status_empresa(assinatura)
        db.session.commit()
        return "confirmado"

    if evento in _EVENTOS_INADIMPLENCIA:
        if assinatura.status != "inadimplente":
            assinatura.status = "inadimplente"
            assinatura.inadimplente_desde = _agora_utc_naive()
            sincronizar_status_empresa(assinatura)
        db.session.commit()
        return "marcado_inadimplente"

    db.session.commit()
    return "evento_nao_tratado"


def downgrade_inadimplentes() -> int:
    """Job diário: qualquer Assinatura inadimplente há >= 8 dias derruba
    Empresa.plano_id pro Free. Nunca deleta/desativa recurso em excesso
    (Unidade/Usuario/Servico acima do limite Free continuam existindo,
    só pode_criar() passa a bloquear crescimento -- decisão Fase 3).
    Assinatura.status continua 'inadimplente' (sem estado 'suspensa'
    intermediário, sem plano_anterior_id -- decisão explícita do usuário).
    Idempotente: rodar de novo em empresa já rebaixada não faz nada."""
    limite = _agora_utc_naive() - timedelta(days=DIAS_INADIMPLENCIA_PARA_DOWNGRADE)
    plano_free = Plano.query.filter_by(nome="free").first()
    if plano_free is None:
        return 0

    candidatas = Assinatura.query.filter(
        Assinatura.status == "inadimplente",
        Assinatura.inadimplente_desde.isnot(None),
        Assinatura.inadimplente_desde <= limite,
    ).all()

    rebaixadas = 0
    for assinatura in candidatas:
        empresa = Empresa.query.get(assinatura.empresa_id)
        if empresa is not None and empresa.plano_id != plano_free.id:
            empresa.plano_id = plano_free.id
            rebaixadas += 1
    db.session.commit()
    return rebaixadas
