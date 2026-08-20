"""Endpoints internos (sem login de usuário) disparados por infraestrutura
fora do processo da aplicação -- cron do SO, não navegador.

Substitui o job diário do APScheduler (Fase 3): sob Gunicorn com
preload_app=True e múltiplos workers, a thread do BackgroundScheduler é
criada no processo master ANTES do fork; fork() no Linux só duplica a
thread chamadora, então as threads dos workers (filhos) nunca herdam essa
thread rodando de verdade -- se o job dispara em algum lugar, é incerto
onde e quando. Confirmado como cenário real (não hipotético) no deploy da
VPS em 2026-08-20: 6 processos gunicorn (1 master + 5 workers) rodando de
verdade. Cron do SO chamando este endpoint roda fora do processo do
Gunicorn inteiramente -- funciona igual não importa a topologia (1
worker, N workers, Passenger no Hostinger, dev local).

Mesma regra do webhook da Asaas: nenhuma requisição sem o token batendo é
processada.
"""
from flask import Blueprint, current_app, jsonify, request

from app.billing.service import downgrade_inadimplentes
from app.extensions import csrf

internal_bp = Blueprint("internal", __name__)
csrf.exempt(internal_bp)


@internal_bp.route("/downgrade-inadimplentes", methods=["POST"])
def downgrade_inadimplentes_view():
    token_esperado = current_app.config["INTERNAL_JOB_TOKEN"]
    token_recebido = request.headers.get("X-Internal-Token")
    if not token_esperado or token_recebido != token_esperado:
        return jsonify({"error": "token inválido"}), 401

    rebaixadas = downgrade_inadimplentes()
    return jsonify({"rebaixadas": rebaixadas}), 200
