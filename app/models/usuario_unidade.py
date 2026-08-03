from app.extensions import db


class UsuarioUnidade(db.Model):
    """Vínculo funcionário↔unidade. Dono/gerente não precisam de linha aqui —
    eles acessam todas as unidades da própria empresa por papel; este vínculo
    existe para restringir funcionário às unidades listadas explicitamente.
    """
    __tablename__ = "usuario_unidade"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(
        db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True
    )
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
