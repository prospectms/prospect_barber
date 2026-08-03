from datetime import datetime, timezone

from app.extensions import db
from app.models.tenant import TenantMixin, UnidadeMixin


class Servico(TenantMixin, UnidadeMixin, db.Model):
    """Antigo `Service`. Tabela mantida como `services` (ver nota em usuario.py)."""
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    appointments = db.relationship("Agendamento", backref="service", lazy="dynamic")

    @property
    def price_formatted(self) -> str:
        return f"R$ {self.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @property
    def duration_formatted(self) -> str:
        if self.duration_minutes < 60:
            return f"{self.duration_minutes} min"
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        return f"{hours}h{mins:02d}" if mins else f"{hours}h"

    def __repr__(self) -> str:
        return f"<Servico {self.name} R${self.price}>"
