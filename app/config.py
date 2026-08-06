import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def _db_url() -> str:
    """Lê DATABASE_URL e normaliza o prefixo postgres:// → postgresql:// (Railway/Heroku)."""
    url = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, '..', 'database.db')}",
    )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 5 * 1024 * 1024))
    WTF_CSRF_ENABLED = True
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

    # Sessão expira após inatividade de 8 horas
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    # remember_me = 30 dias
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_SECURE = False   # True em produção com HTTPS
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    TIMEZONE = "America/Campo_Grande"

    # Asaas (gateway de pagamento, Fase 3). ASAAS_WEBHOOK_TOKEN é o valor
    # configurado manualmente no painel Asaas (Configurações > Webhooks) —
    # comparado contra o header asaas-access-token em toda notificação
    # recebida, nunca aceito sem essa validação.
    ASAAS_API_BASE_URL = os.environ.get("ASAAS_API_BASE_URL", "https://api-sandbox.asaas.com/v3")
    ASAAS_API_KEY = os.environ.get("ASAAS_API_KEY", "")
    ASAAS_WEBHOOK_TOKEN = os.environ.get("ASAAS_WEBHOOK_TOKEN", "")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    WTF_CSRF_SSL_STRICT = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

    # Pool de conexões para PostgreSQL (ignorado pelo SQLite)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,   # reconecta a cada 5 min (evita conexões mortas)
        "pool_pre_ping": True, # valida conexão antes de usar
    }


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
