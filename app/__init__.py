import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, redirect, url_for, flash, session, g
from flask_login import current_user, logout_user
from app.config import config
from app.extensions import db, login_manager, csrf, migrate


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    _configure_logging(app)
    _register_blueprints(app)
    _configure_login_manager()
    _register_error_handlers(app)
    _register_middleware(app)
    _register_security_headers(app)
    _register_shell_context(app)
    _register_context_processors(app)
    _register_template_filters(app)
    # _ensure_schema(app) — CONGELADO na Fase 1-A. Ver docstring da função:
    # substituído por Flask-Migrate/Alembic (comando `flask db upgrade`).

    return app


def _configure_logging(app: Flask) -> None:
    if app.debug:
        return

    log_dir = os.path.join(os.path.dirname(app.root_path), "logs")
    os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        os.path.join(log_dir, "prospect_barber.log"),
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s %(module)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.WARNING)


def _register_blueprints(app: Flask) -> None:
    from app.auth.routes import auth_bp
    from app.dashboard.routes import dashboard_bp
    from app.barbers.routes import barbers_bp
    from app.customers.routes import customers_bp
    from app.services.routes import services_bp
    from app.appointments.routes import appointments_bp
    from app.booking.routes import booking_bp
    from app.raffle.routes import raffle_bp
    from app.reports.routes import reports_bp
    from app.client.routes import client_bp
    from app.subscriptions.routes import subscriptions_bp
    from app.pages.routes import pages_bp
    from app.superadmin.routes import superadmin_bp
    from app.unidades.routes import unidades_bp
    from app.upgrade.routes import upgrade_bp
    from app.webhooks.routes import webhooks_bp
    from app.internal.routes import internal_bp

    app.register_blueprint(auth_bp,           url_prefix="/auth")
    app.register_blueprint(dashboard_bp,      url_prefix="/")
    app.register_blueprint(barbers_bp,        url_prefix="/barbers")
    app.register_blueprint(customers_bp,      url_prefix="/customers")
    app.register_blueprint(services_bp,       url_prefix="/services")
    app.register_blueprint(appointments_bp,   url_prefix="/appointments")
    app.register_blueprint(booking_bp,        url_prefix="/agendar")
    app.register_blueprint(raffle_bp,         url_prefix="/raffle")
    app.register_blueprint(reports_bp,        url_prefix="/reports")
    app.register_blueprint(client_bp,         url_prefix="/p")
    app.register_blueprint(subscriptions_bp,  url_prefix="/subscriptions")
    app.register_blueprint(pages_bp,          url_prefix="/")
    app.register_blueprint(superadmin_bp,     url_prefix="/superadmin")
    app.register_blueprint(unidades_bp,       url_prefix="/unidades")
    app.register_blueprint(upgrade_bp,        url_prefix="/upgrade")
    app.register_blueprint(webhooks_bp,       url_prefix="/webhooks")
    app.register_blueprint(internal_bp,       url_prefix="/internal")


def _configure_login_manager() -> None:
    from app.models.usuario import Usuario

    @login_manager.user_loader
    def load_user(user_id: str):
        # session-level get() ignora o filtro de tenant de propósito: em login
        # ainda não há g.empresa_id — ele é justamente derivado do usuário aqui.
        return db.session.get(Usuario, int(user_id))


def _register_middleware(app: Flask) -> None:

    @app.before_request
    def enforce_active_session():
        if current_user.is_authenticated and not current_user.ativo:
            logout_user()
            flash("Sua conta foi desativada. Contate o administrador.", "danger")
            return redirect(url_for("auth.login"))

    @app.before_request
    def load_tenant_context():
        """Popula g.empresa_id/g.unidade_id a partir da sessão autenticada.

        Rotas públicas que resolvem empresa/unidade por slug (agenda pública,
        portal do cliente) sobrescrevem g.empresa_id/g.unidade_id explicitamente
        depois de validar o slug — ver app/booking/routes.py e app/client/routes.py.
        """
        g.empresa_id = None
        g.unidade_id = None
        if not current_user.is_authenticated:
            return

        g.empresa_id = current_user.empresa_id

        from app.utils.tenant_context import usuario_pode_acessar_unidade
        unidade_ativa_id = session.get("unidade_ativa_id")
        if unidade_ativa_id and usuario_pode_acessar_unidade(current_user, unidade_ativa_id):
            g.unidade_id = unidade_ativa_id
        else:
            session.pop("unidade_ativa_id", None)


def _register_security_headers(app: Flask) -> None:

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


def _register_error_handlers(app: Flask) -> None:

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        app.logger.exception("Erro 500: %s", e)
        return render_template("errors/500.html"), 500


def _register_context_processors(app: Flask) -> None:
    from datetime import datetime, timezone

    @app.context_processor
    def inject_now():
        return {"now": datetime.now(timezone.utc)}

    @app.context_processor
    def inject_tenant_context():
        """Expõe a Unidade ativa (objeto, não só o ID) pros templates —
        sidebar/topbar mostram nome/slug sem cada view precisar passar isso
        manualmente. Unidade.query.get() já reforça que ela pertence a
        g.empresa_id (TenantQuery, ver app/models/tenant.py); se por algum
        motivo unidade_id não bater com a empresa do usuário, isso retorna
        None em vez de vazar a unidade de outra empresa."""
        from app.models.unidade import Unidade
        unidade_ativa = None
        if getattr(g, "unidade_id", None):
            unidade_ativa = Unidade.query.get(g.unidade_id)
        return {"unidade_ativa": unidade_ativa}


def _register_template_filters(app: Flask) -> None:
    import re

    @app.template_filter("wa_number")
    def wa_number_filter(phone: str) -> str:
        if not phone:
            return ""
        digits = re.sub(r"\D", "", phone)
        if not digits:
            return ""
        if not digits.startswith("55"):
            digits = "55" + digits
        return digits


def _ensure_schema(app: Flask) -> None:
    """
    CONGELADA desde a Fase 1-A (multi-tenancy) — não é mais chamada em create_app().

    Mecanismo antigo (pré-Alembic) que adicionava colunas via ALTER TABLE ad-hoc,
    engolindo qualquer erro. Não sabe criar tabelas novas, FKs, constraints de
    unicidade composta nem fazer backfill de dados — por isso não dava conta da
    migração estrutural da Fase 1-A (empresas/unidades + empresa_id/unidade_id
    em todo model de tenant). Ver relatório de investigação da Fase 0, item 4.

    Substituída por Flask-Migrate/Alembic: `flask db upgrade` aplica o schema
    atual. Função mantida apenas como referência histórica — não remover.
    """
    with app.app_context():
        from sqlalchemy import inspect, text
        db.create_all()
        inspector = inspect(db.engine)
        migrations = [
            ("customers",    "cpf",          "VARCHAR(14)"),
            ("barbers",      "whatsapp",     "VARCHAR(20)"),
            ("barbers",      "lunch_start",  "TIME"),
            ("barbers",      "lunch_end",    "TIME"),
            ("appointments", "kit_id",       "INTEGER"),
        ]
        with db.engine.connect() as conn:
            for table, col, col_def in migrations:
                try:
                    existing = {c["name"] for c in inspector.get_columns(table)}
                    if col not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                        conn.commit()
                except Exception:
                    pass


def _register_shell_context(app: Flask) -> None:
    from app.models import (
        Empresa, Unidade, Usuario, UsuarioUnidade, AuditLog,
        Profissional, Cliente, Servico, Agendamento, Raffle,
        ServiceKit, ServiceKitItem,
        SubscriptionPlan, SubscriptionPlanCredit,
        CustomerSubscription, SubscriptionCreditBalance, SubscriptionCreditUsage,
        BarberScheduleException,
    )

    @app.shell_context_processor
    def make_shell_context():
        return {
            "db": db,
            "Empresa": Empresa,
            "Unidade": Unidade,
            "Usuario": Usuario,
            "UsuarioUnidade": UsuarioUnidade,
            "AuditLog": AuditLog,
            "Profissional": Profissional,
            "Cliente": Cliente,
            "Servico": Servico,
            "Agendamento": Agendamento,
            "Raffle": Raffle,
            "ServiceKit": ServiceKit,
            "ServiceKitItem": ServiceKitItem,
            "SubscriptionPlan": SubscriptionPlan,
            "SubscriptionPlanCredit": SubscriptionPlanCredit,
            "CustomerSubscription": CustomerSubscription,
            "SubscriptionCreditBalance": SubscriptionCreditBalance,
            "SubscriptionCreditUsage": SubscriptionCreditUsage,
            "BarberScheduleException": BarberScheduleException,
        }
