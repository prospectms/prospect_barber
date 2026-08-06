"""Job diário de downgrade automático por inadimplência (Fase 3).

Nenhuma infra de scheduler existia no projeto antes da Fase 3 (confirmado
na investigação Fase 0) -- APScheduler roda em thread de background do
próprio processo web, sem worker/serviço separado. Ok pro volume atual do
projeto; se crescer, revisar pra um scheduler externo (cron do SO, Celery
beat etc.).
"""
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = None


def _rodar_downgrade(app):
    with app.app_context():
        from app.billing.service import downgrade_inadimplentes
        rebaixadas = downgrade_inadimplentes()
        if rebaixadas:
            logger.warning("Downgrade automático: %d empresa(s) rebaixada(s) para Free.", rebaixadas)


def init_scheduler(app) -> None:
    """Registra o job diário. Não roda em teste (PYTEST_CURRENT_TEST) nem
    no processo "watcher" do reloader do Flask em debug (WERKZEUG_RUN_MAIN
    != 'true') -- evita agendar o job duas vezes ou durante a suíte."""
    global _scheduler
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _rodar_downgrade, args=(app,), trigger="cron", hour=3, minute=0,
        id="downgrade_inadimplentes", replace_existing=True,
    )
    _scheduler.start()
