from datetime import datetime, timezone

from app.extensions import db


class AuditLog(db.Model):
    """Registro de cada acesso de superadmin a dados de uma empresa que não é a
    dele — trilha obrigatória exigida pela Fase 1-A para o papel superadmin."""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True)
    acao = db.Column(db.String(120), nullable=False)
    detalhe = db.Column(db.String(255), nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    usuario = db.relationship("Usuario")
    empresa = db.relationship("Empresa")

    def __repr__(self) -> str:
        return f"<AuditLog usuario={self.usuario_id} empresa={self.empresa_id} {self.acao!r}>"
