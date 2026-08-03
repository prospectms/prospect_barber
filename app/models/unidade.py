from app.extensions import db
from app.models.tenant import TenantMixin


class Unidade(TenantMixin, db.Model):
    """Herda TenantMixin (não só a coluna) para ganhar a mesma proteção
    automática contra IDOR que os demais models de tenant — sem isso, um
    dono da Empresa A poderia adivinhar o ID de uma Unidade da Empresa B e
    lê-la diretamente. Antes de login/slug resolvido, g.empresa_id é None e
    o filtro simplesmente não se aplica (ver tenant.py), então isso não
    quebra a resolução pública por slug em /agendar/<slug> e /p/<slug>."""
    __tablename__ = "unidades"

    id = db.Column(db.Integer, primary_key=True)
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
