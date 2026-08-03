from datetime import date, datetime, timezone, timedelta
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, jsonify, g,
)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.agendamento import Agendamento, APPOINTMENT_STATUSES
from app.models.profissional import Profissional
from app.models.cliente import Cliente
from app.models.servico import Servico
from app.appointments.forms import AppointmentAdminForm
from app.appointments.availability import get_available_slots, is_slot_available
from app.utils.decorators import requer_papel, requer_unidade
from app.utils.feature_flags import SATELLITE_FEATURES_ENABLED

appointments_bp = Blueprint("appointments", __name__)

# NOTA: as rotas públicas de agendamento (book/slots/book_success) que existiam
# aqui foram removidas deste blueprint — vão para app/booking (agenda pública
# por slug de unidade, /agendar/<slug>), ainda não criado. Até lá, não há rota
# pública de agendamento no ar; só o fluxo autenticado abaixo.


def _minha_profissional_id():
    """ID do Profissional vinculado ao usuário logado, se houver e ele não for
    dono/gerente (que enxergam a agenda inteira da unidade, não só a própria)."""
    if current_user.pode_gerenciar:
        return None
    return current_user.profissional.id if current_user.profissional else None


# ── Admin / Funcionário: Listagem ─────────────────────────────────────────────
@appointments_bp.route("/")
@login_required
@requer_unidade
def index():
    date_str      = request.args.get("date", str(date.today()))
    status_filter = request.args.get("status", "")
    barber_filter = request.args.get("barber_id", type=int)

    try:
        filter_date = date.fromisoformat(date_str)
    except ValueError:
        filter_date = date.today()
        date_str = str(filter_date)

    # empresa_id já vem automático (TenantMixin); unidade_id é manual —
    # a agenda mostra a unidade ativa, não a empresa inteira de uma vez.
    query = Agendamento.query.filter_by(scheduled_date=filter_date, unidade_id=g.unidade_id)

    minha_profissional_id = _minha_profissional_id()
    if minha_profissional_id:
        query = query.filter_by(barber_id=minha_profissional_id)
    elif current_user.pode_gerenciar and barber_filter:
        query = query.filter_by(barber_id=barber_filter)

    if status_filter:
        query = query.filter_by(status=status_filter)

    appointments = query.order_by(Agendamento.scheduled_time).all()

    today = date.today()
    today_q = Agendamento.query.filter_by(scheduled_date=today, unidade_id=g.unidade_id)
    if minha_profissional_id:
        today_q = today_q.filter_by(barber_id=minha_profissional_id)

    stats = {
        "today_total":     today_q.count(),
        "today_pending":   today_q.filter(
                               Agendamento.status.in_(["pending", "confirmed"])
                           ).count(),
        "today_completed": today_q.filter_by(status="completed").count(),
        "today_cancelled": today_q.filter(
                               Agendamento.status.in_(["cancelled", "no_show"])
                           ).count(),
    }

    barbers = (
        Profissional.query.filter_by(is_active=True, unidade_id=g.unidade_id)
        .order_by(Profissional.name).all()
        if current_user.pode_gerenciar else []
    )

    prev_date = str(filter_date - timedelta(days=1))
    next_date = str(filter_date + timedelta(days=1))

    return render_template(
        "appointments/index.html",
        appointments=appointments,
        date_str=date_str,
        filter_date=filter_date,
        prev_date=prev_date,
        next_date=next_date,
        status_filter=status_filter,
        barber_filter=barber_filter,
        stats=stats,
        barbers=barbers,
        STATUS_LABELS=APPOINTMENT_STATUSES,
    )


# ── Admin: Criar agendamento ──────────────────────────────────────────────────
@appointments_bp.route("/new", methods=["GET", "POST"])
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def new():
    form = AppointmentAdminForm()

    customers = Cliente.query.order_by(Cliente.name).all()
    barbers   = Profissional.query.filter_by(is_active=True, unidade_id=g.unidade_id).order_by(Profissional.name).all()
    services  = Servico.query.filter_by(is_active=True, unidade_id=g.unidade_id).order_by(Servico.name).all()
    # Kits de serviço ficam fora do ar na Fase 1-A (ver app/utils/feature_flags.py)
    kits = []

    form.customer_id.choices = [
        (c.id, f"{c.name}" + (f"  ·  {c.phone}" if c.phone else ""))
        for c in customers
    ]
    form.barber_id.choices  = [(b.id, b.name) for b in barbers]
    form.service_id.choices = [(0, "— Selecione —")] + [
        (s.id, f"{s.name}  ·  {s.duration_formatted}  ·  {s.price_formatted}")
        for s in services
    ]

    if not customers:
        flash("Cadastre ao menos um cliente antes de criar um agendamento.", "warning")
    if not barbers:
        flash("Não há profissionais ativos nesta unidade. Cadastre um primeiro.", "warning")
    if not services:
        flash("Não há serviços ativos nesta unidade.", "warning")

    if form.validate_on_submit():
        service_id = form.service_id.data or None

        sched_date = form.scheduled_date.data
        sched_time = datetime.strptime(form.scheduled_time.data.strip(), "%H:%M").time()

        if not service_id:
            flash("Selecione um serviço.", "danger")
            return render_template("appointments/form.html", form=form,
                                   barbers=barbers, services=services, kits=kits)

        if not is_slot_available(form.barber_id.data, service_id, sched_date, sched_time):
            flash("Horário indisponível: o profissional já tem um agendamento neste intervalo.", "danger")
            return render_template("appointments/form.html", form=form,
                                   barbers=barbers, services=services, kits=kits)

        appt = Agendamento(
            empresa_id=g.empresa_id,
            unidade_id=g.unidade_id,
            customer_id=form.customer_id.data,
            barber_id=form.barber_id.data,
            service_id=service_id,
            scheduled_date=sched_date,
            scheduled_time=sched_time,
            notes=(form.notes.data or "").strip() or None,
        )
        db.session.add(appt)

        if SATELLITE_FEATURES_ENABLED:
            db.session.flush()
            from app.subscriptions.service import consume_credit
            consume_credit(form.customer_id.data, service_id, appt.id)

        db.session.commit()
        flash("Agendamento criado com sucesso!", "success")
        return redirect(url_for("appointments.index", date=str(sched_date)))

    return render_template("appointments/form.html", form=form,
                           barbers=barbers, services=services, kits=kits)


# ── Admin / Funcionário: Atualizar status ─────────────────────────────────────
@appointments_bp.route("/<int:appt_id>/status", methods=["POST"])
@login_required
@requer_unidade
def update_status(appt_id: int):
    appt = Agendamento.query.filter_by(id=appt_id, unidade_id=g.unidade_id).first_or_404()

    minha_profissional_id = _minha_profissional_id()
    if minha_profissional_id and appt.barber_id != minha_profissional_id:
        flash("Acesso negado.", "danger")
        return redirect(url_for("appointments.index"))

    new_status = request.form.get("status", "")
    if new_status not in APPOINTMENT_STATUSES:
        flash("Status inválido.", "danger")
        return redirect(url_for("appointments.index", date=str(appt.scheduled_date)))

    old_status = appt.status
    appt.status = new_status

    if new_status == "completed" and appt.customer:
        appt.customer.last_visit = datetime.now(timezone.utc)

    if new_status == "cancelled" and old_status != "cancelled" and SATELLITE_FEATURES_ENABLED:
        from app.subscriptions.service import refund_credit
        refund_credit(appt.id)

    db.session.commit()
    flash(f"Status atualizado para '{APPOINTMENT_STATUSES[new_status]}'.", "success")
    return redirect(url_for("appointments.index", date=str(appt.scheduled_date)))


# ── Admin: Excluir ────────────────────────────────────────────────────────────
@appointments_bp.route("/<int:appt_id>/delete", methods=["POST"])
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def delete(appt_id: int):
    appt = Agendamento.query.filter_by(id=appt_id, unidade_id=g.unidade_id).first_or_404()
    appt_date = str(appt.scheduled_date)

    if SATELLITE_FEATURES_ENABLED:
        from app.subscriptions.service import refund_credit
        refund_credit(appt.id)

    db.session.delete(appt)
    db.session.commit()
    flash("Agendamento removido.", "info")
    return redirect(url_for("appointments.index", date=appt_date))
