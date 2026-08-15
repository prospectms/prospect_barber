"""Cliente HTTP fino pra API do Asaas (Fase 3).

Payloads seguem exatamente a referência oficial (docs.asaas.com/reference),
sem inferência: create-new-customer, create-new-subscription e
create-subscription-with-credit-card. Nenhuma lógica de negócio aqui (isso
fica em app/upgrade/routes.py e no handler de webhook) — só monta o
request, autentica e traduz erro HTTP em AsaasError.
"""
from dataclasses import dataclass

import requests
from flask import current_app


class AsaasError(Exception):
    """Erro retornado pela API do Asaas (HTTP 4xx/5xx) ou falha de rede."""

    def __init__(self, message: str, status_code: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


@dataclass
class CreditCard:
    holder_name: str
    number: str
    expiry_month: str  # 2 dígitos
    expiry_year: str  # 4 dígitos
    ccv: str


@dataclass
class CreditCardHolderInfo:
    name: str
    email: str
    cpf_cnpj: str
    postal_code: str
    address_number: str
    phone: str
    mobile_phone: str | None = None
    address_complement: str | None = None


def _headers() -> dict:
    api_key = current_app.config["ASAAS_API_KEY"]
    if not api_key:
        raise AsaasError("ASAAS_API_KEY não configurada")
    return {
        "access_token": api_key,
        "Content-Type": "application/json",
        "User-Agent": "ProspectBarber",
    }


def _request(method: str, path: str, json_body: dict) -> dict:
    base_url = current_app.config["ASAAS_API_BASE_URL"]
    try:
        resp = requests.request(method, f"{base_url}{path}", json=json_body, headers=_headers(), timeout=15)
    except requests.RequestException as exc:
        raise AsaasError(f"falha de rede ao chamar Asaas: {exc}") from exc

    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        erro = (data.get("errors") or [{}])[0].get("description", resp.text)
        raise AsaasError(f"Asaas retornou {resp.status_code}: {erro}", status_code=resp.status_code, payload=data)
    return data


def _get(path: str, params: dict) -> dict:
    base_url = current_app.config["ASAAS_API_BASE_URL"]
    try:
        resp = requests.get(f"{base_url}{path}", params=params, headers=_headers(), timeout=15)
    except requests.RequestException as exc:
        raise AsaasError(f"falha de rede ao chamar Asaas: {exc}") from exc

    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        erro = (data.get("errors") or [{}])[0].get("description", resp.text)
        raise AsaasError(f"Asaas retornou {resp.status_code}: {erro}", status_code=resp.status_code, payload=data)
    return data


def create_customer(*, name: str, cpf_cnpj: str, email: str, mobile_phone: str | None = None,
                     external_reference: str | None = None) -> dict:
    """POST /v3/customers — retorna o dict de resposta (id em data['id'], ex. 'cus_000000001')."""
    body = {"name": name, "cpfCnpj": cpf_cnpj, "email": email}
    if mobile_phone:
        body["mobilePhone"] = mobile_phone
    if external_reference:
        body["externalReference"] = external_reference
    return _request("POST", "/customers", body)


def create_subscription_pix(*, customer_id: str, value: float, cycle: str, next_due_date: str,
                             description: str | None = None, external_reference: str | None = None) -> dict:
    """POST /v3/subscriptions com billingType=PIX. cycle: WEEKLY/MONTHLY/.../YEARLY
    (usamos só MONTHLY/YEARLY). next_due_date no formato 'YYYY-MM-DD'."""
    body = {
        "customer": customer_id,
        "billingType": "PIX",
        "value": value,
        "nextDueDate": next_due_date,
        "cycle": cycle,
    }
    if description:
        body["description"] = description
    if external_reference:
        body["externalReference"] = external_reference
    return _request("POST", "/subscriptions", body)


def get_first_payment_invoice_url(subscription_id: str) -> str | None:
    """GET /v3/payments?subscription=<id> — link real de pagamento
    (invoiceUrl, mostra Pix/Boleto conforme o billingType) da primeira
    cobrança gerada junto com a assinatura. A resposta de criação da
    assinatura em si NUNCA traz QR code/link nenhum -- confirmado contra o
    sandbox real (smoke test Fase 3, 2026-08-12); sem isso o cliente não
    tem como pagar.

    Só é chamada uma vez, logo após criar a assinatura (iniciar_checkout),
    quando existe exatamente 1 cobrança pra essa assinatura -- por isso
    pega data[0] sem se preocupar em ordenar. Retorna None se a Asaas
    ainda não tiver gerado nenhuma cobrança (não deveria acontecer -- a
    primeira cobrança é criada no mesmo request que cria a assinatura)."""
    data = _get("/payments", {"subscription": subscription_id, "limit": 1})
    pagamentos = data.get("data") or []
    if not pagamentos:
        return None
    return pagamentos[0].get("invoiceUrl")


def create_subscription_credit_card(*, customer_id: str, value: float, cycle: str, next_due_date: str,
                                     credit_card: CreditCard, holder_info: CreditCardHolderInfo,
                                     remote_ip: str, description: str | None = None,
                                     external_reference: str | None = None) -> dict:
    """POST /v3/subscriptions com billingType=CREDIT_CARD — payload exato da
    referência oficial 'create-subscription-with-credit-card'. remote_ip é
    obrigatório (IP do titular do cartão, request.remote_addr do checkout)."""
    body = {
        "customer": customer_id,
        "billingType": "CREDIT_CARD",
        "value": value,
        "nextDueDate": next_due_date,
        "cycle": cycle,
        "remoteIp": remote_ip,
        "creditCard": {
            "holderName": credit_card.holder_name,
            "number": credit_card.number,
            "expiryMonth": credit_card.expiry_month,
            "expiryYear": credit_card.expiry_year,
            "ccv": credit_card.ccv,
        },
        "creditCardHolderInfo": {
            "name": holder_info.name,
            "email": holder_info.email,
            "cpfCnpj": holder_info.cpf_cnpj,
            "postalCode": holder_info.postal_code,
            "addressNumber": holder_info.address_number,
            "phone": holder_info.phone,
        },
    }
    if holder_info.mobile_phone:
        body["creditCardHolderInfo"]["mobilePhone"] = holder_info.mobile_phone
    if holder_info.address_complement:
        body["creditCardHolderInfo"]["addressComplement"] = holder_info.address_complement
    if description:
        body["description"] = description
    if external_reference:
        body["externalReference"] = external_reference
    return _request("POST", "/subscriptions", body)
