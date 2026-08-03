"""Feature flags temporários da Fase 1-A.

ServiceKit, assinaturas (SubscriptionPlan/CustomerSubscription/...) e
sorteios (Raffle/RaffleWinner) são os 9 models "satélite" do relatório de
investigação — ficam de fora do escopo desta fase (empresa_id/unidade_id só
chegam neles na Fase 1-B) e por isso não podem ficar ativos: sem esse
escopo, qualquer rota que os toque vaza dado entre empresas.

SATELLITE_FEATURES_ENABLED = False desliga esses caminhos por completo (não
só esconde o menu): nenhuma leitura ou escrita nesses models acontece
enquanto a flag estiver em False. Isso é mais forte do que só bloquear os
blueprints `raffle`/`subscriptions` — kits de serviço, por exemplo, são
consumidos dentro de `appointments`, não têm blueprint próprio.
"""
SATELLITE_FEATURES_ENABLED = False


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
