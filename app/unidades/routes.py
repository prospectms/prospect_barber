from flask import Blueprint, render_template, redirect, url_for, flash, g, request
from flask_login import login_required

from app.extensions import db
from app.models.unidade import Unidade
from app.unidades.forms import UnidadeForm
from app.utils.decorators import requer_papel
from app.utils.limites import requer_limite

unidades_bp = Blueprint("unidades", __name__)


# ── Listar ────────────────────────────────────────────────────────────────────
@unidades_bp.route("/")
@login_required
@requer_papel("dono")
def index():
    # Unidade.query já vem filtrado por g.empresa_id (TenantMixin) — nenhuma
    # rota de gestão de unidades enxerga unidade de outra empresa.
    unidades = Unidade.query.order_by(Unidade.nome).all()
    return render_template("unidades/index.html", unidades=unidades)


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

    return render_template("unidades/form.html", form=form, action="new")


# ── Editar ────────────────────────────────────────────────────────────────────
@unidades_bp.route("/<int:unidade_id>/edit", methods=["GET", "POST"])
@login_required
@requer_papel("dono")
def edit(unidade_id: int):
    unidade = Unidade.query.get_or_404(unidade_id)
    form = UnidadeForm(unidade_id=unidade_id)

    if request.method == "GET":
        form.nome.data = unidade.nome
        form.slug.data = unidade.slug
        form.endereco.data = unidade.endereco
        form.telefone.data = unidade.telefone

    if form.validate_on_submit():
        unidade.nome = form.nome.data.strip()
        unidade.slug = form.slug.data
        unidade.endereco = (form.endereco.data or "").strip() or None
        unidade.telefone = (form.telefone.data or "").strip() or None
        db.session.commit()
        flash(f"Unidade '{unidade.nome}' atualizada com sucesso!", "success")
        return redirect(url_for("unidades.index"))

    return render_template("unidades/form.html", form=form, action="edit", unidade=unidade)


# ── Ativar / Desativar ───────────────────────────────────────────────────────
@unidades_bp.route("/<int:unidade_id>/toggle", methods=["POST"])
@login_required
@requer_papel("dono")
def toggle(unidade_id: int):
    unidade = Unidade.query.get_or_404(unidade_id)

    if unidade.ativa:
        outras_ativas = Unidade.query.filter(
            Unidade.id != unidade.id, Unidade.ativa.is_(True),
        ).count()
        if outras_ativas == 0:
            flash(
                "Não é possível desativar a única unidade ativa da empresa. "
                "Ative outra unidade antes.",
                "warning",
            )
            return redirect(url_for("unidades.index"))

    unidade.ativa = not unidade.ativa
    db.session.commit()
    status = "ativada" if unidade.ativa else "desativada"
    flash(f"Unidade '{unidade.nome}' {status}.", "info")
    return redirect(url_for("unidades.index"))


# ── Excluir ───────────────────────────────────────────────────────────────────
def _dependencias_unidade(unidade_id: int) -> list[str]:
    """Mesmo padrão de barbers/services: excluir só é permitido sem
    histórico/vínculo real, senão orienta a desativar em vez de excluir.
    Unidade tem mais tabelas dependentes que Profissional/Servico (todas
    com FK RESTRICT — sem isso o DELETE quebraria com erro cru de
    integridade em vez de uma mensagem clara)."""
    from app.models.profissional import Profissional
    from app.models.servico import Servico
    from app.models.agendamento import Agendamento
    from app.models.usuario_unidade import UsuarioUnidade
    from app.models.cliente import Cliente

    checks = [
        ("agendamento(s)", Agendamento.query.filter_by(unidade_id=unidade_id).count()),
        ("profissional(is)", Profissional.query.filter_by(unidade_id=unidade_id).count()),
        ("serviço(s)", Servico.query.filter_by(unidade_id=unidade_id).count()),
        ("usuário(s) vinculado(s)", UsuarioUnidade.query.filter_by(unidade_id=unidade_id).count()),
        ("cliente(s) de origem", Cliente.query.filter_by(unidade_origem_id=unidade_id).count()),
    ]
    return [f"{count} {label}" for label, count in checks if count > 0]


@unidades_bp.route("/<int:unidade_id>/delete", methods=["POST"])
@login_required
@requer_papel("dono")
def delete(unidade_id: int):
    unidade = Unidade.query.get_or_404(unidade_id)

    total_unidades = Unidade.query.count()
    if total_unidades <= 1:
        flash("Não é possível excluir a única unidade da empresa.", "warning")
        return redirect(url_for("unidades.index"))

    if unidade.ativa:
        outras_ativas = Unidade.query.filter(
            Unidade.id != unidade.id, Unidade.ativa.is_(True),
        ).count()
        if outras_ativas == 0:
            flash(
                "Não é possível excluir a única unidade ativa da empresa. "
                "Ative outra unidade antes.",
                "warning",
            )
            return redirect(url_for("unidades.index"))

    dependencias = _dependencias_unidade(unidade_id)
    if dependencias:
        flash(
            f"'{unidade.nome}' possui {', '.join(dependencias)} vinculado(s) e não pode ser "
            "excluída. Desative-a em vez de excluir para preservar o histórico.",
            "warning",
        )
        return redirect(url_for("unidades.index"))

    nome = unidade.nome
    db.session.delete(unidade)
    db.session.commit()
    flash(f"Unidade '{nome}' excluída.", "info")
    return redirect(url_for("unidades.index"))
