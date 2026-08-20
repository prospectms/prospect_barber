"""
Infra de isolamento multi-tenant (Fase 1-A).

`TenantMixin` marca um model como dado de Empresa. A partir daí, toda leitura
desse model é filtrada por `empresa_id` automaticamente, em dois pontos
complementares — nenhum dos dois cobre 100% sozinho:

  1. `with_loader_criteria` — evento global de sessão que injeta
     `WHERE empresa_id = g.empresa_id` em qualquer SELECT via ORM
     (Model.query.filter(...), relationships/lazy loads, db.session.execute(select(...))).
     Não cobre lookup direto por PK (`Session.get()` / `Query.get()`) — é uma
     limitação documentada do SQLAlchemy: get() por identidade ignora
     with_loader_criteria de propósito.

  2. `TenantQuery.get()` / `get_or_404()` — cobre exatamente o caso acima.
     `Model.query.get_or_404(id)` é o padrão mais comum de IDOR neste projeto
     (toda rota de detalhe usa isso), então é o ponto mais crítico de fechar.

`UnidadeMixin` adiciona `unidade_id` mas SEM filtro automático — diferente de
empresa_id, o escopo de unidade é uma escolha de UI (dono/gerente trocam de
unidade ativa), não um limite de segurança absoluto por request. É reforçado
pelo decorator `@requer_unidade` e por filtro explícito nas rotas, não aqui.

Superadmin pode suspender o filtro de empresa dentro de `with tenant_bypass():`
— uso restrito a rotas que já registraram o acesso em AuditLog (ver
app/superadmin/routes.py).
"""
from contextlib import contextmanager
from contextvars import ContextVar

from flask import g, has_request_context, abort
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria
from flask_sqlalchemy.query import Query as _FSAQuery

from app.extensions import db

_bypass_var: ContextVar[bool] = ContextVar("tenant_bypass", default=False)


@contextmanager
def tenant_bypass():
    """Suspende o filtro automático de empresa_id para o bloco do `with`.

    Uso restrito: rotas de superadmin, sempre após registrar o acesso em
    AuditLog. Não usar em rota de tenant normal — anularia o isolamento.
    """
    token = _bypass_var.set(True)
    try:
        yield
    finally:
        _bypass_var.reset(token)


def current_empresa_id():
    """empresa_id efetivo da request atual, ou None (sem filtro / bypass ativo)."""
    if _bypass_var.get():
        return None
    if has_request_context():
        return getattr(g, "empresa_id", None)
    return None


class TenantQuery(_FSAQuery):
    """Query padrão de todo model TenantMixin.

    get()/get_or_404() reforçam o filtro de empresa mesmo em lookup direto
    por PK, caso que with_loader_criteria não cobre (ver docstring do módulo).
    """

    def get(self, ident):
        # Session.get() no lugar do Query.get() legado (SQLAlchemy 2.0
        # depreca o segundo). column_descriptions[0]['entity'] é API
        # pública e estável pra achar a classe mapeada a partir da query
        # genérica — TenantQuery é a mesma classe pra todo model
        # TenantMixin, não dá pra fixar a entidade em tempo de escrita.
        entity = self.column_descriptions[0]["entity"]
        obj = self.session.get(entity, ident)
        if obj is None:
            return None
        empresa_id = current_empresa_id()
        if empresa_id is not None and getattr(obj, "empresa_id", None) != empresa_id:
            return None
        return obj

    def get_or_404(self, ident, description=None):
        obj = self.get(ident)
        if obj is None:
            abort(404, description=description)
        return obj


class TenantMixin:
    """Mixin para todo model que é dado de Empresa (tenant)."""

    query_class = TenantQuery

    empresa_id = db.Column(
        db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True
    )


class UnidadeMixin:
    """Mixin para model operacional que também pertence a uma Unidade.

    Sem filtro automático — ver docstring do módulo. Escopo reforçado por
    @requer_unidade e filtro explícito na rota.
    """

    unidade_id = db.Column(
        db.Integer, db.ForeignKey("unidades.id"), nullable=False, index=True
    )


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(execute_state):
    if not execute_state.is_select:
        return
    empresa_id = current_empresa_id()
    if empresa_id is None:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantMixin,
            lambda cls: cls.empresa_id == empresa_id,
            include_aliases=True,
        )
    )
