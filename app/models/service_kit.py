from app.extensions import db
from app.models.tenant import TenantMixin, UnidadeMixin


class ServiceKit(TenantMixin, UnidadeMixin, db.Model):
    """Por unidade (Fase 1-B): os itens do kit apontam pra Servico, que já
    é por-unidade — duas unidades da mesma empresa têm linhas de Servico
    diferentes pro "mesmo" corte, então um kit só faz sentido natural se
    também for por unidade."""
    __tablename__ = "service_kit"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    items = db.relationship(
        "ServiceKitItem",
        back_populates="kit",
        cascade="all, delete-orphan",
        order_by="ServiceKitItem.order",
        lazy="select",
    )

    @property
    def total_duration_minutes(self) -> int:
        return sum(item.service.duration_minutes for item in self.items if item.service)

    @property
    def total_price(self):
        return sum(item.service.price for item in self.items if item.service)

    @property
    def price_formatted(self) -> str:
        try:
            return (
                f"R$ {float(self.total_price):,.2f}"
                .replace(",", "X").replace(".", ",").replace("X", ".")
            )
        except (TypeError, ValueError):
            return "R$ 0,00"

    @property
    def duration_formatted(self) -> str:
        m = self.total_duration_minutes
        if m < 60:
            return f"{m} min"
        h = m // 60
        r = m % 60
        return f"{h}h{r:02d}" if r else f"{h}h"

    @property
    def services_summary(self) -> str:
        return " + ".join(item.service.name for item in self.items if item.service)

    def __repr__(self):
        return f"<ServiceKit {self.name}>"


class ServiceKitItem(TenantMixin, UnidadeMixin, db.Model):
    """Mesmo escopo do ServiceKit pai — empresa_id/unidade_id redundantes
    com kit_id mas explícitos de propósito (mesma filosofia dos demais
    models de tenant: nunca depender de join implícito pra isolamento)."""
    __tablename__ = "service_kit_item"

    id = db.Column(db.Integer, primary_key=True)
    kit_id = db.Column(db.Integer, db.ForeignKey("service_kit.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    order = db.Column(db.Integer, nullable=False, default=1)

    kit = db.relationship("ServiceKit", back_populates="items")
    service = db.relationship("Servico", foreign_keys=[service_id])
