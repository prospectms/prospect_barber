"""Helpers de resolução de unidade ativa — usados pelo before_request global
e pelo seletor de unidade (auth.routes). Ficam fora de app/models para não
criar dependência de rotas dentro da camada de model."""
from app.models.unidade import Unidade
from app.models.usuario_unidade import UsuarioUnidade


def unidades_do_usuario(usuario) -> list[Unidade]:
    """Unidades que o usuário pode selecionar como ativa."""
    if usuario.pode_gerenciar or usuario.is_superadmin:
        return (
            Unidade.query
            .filter_by(empresa_id=usuario.empresa_id, ativa=True)
            .order_by(Unidade.nome)
            .all()
        )
    return (
        Unidade.query
        .join(UsuarioUnidade, UsuarioUnidade.unidade_id == Unidade.id)
        .filter(
            UsuarioUnidade.usuario_id == usuario.id,
            Unidade.empresa_id == usuario.empresa_id,
            Unidade.ativa.is_(True),
        )
        .order_by(Unidade.nome)
        .all()
    )


def usuario_pode_acessar_unidade(usuario, unidade_id: int) -> bool:
    if not unidade_id:
        return False
    unidade = Unidade.query.filter_by(id=unidade_id, empresa_id=usuario.empresa_id).first()
    if not unidade:
        return False
    if usuario.pode_gerenciar or usuario.is_superadmin:
        return True
    return (
        UsuarioUnidade.query
        .filter_by(usuario_id=usuario.id, unidade_id=unidade_id)
        .first()
        is not None
    )


def resolver_unidade_por_slug(slug: str) -> Unidade:
    """Resolve Unidade por slug para rotas PÚBLICAS (agenda por unidade,
    portal do cliente) — não exigem login.

    Essas rotas rodam sem sessão autenticada, então o before_request global
    (app/__init__.py) não popula g.empresa_id/g.unidade_id sozinho. É este
    helper que faz isso a partir do slug da URL — a partir daqui, toda
    leitura de model TenantMixin nessa request já sai filtrada para a
    empresa da unidade resolvida, sem precisar repetir o filtro manualmente.

    404 se o slug não existir ou a unidade estiver inativa — nunca 403,
    para não revelar a um visitante anônimo se um slug "quase certo" existe.
    """
    from flask import g, abort
    unidade = Unidade.query.filter_by(slug=slug, ativa=True).first()
    if not unidade:
        abort(404)
    g.empresa_id = unidade.empresa_id
    g.unidade_id = unidade.id
    return unidade
