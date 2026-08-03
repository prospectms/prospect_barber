"""
Decorators de autorização multi-tenant (Fase 1-A).

Substituem admin_required/barber_required/own_barber_or_admin da versão
mono-tenant. Nenhum deles filtra dado — isso é papel do TenantMixin
(app/models/tenant.py). Eles só decidem se a rota pode ser acessada.
"""
from functools import wraps
from flask import flash, redirect, url_for, g, abort
from flask_login import current_user


def requer_empresa(f):
    """Garante login + empresa resolvida em g.empresa_id. Base de qualquer
    rota de tenant — normalmente já implícito via before_request, mas serve
    de barreira explícita para rotas que não podem rodar sem empresa (ex.:
    chamadas via API/CLI futuras que pulem o before_request padrão)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not getattr(g, "empresa_id", None):
            flash("Sessão sem empresa associada. Faça login novamente.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def requer_papel(*papeis: str):
    """Permite current_user.papel in papeis. Superadmin sempre passa
    (ele opera fora da hierarquia dono/gerente/funcionario de uma empresa
    normal). Uso: @requer_papel('dono', 'gerente')."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.is_superadmin:
                return f(*args, **kwargs)
            if current_user.papel not in papeis:
                flash("Você não tem permissão para acessar esta página.", "danger")
                return redirect(url_for("dashboard.index"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def requer_unidade(f):
    """Garante que existe uma unidade ativa selecionada (g.unidade_id) e que
    o usuário logado tem acesso a ela:
      - dono/gerente: qualquer unidade da própria empresa
      - funcionario: só unidades listadas em UsuarioUnidade
    A checagem de vínculo em si acontece no seletor de unidade (auth.routes
    set_unidade_ativa), que é o único lugar que escreve g/session; aqui só
    validamos que uma unidade válida está de fato selecionada.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not getattr(g, "unidade_id", None):
            flash("Selecione uma unidade para continuar.", "warning")
            return redirect(url_for("auth.selecionar_unidade"))
        return f(*args, **kwargs)
    return decorated


def requer_profissional_proprio(profissional_id_param: str = "barber_id"):
    """Permite dono/gerente (acesso total) ou o próprio funcionário cujo
    Profissional.usuario_id é o usuário logado. Substitui own_barber_or_admin."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.is_superadmin or current_user.pode_gerenciar:
                return f(*args, **kwargs)
            profissional_id = kwargs.get(profissional_id_param)
            profissional = current_user.profissional
            if profissional and profissional.id == profissional_id:
                return f(*args, **kwargs)
            flash("Você só pode acessar sua própria área.", "danger")
            return redirect(url_for("dashboard.index"))
        return decorated
    return decorator


def requer_superadmin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_superadmin:
            abort(404)
        return f(*args, **kwargs)
    return decorated


def active_required(f):
    """Garante que o usuário autenticado ainda está ativo (camada extra de segurança)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated and not current_user.ativo:
            from flask_login import logout_user
            logout_user()
            flash("Sua conta foi desativada. Contate o administrador.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated
