"""Central de checagem de limites/módulos de plano (Fase 2).

`pode_criar()` é a ÚNICA função que decide se uma empresa pode criar mais
um recurso (Unidade/Usuario/Servico) — nenhuma rota deve contar/comparar
isso por conta própria. Sempre recebe `empresa_id` explícito e filtra
explicitamente por ele, nunca depende do filtro automático de tenant
(TenantMixin, ver app/models/tenant.py): Unidade não tem UnidadeMixin
(não pertence a si mesma) e Usuario/Servico têm TenantMixin, mas a
contagem aqui precisa valer mesmo fora do request autenticado da própria
empresa (ex.: superadmin avaliando outra empresa) — filtro implícito via
`g.empresa_id` não cobre esse caso.

A contagem é sempre em nível de EMPRESA inteira, somando entre todas as
unidades — bate com como os planos definem limite (não existe "limite de
serviço por unidade" nesta fase). Não confundir com o antigo
`Servico.query.filter_by(unidade_id=...)` usado nas telas de listagem.
"""
from functools import wraps

from flask import flash, redirect, url_for, g
from flask_login import current_user

from app.models.empresa import Empresa
from app.models.unidade import Unidade
from app.models.usuario import Usuario
from app.models.servico import Servico

_CONTAGEM = {
    "unidade": (Unidade, "max_unidades"),
    "usuario": (Usuario, "max_usuarios"),
    "servico": (Servico, "max_servicos"),
}

_RECURSO_LABEL = {"unidade": "unidades", "usuario": "usuários", "servico": "serviços"}


def pode_criar(empresa_id: int, recurso: str) -> tuple[bool, str | None]:
    """Retorna (pode, motivo). `motivo` é None quando pode=True, ou
    'upgrade_necessario' quando o limite do plano foi atingido.

    Planos pagos com limite nulo (None) sempre liberam — é assim que
    "sem limite" é representado (ver seed em migrations/versions/
    7a3f9c1d2b4e_planos_e_limites.py), não um número grande arbitrário.
    """
    if recurso not in _CONTAGEM:
        raise ValueError(f"Recurso desconhecido para pode_criar(): {recurso!r}")

    model, campo_limite = _CONTAGEM[recurso]

    empresa = Empresa.query.get(empresa_id)
    if empresa is None or empresa.plano is None:
        # Sem empresa/plano resolvido não há limite pra avaliar — trava
        # por segurança em vez de liberar sem checagem nenhuma.
        return False, "upgrade_necessario"

    limite = getattr(empresa.plano, campo_limite)
    if limite is None:
        return True, None

    atual = model.query.filter_by(empresa_id=empresa_id).count()
    if atual >= limite:
        return False, "upgrade_necessario"
    return True, None


def requer_limite(recurso: str):
    """Bloqueia a criação se a empresa já atingiu o limite do plano pro
    recurso indicado. Entra na pilha DEPOIS de @requer_papel/@requer_unidade
    (precisa de g.empresa_id já populado pelo before_request) e ANTES de
    qualquer lógica de criação da rota — pode_criar() roda sempre antes de
    qualquer INSERT, nunca depois."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            empresa_id = getattr(g, "empresa_id", None)
            if not empresa_id:
                flash("Sessão sem empresa associada. Faça login novamente.", "danger")
                return redirect(url_for("auth.login"))

            pode, motivo = pode_criar(empresa_id, recurso)
            if not pode:
                label = _RECURSO_LABEL.get(recurso, recurso)
                flash(
                    f"Seu plano atual não permite cadastrar mais {label}. "
                    "Faça upgrade para continuar.",
                    "warning",
                )
                return redirect(url_for("upgrade.index"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def requer_modulo(nome_modulo: str):
    """Bloqueia a rota se o plano da empresa não incluir o módulo indicado.

    Convive com SATELLITE_FEATURES_ENABLED (app/utils/feature_flags.py),
    não o substitui: este decorator checa CONTRATO (a empresa pagou por
    isso), aquele checa SEGURANÇA (o código está pronto pra isolar esse
    dado entre empresas). Os models satélite (ServiceKit/SubscriptionPlan/
    CustomerSubscription/Raffle) ainda não têm empresa_id — então mesmo
    uma empresa no plano Pro não pode usar essas rotas de verdade até a
    Fase 1-B dar esse escopo a eles. Nas rotas que já usam
    @bloqueado_enquanto_satelite_desativado (raffle/subscriptions), esse
    decorator entra ANTES dele: SATELLITE_FEATURES_ENABLED continua
    vencendo enquanto for False, independente do plano.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.is_superadmin:
                return f(*args, **kwargs)

            empresa_id = getattr(g, "empresa_id", None)
            empresa = Empresa.query.get(empresa_id) if empresa_id else None
            if not empresa or not empresa.plano or not empresa.plano.tem_modulo(nome_modulo):
                flash(
                    "Este recurso não está incluído no seu plano atual. "
                    "Faça upgrade para desbloquear.",
                    "warning",
                )
                return redirect(url_for("upgrade.index"))
            return f(*args, **kwargs)
        return decorated
    return decorator
