from app.extensions import db


class Unidade(db.Model):
    __tablename__ = "unidades"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(
        db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True
    )
    nome = db.Column(db.String(150), nullable=False)
    # Único GLOBAL (não por empresa) — usado como identificador de URL pública
    # em /agendar/<slug> e /p/<slug>/lookup, então precisa ser único no sistema.
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    endereco = db.Column(db.String(255), nullable=True)
    telefone = db.Column(db.String(20), nullable=True)
    ativa = db.Column(db.Boolean, default=True, nullable=False)

    empresa = db.relationship("Empresa", back_populates="unidades")

    def __repr__(self) -> str:
        return f"<Unidade {self.nome!r} ({self.slug})>"
