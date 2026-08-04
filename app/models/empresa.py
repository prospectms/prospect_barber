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

    # FK real desde a Fase 2 (planos/limites) — era Integer solto na Fase 1-A,
    # "placeholder simples" documentado no próprio comentário anterior.
    # default=1 == plano "free", garantido pela ordem de seed da migração.
    plano_id = db.Column(db.Integer, db.ForeignKey("planos.id"), nullable=False, default=1)
    status_assinatura = db.Column(db.String(20), nullable=False, default="ativa")

    # periodicidade/preco_congelado só fazem sentido depois que a empresa
    # contrata um plano pago pela primeira vez (checkout ainda é stub nesta
    # fase — ver app/upgrade/routes.py). preco_congelado NUNCA é recalculado
    # por reajuste futuro da tabela de preços do Plano; só muda em novo
    # ciclo de cobrança ou upgrade explícito.
    periodicidade = db.Column(db.String(10), nullable=True)  # 'mensal'|'anual'
    preco_congelado = db.Column(db.Numeric(10, 2), nullable=True)

    # Guardados desde já, não consumidos nesta fase (ver relatório Fase 0, item 5).
    logo_url = db.Column(db.String(255), nullable=True)
    cor_primaria = db.Column(db.String(7), nullable=True)

    criada_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    unidades = db.relationship(
        "Unidade", back_populates="empresa", cascade="all, delete-orphan"
    )
    plano = db.relationship("Plano", back_populates="empresas")

    def __repr__(self) -> str:
        return f"<Empresa {self.nome!r} ({self.slug})>"
