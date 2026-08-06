"""Feature flags — histórico nas Fases 1-A/1-B.

ServiceKit, assinaturas (SubscriptionPlan/CustomerSubscription/...) e
sorteios (Raffle/RaffleWinner) são os 9 models "satélite" do relatório de
investigação original. Ficaram bloqueados por completo (SATELLITE_
FEATURES_ENABLED = False) da Fase 1-A até a Fase 1-B porque não tinham
empresa_id/unidade_id — qualquer rota que os tocasse vazava dado entre
empresas.

Fase 1-B deu esse escopo aos 9 models (TenantMixin/UnidadeMixin, ver
migrations/versions/5f8c3d7e9a1b_escopo_satelite.py), reescreveu
raffle/subscriptions/service.py com filtro explícito de empresa_id, e só
então — depois da suíte de isolamento (tests/test_8_isolamento_satelite.py,
10 testes, incluindo o cenário do pool de sorteio cross-tenant) passar —
a flag virou True. Raffle ganhou @requer_modulo('sorteios') nesse
processo (decisão explícita, não ficou liberado pra todo plano por
default).

SATELLITE_FEATURES_ENABLED = True: os 9 models já são seguros de usar. A
função abaixo (bloqueado_enquanto_satelite_desativado) fica no código
como mecanismo — se a flag precisar voltar pra False por qualquer motivo
futuro (ex.: bug descoberto em produção), o bloqueio duro continua
funcionando exatamente como antes.
"""
SATELLITE_FEATURES_ENABLED = True


def bloqueado_enquanto_satelite_desativado(f):
    """Bloqueia uma rota inteira enquanto SATELLITE_FEATURES_ENABLED for False.

    Uso: blueprints raffle/subscriptions (dono/gerente só veem aviso
    "temporariamente indisponível" no painel). NÃO usar em rotas públicas
    (agenda pública, portal do cliente) — lá a regra é diferente: elas
    simplesmente não expõem link/menu para essas features, sem mensagem
    nenhuma ao cliente final. Ver combinado da Fase 1-A.
    """
    from functools import wraps
    from flask import flash, redirect, url_for

    @wraps(f)
    def decorated(*args, **kwargs):
        if not SATELLITE_FEATURES_ENABLED:
            flash(
                "Este recurso está temporariamente indisponível durante a "
                "migração para multi-unidade. Volta em breve.",
                "warning",
            )
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated
