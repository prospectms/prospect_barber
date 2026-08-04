from flask import Blueprint, render_template, redirect, url_for, flash, g
from flask_login import login_required

from app.models.empresa import Empresa
from app.models.plano import Plano
from app.utils.decorators import requer_papel

upgrade_bp = Blueprint("upgrade", __name__)


@upgrade_bp.route("/")
@login_required
@requer_papel("dono", "gerente")
def index():
    empresa = Empresa.query.get(g.empresa_id)
    planos = Plano.query.order_by(Plano.preco_mensal).all()
    return render_template("upgrade/index.html", empresa=empresa, planos=planos)


@upgrade_bp.route("/checkout/<int:plano_id>", methods=["POST"])
@login_required
@requer_papel("dono")
def checkout(plano_id: int):
    """STUB — nenhuma integração de gateway de pagamento nesta fase (Fase 3).
    Não muda plano_id/periodicidade/preco_congelado da empresa; só informa
    que o fluxo real ainda não existe. Existe como endpoint desde já pra o
    botão "Assinar" da tela de upgrade ter pra onde apontar."""
    plano = Plano.query.get_or_404(plano_id)
    flash(
        f"Assinatura do plano '{plano.nome}' em breve — pagamento online "
        "ainda não está disponível. Fale com o time Prospect pra migrar seu plano.",
        "info",
    )
    return redirect(url_for("upgrade.index"))
