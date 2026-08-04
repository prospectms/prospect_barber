from datetime import date, datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from app.extensions import db
from app.models.agendamento import Agendamento
from app.models.profissional import Profissional
from app.models.cliente import Cliente
from app.models.servico import Servico
from app.appointments.forms import BookingForm
from app.appointments.availability import get_available_slots, is_slot_available
from app.utils.tenant_context import resolver_unidade_por_slug
from app.utils.feature_flags import SATELLITE_FEATURES_ENABLED
from app.utils.uso import registrar_agendamento_criado

booking_bp = Blueprint("booking", __name__)

# Agenda pública por unidade — /agendar/<slug-da-unidade>. Sem login. Toda
# rota resolve a unidade pelo slug ANTES de qualquer query (isso é o que
# popula g.empresa_id/g.unidade_id e liga o filtro automático do
# TenantMixin — ver resolver_unidade_por_slug em app/utils/tenant_context.py).
#
# Kits de serviço (ServiceKit) não aparecem aqui — SATELLITE_FEATURES_ENABLED
# está False nesta fase (ver app/utils/feature_flags.py).


@booking_bp.route("/<slug>", methods=["GET", "POST"])
def book(slug: str):
    unidade = resolver_unidade_por_slug(slug)

    services = Servico.query.filter_by(is_active=True, unidade_id=unidade.id).order_by(Servico.name).all()
    barbers = Profissional.query.filter_by(is_active=True, unidade_id=unidade.id).order_by(Profissional.name).all()
    kits = []  # ver nota acima

    form = BookingForm()

    if form.validate_on_submit():
        service_id_raw = form.service_id.data

        missing = []
        if not service_id_raw:
            missing.append("serviço")
        if not form.barber_id.data:
            missing.append("barbeiro")
        if not form.scheduled_date.data:
            missing.append("data")
        if not form.scheduled_time.data:
            missing.append("horário")
        if missing:
            flash(f"Por favor, selecione: {', '.join(missing)}.", "warning")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits, unidade=unidade)

        try:
            sched_date = date.fromisoformat(form.scheduled_date.data)
            sched_time = datetime.strptime(form.scheduled_time.data, "%H:%M").time()
            barber_id  = int(form.barber_id.data)
            service_id = int(service_id_raw)
        except (ValueError, TypeError):
            flash("Dados inválidos. Por favor, refaça a seleção.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits, unidade=unidade)

        # barber_id/service_id chegam do form (poderiam ser adulterados no
        # POST) — confirmam que pertencem à unidade resolvida antes de usar,
        # senão um slug válido poderia agendar num profissional/serviço de
        # outra unidade (ou outra empresa).
        barber = Profissional.query.filter_by(id=barber_id, unidade_id=unidade.id, is_active=True).first()
        service = Servico.query.filter_by(id=service_id, unidade_id=unidade.id, is_active=True).first()
        if not barber or not service:
            flash("Profissional ou serviço inválido para esta unidade.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits, unidade=unidade)

        if not is_slot_available(barber_id, service_id, sched_date, sched_time):
            flash("Este horário não está mais disponível. Por favor, escolha outro.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits, unidade=unidade)

        try:
            customer, _ = Cliente.get_or_create(
                empresa_id=unidade.empresa_id,
                name=form.customer_name.data,
                phone=form.customer_phone.data,
                cpf=form.customer_cpf.data,
                unidade_origem_id=unidade.id,
            )
            db.session.flush()

            appt = Agendamento(
                empresa_id=unidade.empresa_id,
                unidade_id=unidade.id,
                customer_id=customer.id,
                barber_id=barber_id,
                service_id=service_id,
                scheduled_date=sched_date,
                scheduled_time=sched_time,
                notes=(form.notes.data or "").strip() or None,
            )
            db.session.add(appt)
            registrar_agendamento_criado(unidade.empresa_id)  # agendamento_original_id=None -> conta
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar o agendamento. Por favor, tente novamente.", "danger")
            return render_template("appointments/book.html",
                                   form=form, services=services, barbers=barbers, kits=kits, unidade=unidade)

        return redirect(url_for("booking.book_success", slug=slug, appt_id=appt.id))

    return render_template("appointments/book.html",
                           form=form, services=services, barbers=barbers, kits=kits, unidade=unidade)


@booking_bp.route("/<slug>/slots")
def slots(slug: str):
    unidade = resolver_unidade_por_slug(slug)

    barber_id  = request.args.get("barber_id",  type=int)
    service_id = request.args.get("service_id", type=int)
    date_str   = request.args.get("date", "")

    if not barber_id or not date_str or not service_id:
        return jsonify({"slots": []})

    # barber_id vem de query string pública — confirma que é desta unidade
    # antes de calcular disponibilidade (senão dá pra enumerar agenda de
    # profissionais de outras unidades/empresas por tentativa).
    barber = Profissional.query.filter_by(id=barber_id, unidade_id=unidade.id).first()
    if not barber:
        return jsonify({"slots": []})

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"slots": []})

    if target_date < date.today():
        return jsonify({"slots": []})

    from app.models.barber_schedule_exception import BarberScheduleException
    exc = BarberScheduleException.query.filter_by(
        barber_id=barber_id, date=target_date
    ).first()
    if exc and exc.exception_type == "day_off":
        return jsonify({"slots": [], "reason": "day_off"})

    available = get_available_slots(barber_id, service_id, target_date)
    return jsonify({"slots": [t.strftime("%H:%M") for t in available]})


@booking_bp.route("/<slug>/sucesso/<int:appt_id>")
def book_success(slug: str, appt_id: int):
    unidade = resolver_unidade_por_slug(slug)

    appt = Agendamento.query.filter_by(id=appt_id, unidade_id=unidade.id).first_or_404()

    credit_items = []
    if SATELLITE_FEATURES_ENABLED:
        from app.models.subscription import SubscriptionCreditUsage, SubscriptionCreditBalance
        usages = SubscriptionCreditUsage.query.filter_by(appointment_id=appt_id).all()
        for usage in usages:
            balance = SubscriptionCreditBalance.query.filter_by(
                subscription_id=usage.subscription_id,
                service_id=usage.service_id,
            ).first()
            credit_items.append({
                "plan_name": (
                    usage.subscription.plan.name
                    if usage.subscription and usage.subscription.plan
                    else "Clube de Assinaturas"
                ),
                "service_name": usage.service.name if usage.service else "—",
                "remaining": balance.remaining_credits if balance else 0,
                "total": balance.total_credits if balance else 0,
            })

    return render_template("appointments/book_success.html",
                           appt=appt, credit_items=credit_items, unidade=unidade)
