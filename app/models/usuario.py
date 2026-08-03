from datetime import datetime, timezone, timedelta

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.models.tenant import TenantMixin

_LOCK_THRESHOLD = 5       # tentativas antes de bloquear
_LOCK_MINUTES = 15        # minutos de bloqueio

PAPEIS = ("dono", "gerente", "funcionario")


class Usuario(TenantMixin, UserMixin, db.Model):
    """Conta de login. Tabela mantida como `users` (nome herdado do schema
    pré-multi-tenant) para não obrigar rename de tabela numa migração que já
    mexe em muita coisa — ver nota na migração Alembic da Fase 1-A."""
    __tablename__ = "users"
    __table_args__ = (
        db.UniqueConstraint("empresa_id", "email", name="uq_usuario_empresa_email"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="funcionario")  # dono|gerente|funcionario
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime, nullable=True)
    login_count = db.Column(db.Integer, default=0, nullable=False)

    # Proteção brute-force
    failed_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    empresa = db.relationship("Empresa")
    profissional = db.relationship(
        "Profissional", back_populates="usuario", uselist=False
    )
    unidades_vinculadas = db.relationship(
        "UsuarioUnidade", back_populates="usuario", cascade="all, delete-orphan"
    )

    # Flask-Login exige is_active como atributo/propriedade — mapeado para `ativo`.
    @property
    def is_active(self) -> bool:
        return self.ativo

    # ── Senha ──────────────────────────────────────────
    def set_password(self, password: str) -> None:
        self.senha_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.senha_hash, password)

    # ── Papéis ───────────────────────────────────────────
    @property
    def is_dono(self) -> bool:
        return self.papel == "dono"

    @property
    def is_gerente(self) -> bool:
        return self.papel == "gerente"

    @property
    def is_funcionario(self) -> bool:
        return self.papel == "funcionario"

    @property
    def pode_gerenciar(self) -> bool:
        """dono ou gerente — acesso de gestão da empresa (equivalente ao antigo admin_required)."""
        return self.papel in ("dono", "gerente")

    @property
    def papel_label(self) -> str:
        return {"dono": "Dono", "gerente": "Gerente", "funcionario": "Funcionário"}.get(
            self.papel, self.papel
        )

    @property
    def role_badge_color(self) -> str:
        return {"dono": "gold", "gerente": "info", "funcionario": "secondary"}.get(
            self.papel, "secondary"
        )

    # ── Bloqueio por tentativas ──────────────────────────
    @property
    def is_locked(self) -> bool:
        if self.locked_until:
            return datetime.now(timezone.utc) < self.locked_until.replace(tzinfo=timezone.utc)
        return False

    @property
    def lock_remaining_minutes(self) -> int:
        if self.is_locked:
            delta = self.locked_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
            return max(1, int(delta.total_seconds() // 60) + 1)
        return 0

    def handle_failed_login(self) -> None:
        self.failed_attempts += 1
        if self.failed_attempts >= _LOCK_THRESHOLD:
            self.locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCK_MINUTES)

    def reset_login_attempts(self) -> None:
        self.failed_attempts = 0
        self.locked_until = None

    def record_login(self) -> None:
        self.reset_login_attempts()
        self.last_login = datetime.now(timezone.utc)
        self.login_count = (self.login_count or 0) + 1

    # ── Display ─────────────────────────────────────────
    @property
    def display_name(self) -> str:
        return self.nome

    def __repr__(self) -> str:
        return f"<Usuario {self.email} [{self.papel}] empresa={self.empresa_id}>"
