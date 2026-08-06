from datetime import date, datetime
from app.extensions import db
from app.models.tenant import TenantMixin


class CustomerSubscription(TenantMixin, db.Model):
    """Por EMPRESA, não unidade (Fase 1-B) — segue Cliente, cujo histórico
    já atravessa unidades da mesma empresa."""
    __tablename__ = "customer_subscription"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plan.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    renewed_at = db.Column(db.DateTime, nullable=True)

    plan = db.relationship("SubscriptionPlan", back_populates="subscriptions")
    customer = db.relationship("Cliente", back_populates="subscriptions")
    credit_balances = db.relationship(
        "SubscriptionCreditBalance",
        back_populates="subscription",
        cascade="all, delete-orphan",
        lazy="select",
    )
    credit_usages = db.relationship(
        "SubscriptionCreditUsage",
        back_populates="subscription",
        lazy="dynamic",
    )

    @property
    def is_deadline_passed(self) -> bool:
        return self.end_date < date.today()

    @property
    def has_remaining_credits(self) -> bool:
        return any(bal.remaining_credits > 0 for bal in self.credit_balances)

    @property
    def is_expired(self) -> bool:
        return self.end_date < date.today()

    @property
    def days_remaining(self) -> int:
        return max(0, (self.end_date - date.today()).days)

    @property
    def is_expiring_soon(self) -> bool:
        return not self.is_expired and self.days_remaining <= 3

    @property
    def effective_status(self) -> str:
        if self.status == "cancelled":
            return "cancelled"
        if self.is_deadline_passed:
            if self.has_remaining_credits:
                return "expired_with_credits"
            return "expired"
        return "active"

    @property
    def status_label(self) -> str:
        return {
            "active": "Ativa",
            "expired": "Vencida",
            "expired_with_credits": "Vencida c/ créditos",
            "cancelled": "Cancelada",
        }.get(self.effective_status, self.effective_status)

    @property
    def status_badge(self) -> str:
        return {
            "active": "badge-confirmed",
            "expired": "badge-no_show",
            "expired_with_credits": "badge-pending",
            "cancelled": "badge-cancelled",
        }.get(self.effective_status, "badge-pending")

    def credits_summary(self) -> list:
        return [
            {
                "service_name": bal.service.name if bal.service else "—",
                "service_id": bal.service_id,
                "remaining": bal.remaining_credits,
                "used": bal.used_credits,
                "total": bal.total_credits,
            }
            for bal in self.credit_balances
        ]


class SubscriptionCreditBalance(TenantMixin, db.Model):
    """Mesmo escopo do CustomerSubscription pai — empresa, não unidade."""
    __tablename__ = "subscription_credit_balance"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("customer_subscription.id"), nullable=False
    )
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    total_credits = db.Column(db.Integer, nullable=False, default=0)
    used_credits = db.Column(db.Integer, nullable=False, default=0)

    subscription = db.relationship("CustomerSubscription", back_populates="credit_balances")
    service = db.relationship("Servico", foreign_keys=[service_id])

    @property
    def remaining_credits(self) -> int:
        return max(0, self.total_credits - self.used_credits)


class SubscriptionCreditUsage(TenantMixin, db.Model):
    """Mesmo escopo do CustomerSubscription pai — empresa, não unidade."""
    __tablename__ = "subscription_credit_usage"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("customer_subscription.id"), nullable=False
    )
    # ondelete='SET NULL' (Fase 1-B, era NO ACTION) — preserva o histórico
    # de uso de crédito mesmo se o Agendamento em si for apagado, em vez de
    # depender só de refund_credit() já ter deletado este registro antes.
    appointment_id = db.Column(
        db.Integer, db.ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)
    used_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(255), nullable=True)

    subscription = db.relationship("CustomerSubscription", back_populates="credit_usages")
    service = db.relationship("Servico", foreign_keys=[service_id])
    appointment = db.relationship("Agendamento", foreign_keys=[appointment_id])
