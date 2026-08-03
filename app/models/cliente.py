import re
from datetime import datetime, timezone, date

from app.extensions import db
from app.models.tenant import TenantMixin


def _digits(phone: str) -> str:
    return re.sub(r'\D', '', phone or '')


def _format_cpf(cpf: str) -> str | None:
    clean = re.sub(r'\D', '', cpf or '')
    if len(clean) == 11:
        return f'{clean[:3]}.{clean[3:6]}.{clean[6:9]}-{clean[9:]}'
    return None


class Cliente(TenantMixin, db.Model):
    """Antigo `Customer`. Tabela mantida como `customers` (ver nota em
    usuario.py). Cliente pertence à Empresa, não à Unidade — `unidade_origem_id`
    é só referência histórica (onde o cliente apareceu pela 1ª vez), o
    histórico de agendamentos segue o cliente entre unidades da mesma empresa.

    `cpf` deixa de ser único globalmente e passa a ser único por empresa —
    duas empresas diferentes podem ter clientes com o mesmo CPF sem colisão.
    """
    __tablename__ = "customers"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "cpf", name="uq_cliente_empresa_cpf"),
    )

    id = db.Column(db.Integer, primary_key=True)
    unidade_origem_id = db.Column(
        db.Integer, db.ForeignKey("unidades.id"), nullable=True
    )
    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True, index=True)
    phone = db.Column(db.String(20), nullable=True, index=True)
    cpf = db.Column(db.String(14), nullable=True, index=True)
    birth_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_visit = db.Column(db.DateTime, nullable=True)

    unidade_origem = db.relationship("Unidade", foreign_keys=[unidade_origem_id])
    appointments = db.relationship("Agendamento", backref="customer", lazy="dynamic")
    raffle_winners = db.relationship("RaffleWinner", back_populates="customer", lazy="dynamic")
    subscriptions = db.relationship(
        "CustomerSubscription", back_populates="customer", lazy="dynamic"
    )

    # ── Estatísticas ─────────────────────────────────────────
    @property
    def total_appointments(self) -> int:
        return self.appointments.count()

    @property
    def total_visits(self) -> int:
        return self.appointments.filter_by(status="completed").count()

    @property
    def pending_appointments(self) -> int:
        from app.models.agendamento import Agendamento
        return self.appointments.filter(
            Agendamento.status.in_(["pending", "confirmed"])
        ).count()

    @property
    def age(self):
        if self.birth_date:
            today = date.today()
            return today.year - self.birth_date.year - (
                (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
            )
        return None

    # ── Avatar ───────────────────────────────────────────────
    @property
    def initials(self) -> str:
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.name[:2].upper()

    # ── Criação automática ───────────────────────────────────
    @classmethod
    def get_or_create(cls, empresa_id: int, name: str, phone: str | None,
                       cpf: str | None = None, unidade_origem_id: int | None = None):
        """
        Busca cliente da empresa pelo CPF (prioritário) ou telefone normalizado.
        Se não encontrar, cria um novo. Retorna (customer, created: bool).
        O chamador é responsável por fazer db.session.commit().
        """
        if cpf:
            formatted = _format_cpf(cpf)
            if formatted:
                match = cls.query.filter_by(empresa_id=empresa_id, cpf=formatted).first()
                if match:
                    return match, False

        if phone:
            digits = _digits(phone)
            if digits:
                match = next(
                    (c for c in cls.query.filter_by(empresa_id=empresa_id)
                     .filter(cls.phone.isnot(None)).all()
                     if _digits(c.phone) == digits),
                    None,
                )
                if match:
                    return match, False

        customer = cls(
            empresa_id=empresa_id,
            unidade_origem_id=unidade_origem_id,
            name=name.strip(),
            phone=(phone or "").strip() or None,
            cpf=_format_cpf(cpf) if cpf else None,
        )
        db.session.add(customer)
        return customer, True

    def __repr__(self) -> str:
        return f"<Cliente {self.name}>"
