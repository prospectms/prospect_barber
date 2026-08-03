from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.usuario import Usuario
from app.auth.forms import LoginForm, SelecionarEmpresaForm, SelecionarUnidadeForm
from app.utils.tenant_context import unidades_do_usuario, usuario_pode_acessar_unidade

auth_bp = Blueprint("auth", __name__)

_LOGIN_PENDING_KEY = "login_pending_usuario_ids"


# ── Login ─────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    lock_info = None  # {minutes: int} quando a única conta candidata está bloqueada

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        # g.empresa_id ainda não existe nesta request (login é o que o define) —
        # o filtro automático de tenant não interfere aqui, a busca é global
        # de propósito: o mesmo e-mail pode existir em empresas diferentes.
        candidates = Usuario.query.filter(
            db.func.lower(Usuario.email) == email
        ).all()

        if not candidates:
            flash("E-mail ou senha inválidos.", "danger")
            return render_template("auth/login.html", form=form)

        matched = [u for u in candidates if u.check_password(form.password.data)]

        if not matched:
            for u in candidates:
                if not u.is_locked:
                    u.handle_failed_login()
            db.session.commit()
            flash("E-mail ou senha inválidos.", "danger")
            return render_template("auth/login.html", form=form)

        if len(matched) > 1:
            # Mesmo e-mail + mesma senha cadastrados em empresas diferentes
            # (ex: a mesma pessoa é dona de duas barbearias). Guarda só os
            # IDs que já provaram conhecer a senha — a escolha final ainda
            # passa pelas mesmas checagens de bloqueio/conta ativa.
            session[_LOGIN_PENDING_KEY] = [u.id for u in matched]
            return redirect(url_for("auth.selecionar_empresa"))

        user = matched[0]
        return _finalizar_login(user, form)

    return render_template("auth/login.html", form=form, lock_info=lock_info)


@auth_bp.route("/login/empresa", methods=["GET", "POST"])
def selecionar_empresa():
    pending_ids = session.get(_LOGIN_PENDING_KEY)
    if not pending_ids:
        return redirect(url_for("auth.login"))

    # g.empresa_id é None aqui (pré-login) — busca global mesmo, restrita à
    # lista fechada de IDs que a etapa anterior já validou por senha.
    usuarios = Usuario.query.filter(Usuario.id.in_(pending_ids)).all()
    if not usuarios:
        session.pop(_LOGIN_PENDING_KEY, None)
        return redirect(url_for("auth.login"))

    form = SelecionarEmpresaForm()
    form.usuario_id.choices = [
        (u.id, f"{u.empresa.nome} — {u.papel_label}") for u in usuarios
    ]

    if form.validate_on_submit():
        if form.usuario_id.data not in pending_ids:
            flash("Seleção inválida.", "danger")
            return redirect(url_for("auth.login"))
        user = next(u for u in usuarios if u.id == form.usuario_id.data)
        session.pop(_LOGIN_PENDING_KEY, None)
        return _finalizar_login(user)

    return render_template("auth/selecionar_empresa.html", form=form)


def _finalizar_login(user: Usuario, form: LoginForm | None = None):
    """Checagens finais (bloqueio/conta ativa) + login_user + resolução de
    unidade ativa. Compartilhado entre login direto e pós-desambiguação."""
    if user.is_locked:
        flash(
            f"Conta bloqueada. Tente novamente em {user.lock_remaining_minutes} minuto(s).",
            "danger",
        )
        return redirect(url_for("auth.login"))

    if not user.ativo:
        flash("Sua conta foi desativada. Contate o administrador.", "warning")
        return redirect(url_for("auth.login"))

    user.record_login()
    db.session.commit()
    remember = form.remember_me.data if form is not None else False
    login_user(user, remember=remember)

    flash(f"Bem-vindo de volta, {user.display_name}!", "success")

    # Auto-seleciona unidade quando só existe uma opção — evita um clique
    # extra no caso mais comum (empresa/funcionário de unidade única).
    unidades = unidades_do_usuario(user)
    if len(unidades) == 1:
        session["unidade_ativa_id"] = unidades[0].id
    else:
        session.pop("unidade_ativa_id", None)

    next_page = request.args.get("next")
    if next_page:
        from urllib.parse import urlparse
        parsed = urlparse(next_page)
        if parsed.netloc or parsed.scheme:
            next_page = None

    if len(unidades) > 1 and not next_page:
        return redirect(url_for("auth.selecionar_unidade"))

    return redirect(next_page or url_for("dashboard.index"))


# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("unidade_ativa_id", None)
    session.pop(_LOGIN_PENDING_KEY, None)
    flash("Sessão encerrada com sucesso.", "info")
    return redirect(url_for("auth.login"))


# ── Seletor de unidade ativa ───────────────────────────────────────────────────
@auth_bp.route("/unidade", methods=["GET", "POST"])
@login_required
def selecionar_unidade():
    unidades = unidades_do_usuario(current_user)

    if not unidades:
        flash(
            "Nenhuma unidade disponível para o seu usuário. Contate o dono/gerente da empresa.",
            "warning",
        )
        return render_template("auth/selecionar_unidade.html", form=None, unidades=[])

    form = SelecionarUnidadeForm()
    form.unidade_id.choices = [(u.id, u.nome) for u in unidades]

    if form.validate_on_submit():
        if not usuario_pode_acessar_unidade(current_user, form.unidade_id.data):
            flash("Você não tem acesso a essa unidade.", "danger")
            return redirect(url_for("auth.selecionar_unidade"))
        session["unidade_ativa_id"] = form.unidade_id.data
        flash("Unidade ativa atualizada.", "success")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("dashboard.index"))

    if request.method == "GET" and len(unidades) == 1:
        form.unidade_id.data = unidades[0].id

    return render_template("auth/selecionar_unidade.html", form=form, unidades=unidades)
