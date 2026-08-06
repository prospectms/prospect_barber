from datetime import datetime, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, g, request
from flask_login import login_required

from app.billing.service import CheckoutError, DIAS_INADIMPLENCIA_PARA_DOWNGRADE, iniciar_checkout
from app.models.assinatura import Assinatura
from app.models.empresa import Empresa
from app.models.plano import Plano
from app.upgrade.forms import CheckoutForm
from app.utils import asaas_client
from app.utils.decorators import requer_papel

upgrade_bp = Blueprint("upgrade", __name__)


@upgrade_bp.route("/")
@login_required
@requer_papel("dono", "gerente")
def index():
    empresa = Empresa.query.get(g.empresa_id)
    planos = Plano.query.order_by(Plano.preco_mensal).all()
    return render_template("upgrade/index.html", empresa=empresa, planos=planos)


@upgrade_bp.route("/checkout/<int:plano_id>", methods=["GET", "POST"])
@login_required
@requer_papel("dono")
def checkout(plano_id: int):
    plano = Plano.query.get_or_404(plano_id)
    if plano.nome == "free":
        flash("O plano Free não precisa de pagamento.", "info")
        return redirect(url_for("upgrade.index"))

    empresa = Empresa.query.get(g.empresa_id)
    form = CheckoutForm(
        documento=empresa.documento, email=empresa.email, telefone=empresa.telefone,
    )

    if form.validate_on_submit():
        erros_cartao = form.validate_campos_cartao()
        for erro in erros_cartao:
            flash(erro, "danger")

        if not erros_cartao:
            dados_cartao = dados_titular = None
            if form.forma_pagamento.data == "cartao":
                telefone = form.telefone.data.strip()
                dados_cartao = asaas_client.CreditCard(
                    holder_name=form.card_holder_name.data.strip(),
                    number=form.card_number.data.strip(),
                    expiry_month=form.card_expiry_month.data.strip(),
                    expiry_year=form.card_expiry_year.data.strip(),
                    ccv=form.card_ccv.data.strip(),
                )
                dados_titular = asaas_client.CreditCardHolderInfo(
                    name=empresa.nome,
                    email=form.email.data.strip(),
                    cpf_cnpj=form.documento.data.strip(),
                    postal_code=form.card_postal_code.data.strip(),
                    address_number=form.card_address_number.data.strip(),
                    phone=telefone,
                    mobile_phone=telefone,
                )

            try:
                iniciar_checkout(
                    empresa=empresa,
                    plano=plano,
                    periodicidade=form.periodicidade.data,
                    forma_pagamento=form.forma_pagamento.data,
                    documento=form.documento.data.strip(),
                    email=form.email.data.strip(),
                    telefone=(form.telefone.data or "").strip() or None,
                    remote_ip=request.remote_addr,
                    dados_cartao=dados_cartao,
                    dados_titular_cartao=dados_titular,
                )
            except (CheckoutError, asaas_client.AsaasError) as exc:
                flash(f"Não foi possível iniciar a assinatura: {exc}", "danger")
            else:
                flash(
                    "Assinatura criada! Assim que o pagamento for confirmado pela "
                    "operadora, seu plano será liberado automaticamente.",
                    "success",
                )
                return redirect(url_for("upgrade.status"))

    return render_template("upgrade/checkout.html", plano=plano, form=form)


@upgrade_bp.route("/status")
@login_required
@requer_papel("dono", "gerente")
def status():
    empresa = Empresa.query.get(g.empresa_id)
    assinatura = (
        Assinatura.query.filter_by(empresa_id=g.empresa_id)
        .order_by(Assinatura.criado_em.desc())
        .first()
    )

    dias_restantes = None
    if assinatura is not None and assinatura.status == "inadimplente" and assinatura.inadimplente_desde:
        dias_passados = (datetime.now(timezone.utc).replace(tzinfo=None) - assinatura.inadimplente_desde).days
        dias_restantes = max(0, DIAS_INADIMPLENCIA_PARA_DOWNGRADE - dias_passados)

    return render_template(
        "upgrade/status.html", empresa=empresa, assinatura=assinatura, dias_restantes=dias_restantes,
    )
