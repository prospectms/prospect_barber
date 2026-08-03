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
