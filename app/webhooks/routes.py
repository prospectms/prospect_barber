"""Endpoint público (sem login) que recebe notificações da Asaas.

Regra inegociável (combinado da Fase 3): nenhum payload é processado sem
validar o header asaas-access-token contra o segredo configurado
manualmente no painel Asaas -- qualquer requisição sem esse header batendo
é rejeitada com 401 antes de tocar em qualquer dado.
"""
from flask import Blueprint, current_app, jsonify, request

from app.billing.service import aplicar_evento_webhook
from app.extensions import csrf

webhooks_bp = Blueprint("webhooks", __name__)
csrf.exempt(webhooks_bp)


@webhooks_bp.route("/asaas", methods=["POST"])
def asaas():
    token_esperado = current_app.config["ASAAS_WEBHOOK_TOKEN"]
    token_recebido = request.headers.get("asaas-access-token")
    if not token_esperado or token_recebido != token_esperado:
        return jsonify({"error": "token inválido"}), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "payload inválido"}), 400

    resultado = aplicar_evento_webhook(payload)
    return jsonify({"status": resultado}), 200
