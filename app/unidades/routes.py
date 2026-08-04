from flask import Blueprint, render_template, redirect, url_for, flash, g
from flask_login import login_required

from app.extensions import db
from app.models.unidade import Unidade
from app.unidades.forms import UnidadeForm
from app.utils.decorators import requer_papel
from app.utils.limites import requer_limite

unidades_bp = Blueprint("unidades", __name__)


# ── Criar ─────────────────────────────────────────────────────────────────────
@unidades_bp.route("/new", methods=["GET", "POST"])
@login_required
@requer_papel("dono")
@requer_limite("unidade")
def new():
    form = UnidadeForm()

    if form.validate_on_submit():
        unidade = Unidade(
            empresa_id=g.empresa_id,
            nome=form.nome.data.strip(),
            slug=form.slug.data,  # já normalizado/validado no form
            endereco=(form.endereco.data or "").strip() or None,
            telefone=(form.telefone.data or "").strip() or None,
            ativa=True,
        )
        db.session.add(unidade)
        db.session.commit()
        flash(f"Unidade '{unidade.nome}' criada com sucesso!", "success")
        return redirect(url_for("auth.selecionar_unidade"))

    return render_template("unidades/form.html", form=form)
