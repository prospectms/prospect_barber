"""Helpers para consumo e estorno de créditos do Clube de Assinaturas.

Toda função aqui recebe `empresa_id` como parâmetro explícito e filtra
por ele diretamente — nunca depende do filtro automático de tenant
(TenantMixin/g.empresa_id ambiente), mesmo já sendo redundante com ele
na maioria das chamadas de hoje (decisão da Fase 1-B: defesa em camada,
igual pode_criar() em app/utils/limites.py — nenhuma dessas 6 funções
deveria só "funcionar por acidente" porque quem chamou já filtrou certo).
"""
from datetime import date
from app.extensions import db


def get_active_subscription(empresa_id: int, customer_id: int):
    """
    Retorna a assinatura ativa do cliente (dentro da empresa) ou None.
    Considera ativa: status=active + (prazo não vencido OU créditos restantes).
    """
    from app.models.subscription import CustomerSubscription
    today = date.today()

    sub = (
        CustomerSubscription.query
        .filter_by(empresa_id=empresa_id, customer_id=customer_id, status="active")
        .filter(CustomerSubscription.end_date >= today)
        .first()
    )
    if sub:
        return sub

    expired_subs = (
        CustomerSubscription.query
        .filter_by(empresa_id=empresa_id, customer_id=customer_id, status="active")
        .filter(CustomerSubscription.end_date < today)
        .all()
    )
    for expired in expired_subs:
        if expired.has_remaining_credits:
            return expired

    return None


def check_credit(empresa_id: int, customer_id: int, service_id: int) -> dict:
    """Verifica se o cliente tem crédito disponível para o serviço."""
    from app.models.subscription import SubscriptionCreditBalance
    sub = get_active_subscription(empresa_id, customer_id)
    if not sub:
        return {"has_credit": False}
    balance = SubscriptionCreditBalance.query.filter_by(
        empresa_id=empresa_id, subscription_id=sub.id, service_id=service_id,
    ).first()
    if not balance or balance.remaining_credits <= 0:
        return {"has_credit": False}
    return {
        "has_credit": True,
        "plan_name": sub.plan.name,
        "remaining": balance.remaining_credits,
    }


def check_credit_kit(empresa_id: int, customer_id: int, kit_id: int) -> dict:
    """Verifica se o cliente tem crédito para todos os serviços do kit."""
    from app.models.service_kit import ServiceKit
    from app.models.subscription import SubscriptionCreditBalance
    sub = get_active_subscription(empresa_id, customer_id)
    if not sub:
        return {"has_credit": False}
    kit = ServiceKit.query.filter_by(empresa_id=empresa_id, id=kit_id).first()
    if not kit:
        return {"has_credit": False}
    for item in kit.items:
        bal = SubscriptionCreditBalance.query.filter_by(
            empresa_id=empresa_id, subscription_id=sub.id, service_id=item.service_id,
        ).first()
        if not bal or bal.remaining_credits <= 0:
            return {"has_credit": False}
    return {
        "has_credit": True,
        "plan_name": sub.plan.name,
        "kit_name": kit.name,
    }


def consume_credit(empresa_id: int, customer_id: int, service_id: int, appointment_id: int) -> bool:
    """Deduz 1 crédito de um serviço. Retorna True se consumido."""
    from app.models.subscription import SubscriptionCreditBalance, SubscriptionCreditUsage
    sub = get_active_subscription(empresa_id, customer_id)
    if not sub:
        return False
    balance = SubscriptionCreditBalance.query.filter_by(
        empresa_id=empresa_id, subscription_id=sub.id, service_id=service_id,
    ).first()
    if not balance or balance.remaining_credits <= 0:
        return False
    balance.used_credits += 1
    db.session.add(SubscriptionCreditUsage(
        empresa_id=empresa_id,
        subscription_id=sub.id,
        appointment_id=appointment_id,
        service_id=service_id,
    ))
    return True


def consume_credit_kit(empresa_id: int, customer_id: int, kit, appointment_id: int) -> bool:
    """
    Deduz 1 crédito de cada serviço do kit de forma atômica.
    Se algum serviço não tiver crédito, não deduz nenhum (retorna False).
    """
    from app.models.subscription import SubscriptionCreditBalance, SubscriptionCreditUsage
    sub = get_active_subscription(empresa_id, customer_id)
    if not sub:
        return False

    balances = []
    for item in kit.items:
        bal = SubscriptionCreditBalance.query.filter_by(
            empresa_id=empresa_id, subscription_id=sub.id, service_id=item.service_id,
        ).first()
        if not bal or bal.remaining_credits <= 0:
            return False
        balances.append((bal, item.service_id))

    for bal, service_id in balances:
        bal.used_credits += 1
        db.session.add(SubscriptionCreditUsage(
            empresa_id=empresa_id,
            subscription_id=sub.id,
            appointment_id=appointment_id,
            service_id=service_id,
        ))
    return True


def refund_credit(empresa_id: int, appointment_id: int) -> bool:
    """
    Estorna todos os créditos usados por este agendamento (dentro da empresa).
    Suporta kits (múltiplos SubscriptionCreditUsage por appointment_id).
    Retorna True se ao menos um crédito foi estornado.
    """
    from app.models.subscription import SubscriptionCreditUsage, SubscriptionCreditBalance
    usages = SubscriptionCreditUsage.query.filter_by(
        empresa_id=empresa_id, appointment_id=appointment_id,
    ).all()
    if not usages:
        return False
    for usage in usages:
        balance = SubscriptionCreditBalance.query.filter_by(
            empresa_id=empresa_id,
            subscription_id=usage.subscription_id,
            service_id=usage.service_id,
        ).first()
        if balance:
            balance.used_credits = max(0, balance.used_credits - 1)
        db.session.delete(usage)
    return True
