from app.extensions import db
from app.models.tenant import TenantMixin


class UsuarioUnidade(TenantMixin, db.Model):
    """Vínculo funcionário↔unidade. Dono/gerente não precisam de linha aqui —
    eles acessam todas as unidades da própria empresa por papel; este vínculo
    existe para restringir funcionário às unidades listadas explicitamente.

    Herda TenantMixin pela mesma razão de Unidade (ver unidade.py): consistência
    — nenhum model de tenant fica de fora da proteção automática por padrão.
    """
    __tablename__ = "usuario_unidade"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    unidade_id = db.Column(
        db.Integer, db.ForeignKey("unidades.id"), nullable=False, index=True
    )

    usuario = db.relationship("Usuario", back_populates="unidades_vinculadas")
    unidade = db.relationship("Unidade")

    __table_args__ = (
        db.UniqueConstraint("usuario_id", "unidade_id", name="uq_usuario_unidade"),
    )

    def __repr__(self) -> str:
        return f"<UsuarioUnidade usuario={self.usuario_id} unidade={self.unidade_id}>"
