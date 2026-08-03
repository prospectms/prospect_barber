import re
from datetime import datetime, timezone

from app.extensions import db


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value or "").strip().lower()
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-")


class Empresa(db.Model):
    __tablename__ = "empresas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    documento = db.Column(db.String(20), nullable=True)  # CNPJ/CPF
    email = db.Column(db.String(120), nullable=True)
    telefone = db.Column(db.String(20), nullable=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)

    # Placeholder simples — tabela Plano/limites reais só na Fase 2.
    plano_id = db.Column(db.Integer, nullable=False, default=1)
    status_assinatura = db.Column(db.String(20), nullable=False, default="ativa")

    # Guardados desde já, não consumidos nesta fase (ver relatório Fase 0, item 5).
    logo_url = db.Column(db.String(255), nullable=True)
    cor_primaria = db.Column(db.String(7), nullable=True)

    criada_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    unidades = db.relationship(
        "Unidade", back_populates="empresa", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Empresa {self.nome!r} ({self.slug})>"
