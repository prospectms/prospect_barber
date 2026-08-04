from flask import Blueprint, render_template, redirect, url_for, flash, request, session, g
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.empresa import Empresa
from app.models.unidade import Unidade
from app.models.usuario import Usuario
from app.models.usuario_unidade import UsuarioUnidade
from app.models.profissional import Profissional
from app.auth.forms import (
    LoginForm, SelecionarEmpresaForm, SelecionarUnidadeForm,
    CadastroEmpresaForm, RegisterUserForm, EditUserForm,
    AdminResetPasswordForm, ProfileForm, ChangePasswordForm,
)
from app.utils.decorators import requer_papel
from app.utils.limites import requer_limite
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


# ════════════════════════════════════════════════════════
#  CADASTRO DE EMPRESA (público — self-signup)
# ════════════════════════════════════════════════════════

def _unique_empresa_slug(nome: str) -> str:
    from app.models.empresa import slugify
    base = slugify(nome) or "empresa"
    slug = base
    i = 2
    while Empresa.query.filter_by(slug=slug).first():
        slug = f"{base}-{i}"
        i += 1
    return slug


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = CadastroEmpresaForm()

    if form.validate_on_submit():
        try:
            empresa = Empresa(
                nome=form.empresa_nome.data.strip(),
                documento=(form.empresa_documento.data or "").strip() or None,
                email=form.dono_email.data.strip().lower(),
                telefone=(form.empresa_telefone.data or "").strip() or None,
                slug=_unique_empresa_slug(form.empresa_nome.data),
                plano_id=1,
                status_assinatura="ativa",
            )
            db.session.add(empresa)
            db.session.flush()  # obtém empresa.id

            unidade = Unidade(
                empresa_id=empresa.id,
                nome=form.unidade_nome.data.strip(),
                slug=form.unidade_slug.data,  # já normalizado/validado no form
                endereco=(form.unidade_endereco.data or "").strip() or None,
                telefone=(form.unidade_telefone.data or "").strip() or None,
                ativa=True,
            )
            db.session.add(unidade)

            dono = Usuario(
                empresa_id=empresa.id,
                nome=form.dono_nome.data.strip(),
                email=form.dono_email.data.strip().lower(),
                papel="dono",
                ativo=True,
            )
            dono.set_password(form.dono_password.data)
            db.session.add(dono)

            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao criar sua empresa. Tente novamente.", "danger")
            return render_template("auth/cadastro.html", form=form)

        dono.record_login()
        db.session.commit()
        login_user(dono)
        session["unidade_ativa_id"] = unidade.id

        flash(f"Empresa '{empresa.nome}' criada com sucesso! Bem-vindo, {dono.nome}.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("auth/cadastro.html", form=form)


# ════════════════════════════════════════════════════════
#  GESTÃO DE USUÁRIOS — dono/gerente da empresa
# ════════════════════════════════════════════════════════

@auth_bp.route("/users")
@login_required
@requer_papel("dono", "gerente")
def users():
    # Usuario.query já vem filtrado por g.empresa_id (TenantMixin) — nenhuma
    # rota de gestão de usuários enxerga contas de outra empresa.
    all_users = Usuario.query.order_by(Usuario.papel, Usuario.nome).all()
    return render_template("auth/users/index.html", users=all_users)


def _unidades_choices():
    return [
        (u.id, u.nome)
        for u in Unidade.query.filter_by(ativa=True).order_by(Unidade.nome).all()
    ]


@auth_bp.route("/users/new", methods=["GET", "POST"])
@login_required
@requer_papel("dono", "gerente")
@requer_limite("usuario")
def new_user():
    form = RegisterUserForm()
    form.unidades_ids.choices = _unidades_choices()

    if form.validate_on_submit():
        if form.criar_perfil_profissional.data and not form.unidades_ids.data:
            flash("Selecione ao menos uma unidade para o perfil de profissional.", "danger")
            return render_template("auth/users/form.html", form=form, action="new")

        user = Usuario(
            empresa_id=g.empresa_id,
            nome=form.nome.data.strip(),
            email=form.email.data.strip().lower(),
            papel=form.papel.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # obtém o ID antes do commit

        if form.papel.data == "funcionario":
            for unidade_id in form.unidades_ids.data:
                db.session.add(UsuarioUnidade(
                    empresa_id=g.empresa_id, usuario_id=user.id, unidade_id=unidade_id,
                ))

        if form.criar_perfil_profissional.data:
            profissional = Profissional(
                empresa_id=g.empresa_id,
                unidade_id=form.unidades_ids.data[0],
                usuario_id=user.id,
                name=form.nome.data.strip(),
                phone=(form.phone.data or "").strip() or None,
                specialty=(form.specialty.data or "").strip() or None,
            )
            db.session.add(profissional)

        db.session.commit()
        flash(f"Usuário '{user.nome}' criado com sucesso!", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/users/form.html", form=form, action="new")


@auth_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@requer_papel("dono", "gerente")
def edit_user(user_id: int):
    user = Usuario.query.get_or_404(user_id)
    form = EditUserForm(usuario_id=user_id)
    form.unidades_ids.choices = _unidades_choices()

    if request.method == "GET":
        form.nome.data = user.nome
        form.email.data = user.email
        form.papel.data = user.papel
        form.ativo.data = user.ativo
        form.unidades_ids.data = [
            uu.unidade_id for uu in UsuarioUnidade.query.filter_by(usuario_id=user.id).all()
        ]

    if form.validate_on_submit():
        user.nome = form.nome.data.strip()
        user.email = form.email.data.strip().lower()
        user.papel = form.papel.data
        user.ativo = form.ativo.data

        existentes = UsuarioUnidade.query.filter_by(usuario_id=user.id).all()
        existentes_ids = {uu.unidade_id for uu in existentes}
        novos_ids = set(form.unidades_ids.data) if form.papel.data == "funcionario" else set()

        for uu in existentes:
            if uu.unidade_id not in novos_ids:
                db.session.delete(uu)
        for unidade_id in novos_ids - existentes_ids:
            db.session.add(UsuarioUnidade(
                empresa_id=g.empresa_id, usuario_id=user.id, unidade_id=unidade_id,
            ))

        db.session.commit()
        flash(f"Usuário '{user.nome}' atualizado!", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/users/form.html", form=form, action="edit", user=user)


@auth_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
@login_required
@requer_papel("dono", "gerente")
def toggle_user(user_id: int):
    user = Usuario.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Você não pode desativar a própria conta.", "warning")
        return redirect(url_for("auth.users"))

    if user.papel == "dono" and user.ativo:
        donos_ativos = Usuario.query.filter_by(papel="dono", ativo=True).count()
        if donos_ativos <= 1:
            flash("Não é possível desativar o único dono ativo da empresa.", "danger")
            return redirect(url_for("auth.users"))

    user.ativo = not user.ativo
    db.session.commit()
    status = "ativado" if user.ativo else "desativado"
    flash(f"Usuário '{user.nome}' {status}.", "info")
    return redirect(url_for("auth.users"))


@auth_bp.route("/users/<int:user_id>/reset-password", methods=["GET", "POST"])
@login_required
@requer_papel("dono", "gerente")
def reset_password(user_id: int):
    user = Usuario.query.get_or_404(user_id)
    form = AdminResetPasswordForm()

    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        user.reset_login_attempts()
        db.session.commit()
        flash(f"Senha de '{user.nome}' redefinida com sucesso!", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/users/reset_password.html", form=form, user=user)


@auth_bp.route("/users/<int:user_id>/unlock", methods=["POST"])
@login_required
@requer_papel("dono", "gerente")
def unlock_user(user_id: int):
    user = Usuario.query.get_or_404(user_id)
    user.reset_login_attempts()
    db.session.commit()
    flash(f"Conta de '{user.nome}' desbloqueada.", "success")
    return redirect(url_for("auth.users"))


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@requer_papel("dono", "gerente")
def delete_user(user_id: int):
    user = Usuario.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Você não pode excluir a própria conta.", "danger")
        return redirect(url_for("auth.users"))

    if user.papel == "dono":
        donos_ativos = Usuario.query.filter_by(papel="dono", ativo=True).count()
        if donos_ativos <= 1:
            flash("Não é possível remover o único dono da empresa.", "danger")
            return redirect(url_for("auth.users"))

    if user.profissional and user.profissional.total_appointments > 0:
        flash(
            f"'{user.nome}' possui agendamentos vinculados como profissional e não pode ser "
            "excluído. Desative a conta em vez de excluir para preservar o histórico.",
            "warning",
        )
        return redirect(url_for("auth.users"))

    nome = user.nome
    UsuarioUnidade.query.filter_by(usuario_id=user.id).delete()

    if user.profissional:
        from app.utils.helpers import delete_upload
        if user.profissional.photo:
            delete_upload(user.profissional.photo)
        db.session.delete(user.profissional)
        db.session.flush()

    db.session.delete(user)
    db.session.commit()
    flash(f"Usuário '{nome}' removido.", "info")
    return redirect(url_for("auth.users"))


# ════════════════════════════════════════════════════════
#  AUTOGESTÃO DE CONTA — qualquer usuário logado
# ════════════════════════════════════════════════════════

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(usuario_id=current_user.id)

    if request.method == "GET":
        form.nome.data = current_user.nome
        form.email.data = current_user.email
        if current_user.profissional:
            prof = current_user.profissional
            form.phone.data = prof.phone
            form.specialty.data = prof.specialty
            form.bio.data = prof.bio

    if form.validate_on_submit():
        current_user.nome = form.nome.data.strip()
        current_user.email = form.email.data.strip().lower()

        if current_user.profissional:
            prof = current_user.profissional
            prof.name = form.nome.data.strip()
            prof.phone = form.phone.data.strip() if form.phone.data else prof.phone
            prof.specialty = form.specialty.data.strip() if form.specialty.data else prof.specialty
            prof.bio = form.bio.data.strip() if form.bio.data else prof.bio

        db.session.commit()
        flash("Perfil atualizado com sucesso!", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", form=form)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Senha atual incorreta.", "danger")
            return render_template("auth/change_password.html", form=form)
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("Senha alterada com sucesso!", "success")
        return redirect(url_for("auth.profile"))
    return render_template("auth/change_password.html", form=form)
