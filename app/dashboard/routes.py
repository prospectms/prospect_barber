from flask import Blueprint, render_template, g
from flask_login import login_required, current_user
from datetime import date, timedelta
from sqlalchemy import func
from app.extensions import db
from app.models.agendamento import Agendamento
from app.models.cliente import Cliente
from app.models.profissional import Profissional
from app.models.servico import Servico
from app.utils.decorators import requer_unidade

dashboard_bp = Blueprint("dashboard", __name__)

_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
_WEEKDAYS_PT = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dashboard_bp.route("/")
@login_required
@requer_unidade
def index():
    today = date.today()
    month_start = today.replace(day=1)
    unidade_id = g.unidade_id

    # Escopo: dono/gerente vê a unidade ativa inteira; funcionário só a
    # própria agenda dentro dela.
    barber_id = None
    if not current_user.pode_gerenciar and current_user.profissional:
        barber_id = current_user.profissional.id

    stats = _build_stats(today, month_start, unidade_id, barber_id)
    weekly = _weekly_revenue(unidade_id, barber_id)
    upcoming = _upcoming_appointments(today, unidade_id, barber_id)
    top_barbers = _top_barbers(month_start, unidade_id) if current_user.pode_gerenciar else []
    top_services = _top_services(month_start, unidade_id, barber_id)

    today_label = (
        f"{_WEEKDAYS_PT[today.weekday()].capitalize()}, "
        f"{today.day} de {_MONTHS_PT[today.month - 1]} de {today.year}"
    )
    month_label = f"{_MONTHS_PT[today.month - 1].capitalize()} {today.year}"

    return render_template(
        "dashboard/index.html",
        stats=stats,
        weekly=weekly,
        upcoming=upcoming,
        top_barbers=top_barbers,
        top_services=top_services,
        today=today,
        today_label=today_label,
        month_label=month_label,
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_stats(today, month_start, unidade_id, barber_id=None) -> dict:
    """
    All KPI numbers for the cards.
    barber_id=None → visão da unidade inteira (dono/gerente).
    barber_id set  → filtrado para aquele profissional (funcionário).
    """

    def _count(*filters):
        q = Agendamento.query.filter(Agendamento.unidade_id == unidade_id)
        if barber_id:
            q = q.filter(Agendamento.barber_id == barber_id)
        for f in filters:
            q = q.filter(f)
        return q.count()

    def _revenue(*filters):
        """Sum of Servico.price para agendamentos concluídos."""
        q = (
            db.session.query(func.sum(Servico.price))
            .join(Agendamento, Agendamento.service_id == Servico.id)
            .filter(Agendamento.unidade_id == unidade_id, Agendamento.status == "completed")
        )
        if barber_id:
            q = q.filter(Agendamento.barber_id == barber_id)
        for f in filters:
            q = q.filter(f)
        return float(q.scalar() or 0)

    today_total     = _count(Agendamento.scheduled_date == today)
    today_pending   = _count(
        Agendamento.scheduled_date == today,
        Agendamento.status.in_(["pending", "confirmed"]),
    )
    today_completed = _count(
        Agendamento.scheduled_date == today,
        Agendamento.status == "completed",
    )
    today_revenue   = _revenue(Agendamento.scheduled_date == today)
    month_revenue   = _revenue(Agendamento.scheduled_date >= month_start)

    # Completion rate = completed / (completed + cancelled + no_show) this month
    # Excludes still-pending/confirmed appointments to avoid penalising future slots
    month_closed = _count(
        Agendamento.scheduled_date >= month_start,
        Agendamento.status.in_(["completed", "cancelled", "no_show"]),
    )
    month_completed = _count(
        Agendamento.scheduled_date >= month_start,
        Agendamento.status == "completed",
    )
    completion_rate = round(
        (month_completed / month_closed * 100) if month_closed else 0, 1
    )

    avg_ticket = (today_revenue / today_completed) if today_completed else 0

    total_customers = Cliente.query.count() if not barber_id else None
    active_barbers = (
        Profissional.query.filter_by(is_active=True, unidade_id=unidade_id).count()
        if not barber_id else None
    )

    return {
        "today_total":       today_total,
        "today_pending":     today_pending,
        "today_completed":   today_completed,
        "today_revenue":     today_revenue,
        "today_revenue_fmt": _fmt_brl(today_revenue),
        "month_revenue":     month_revenue,
        "month_revenue_fmt": _fmt_brl(month_revenue),
        "completion_rate":   completion_rate,
        "avg_ticket":        avg_ticket,
        "avg_ticket_fmt":    _fmt_brl(avg_ticket),
        "total_customers":   total_customers,
        "active_barbers":    active_barbers,
    }


def _weekly_revenue(unidade_id, barber_id=None) -> dict:
    """Daily completed revenue for the last 7 days (including today)."""
    today = date.today()
    labels, values = [], []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        labels.append(day.strftime("%d/%m"))
        q = (
            db.session.query(func.sum(Servico.price))
            .join(Agendamento, Agendamento.service_id == Servico.id)
            .filter(
                Agendamento.unidade_id == unidade_id,
                Agendamento.scheduled_date == day,
                Agendamento.status == "completed",
            )
        )
        if barber_id:
            q = q.filter(Agendamento.barber_id == barber_id)
        values.append(float(q.scalar() or 0))
    return {"labels": labels, "amounts": values}


def _upcoming_appointments(today, unidade_id, barber_id=None):
    """Next 8 pending/confirmed appointments from today onwards."""
    q = Agendamento.query.filter(
        Agendamento.unidade_id == unidade_id,
        Agendamento.scheduled_date >= today,
        Agendamento.status.in_(["pending", "confirmed"]),
    )
    if barber_id:
        q = q.filter(Agendamento.barber_id == barber_id)
    return (
        q.order_by(Agendamento.scheduled_date, Agendamento.scheduled_time)
        .limit(8)
        .all()
    )


def _top_barbers(month_start, unidade_id) -> list:
    """Top 5 barbers by completed appointment count this month (dono/gerente)."""
    rows = (
        db.session.query(
            Profissional,
            func.count(Agendamento.id).label("cnt"),
            func.coalesce(func.sum(Servico.price), 0).label("revenue"),
        )
        .join(Agendamento, Agendamento.barber_id == Profissional.id)
        .join(Servico, Servico.id == Agendamento.service_id)
        .filter(
            Agendamento.unidade_id == unidade_id,
            Agendamento.status == "completed",
            Agendamento.scheduled_date >= month_start,
        )
        .group_by(Profissional.id)
        .order_by(func.count(Agendamento.id).desc())
        .limit(5)
        .all()
    )
    return [
        {
            "barber":      r[0],
            "cnt":         r.cnt,
            "revenue":     float(r.revenue),
            "revenue_fmt": _fmt_brl(float(r.revenue)),
        }
        for r in rows
    ]


def _top_services(month_start, unidade_id, barber_id=None) -> list:
    """Top 6 services by completed appointment count this month."""
    q = (
        db.session.query(
            Servico,
            func.count(Agendamento.id).label("cnt"),
            func.coalesce(func.sum(Servico.price), 0).label("revenue"),
        )
        .join(Agendamento, Agendamento.service_id == Servico.id)
        .filter(
            Agendamento.unidade_id == unidade_id,
            Agendamento.status == "completed",
            Agendamento.scheduled_date >= month_start,
        )
    )
    if barber_id:
        q = q.filter(Agendamento.barber_id == barber_id)
    rows = (
        q.group_by(Servico.id)
        .order_by(func.count(Agendamento.id).desc())
        .limit(6)
        .all()
    )
    return [
        {
            "service":     r[0],
            "cnt":         r.cnt,
            "revenue":     float(r.revenue),
            "revenue_fmt": _fmt_brl(float(r.revenue)),
        }
        for r in rows
    ]
