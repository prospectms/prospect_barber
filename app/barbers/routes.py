from datetime import datetime, date
from sqlalchemy import func
from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from app.extensions import db
from app.models.profissional import Profissional
from app.models.usuario import Usuario
from app.models.agendamento import Agendamento
from app.models.servico import Servico
from app.barbers.forms import CreateBarberForm, EditBarberForm, ScheduleExceptionForm
from app.utils.decorators import requer_papel, requer_unidade
from app.utils.helpers import save_upload, delete_upload, allowed_file

barbers_bp = Blueprint("barbers", __name__)


def _usuarios_sem_perfil_choices():
    """Usuarios da empresa que ainda não têm Profissional vinculado —
    escolhas para o campo opcional de vínculo em CreateBarberForm."""
    sem_perfil = [u for u in Usuario.query.all() if not u.profissional]
    return [(0, "— Nenhum (sem login) —")] + [(u.id, f"{u.nome} ({u.email})") for u in sem_perfil]


# ── Listagem ──────────────────────────────────────────────────────────────────
@barbers_bp.route("/")
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")

    query = Profissional.query.filter_by(unidade_id=g.unidade_id)
    if q:
        query = query.filter(
            Profissional.name.ilike(f"%{q}%") | Profissional.specialty.ilike(f"%{q}%")
        )
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)

    barbers = query.order_by(Profissional.is_active.desc(), Profissional.name).all()

    base = Profissional.query.filter_by(unidade_id=g.unidade_id)
    summary = {
        "total": base.count(),
        "active": base.filter_by(is_active=True).count(),
        "today_total": sum(b.appointments_today() for b in barbers),
    }

    return render_template(
        "barbers/index.html",
        barbers=barbers, summary=summary, q=q, status=status,
    )


# ── Detalhe ───────────────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>")
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def detail(barber_id: int):
    barber = Profissional.query.filter_by(id=barber_id, unidade_id=g.unidade_id).first_or_404()
    today = date.today()
    month_start = today.replace(day=1)

    revenue_total = float(
        db.session.query(func.sum(Servico.price))
        .join(Agendamento, Agendamento.service_id == Servico.id)
        .filter(
            Agendamento.barber_id == barber_id,
            Agendamento.status == "completed",
        )
        .scalar() or 0
    )
    revenue_month = float(
        db.session.query(func.sum(Servico.price))
        .join(Agendamento, Agendamento.service_id == Servico.id)
        .filter(
            Agendamento.barber_id == barber_id,
            Agendamento.status == "completed",
            Agendamento.scheduled_date >= month_start,
        )
        .scalar() or 0
    )

    stats = {
        "total":         barber.total_appointments,
        "completed":     barber.completed_appointments,
        "this_month":    barber.appointments_this_month(),
        "today":         barber.appointments_today(),
        "revenue_total": revenue_total,
        "revenue_month": revenue_month,
    }

    today_appts = (
        barber.appointments
        .filter_by(scheduled_date=today)
        .order_by(Agendamento.scheduled_time)
        .all()
    )

    recent = (
        barber.appointments
        .order_by(Agendamento.scheduled_date.desc(), Agendamento.scheduled_time.desc())
        .limit(20)
        .all()
    )

    from app.models.barber_schedule_exception import BarberScheduleException
    from datetime import timedelta
    upcoming_window = today + timedelta(days=60)
    exceptions = (
        BarberScheduleException.query
        .filter_by(barber_id=barber_id)
        .filter(BarberScheduleException.date >= today)
        .filter(BarberScheduleException.date <= upcoming_window)
        .order_by(BarberScheduleException.date)
        .all()
    )
    exc_form = ScheduleExceptionForm()

    return render_template(
        "barbers/detail.html",
        barber=barber, stats=stats,
        today_appts=today_appts, recent=recent, today=today,
        exceptions=exceptions, exc_form=exc_form,
    )


# ── Criar ─────────────────────────────────────────────────────────────────────
@barbers_bp.route("/new", methods=["GET", "POST"])
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def new():
    form = CreateBarberForm(unidade_id=g.unidade_id)
    form.usuario_id.choices = _usuarios_sem_perfil_choices()

    if form.validate_on_submit():
        photo_path = None
        photo_file = form.photo.data
        if photo_file and photo_file.filename:
            photo_path = save_upload(photo_file, subfolder="barbers")

        work_start  = _parse_time_safe(form.work_start_time.data)
        work_end    = _parse_time_safe(form.work_end_time.data)
        lunch_start = _parse_time_safe(form.lunch_start.data)
        lunch_end   = _parse_time_safe(form.lunch_end.data)

        if work_start and work_end and work_start >= work_end:
            flash("O horário de início deve ser anterior ao horário de término.", "danger")
            return render_template("barbers/form.html", form=form, action="new")

        import re as _re
        barber = Profissional(
            empresa_id=g.empresa_id,
            unidade_id=g.unidade_id,
            usuario_id=form.usuario_id.data or None,
            name=form.name.data.strip(),
            phone=form.phone.data.strip() or None,
            whatsapp=_re.sub(r'\D', '', form.whatsapp.data or '') or None,
            specialty=form.specialty.data.strip() or None,
            bio=form.bio.data.strip() or None,
            photo=photo_path,
            work_start_time=work_start,
            work_end_time=work_end,
            lunch_start=lunch_start,
            lunch_end=lunch_end,
        )
        db.session.add(barber)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar o profissional. Tente novamente.", "danger")
            return render_template("barbers/form.html", form=form, action="new")

        flash(f"Profissional '{barber.name}' cadastrado com sucesso!", "success")
        return redirect(url_for("barbers.detail", barber_id=barber.id))

    return render_template("barbers/form.html", form=form, action="new")


# ── Editar ────────────────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>/edit", methods=["GET", "POST"])
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def edit(barber_id: int):
    barber = Profissional.query.filter_by(id=barber_id, unidade_id=g.unidade_id).first_or_404()
    form = EditBarberForm(barber_id=barber_id, unidade_id=g.unidade_id)

    if request.method == "GET":
        form.name.data = barber.name
        form.phone.data = barber.phone or ""
        form.whatsapp.data = barber.whatsapp or ""
        form.specialty.data = barber.specialty or ""
        form.bio.data = barber.bio or ""
        form.work_start_time.data = barber.work_start_str
        form.work_end_time.data = barber.work_end_str
        form.lunch_start.data = barber.lunch_start_str
        form.lunch_end.data = barber.lunch_end_str
        form.is_active.data = barber.is_active

    if form.validate_on_submit():
        import re as _re
        barber.name = form.name.data.strip()
        barber.phone = form.phone.data.strip() or None
        barber.whatsapp = _re.sub(r'\D', '', form.whatsapp.data or '') or None
        barber.specialty = form.specialty.data.strip() or None
        barber.bio = form.bio.data.strip() or None
        work_start  = _parse_time_safe(form.work_start_time.data)
        work_end    = _parse_time_safe(form.work_end_time.data)
        lunch_start = _parse_time_safe(form.lunch_start.data)
        lunch_end   = _parse_time_safe(form.lunch_end.data)

        if work_start and work_end and work_start >= work_end:
            flash("O horário de início deve ser anterior ao horário de término.", "danger")
            return render_template("barbers/form.html", form=form, action="edit", barber=barber)

        barber.work_start_time = work_start
        barber.work_end_time = work_end
        barber.lunch_start = lunch_start
        barber.lunch_end = lunch_end
        barber.is_active = form.is_active.data

        if form.remove_photo.data and barber.photo:
            delete_upload(barber.photo)
            barber.photo = None

        photo_file = form.photo.data
        if photo_file and photo_file.filename:
            try:
                new_photo = save_upload(photo_file, subfolder="barbers")
                if barber.photo:
                    delete_upload(barber.photo)
                barber.photo = new_photo
            except (ValueError, RuntimeError) as exc:
                flash(str(exc), "danger")
                return render_template("barbers/form.html", form=form, action="edit", barber=barber)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Erro ao salvar as alterações. Tente novamente.", "danger")
            return render_template("barbers/form.html", form=form, action="edit", barber=barber)

        flash(f"Profissional '{barber.name}' atualizado com sucesso!", "success")
        return redirect(url_for("barbers.detail", barber_id=barber.id))

    return render_template("barbers/form.html", form=form, action="edit", barber=barber)


# ── Ativar / Desativar ────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>/toggle", methods=["POST"])
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def toggle(barber_id: int):
    barber = Profissional.query.filter_by(id=barber_id, unidade_id=g.unidade_id).first_or_404()
    barber.is_active = not barber.is_active
    db.session.commit()
    status = "ativado" if barber.is_active else "desativado"
    flash(f"Profissional '{barber.name}' {status}.", "info")
    return redirect(url_for("barbers.index"))


# ── Excluir ───────────────────────────────────────────────────────────────────
@barbers_bp.route("/<int:barber_id>/delete", methods=["POST"])
@login_required
@requer_papel("dono", "gerente")
@requer_unidade
def delete(barber_id: int):
    barber = Profissional.query.filter_by(id=barber_id, unidade_id=g.unidade_id).first_or_404()

    total = barber.total_appointments
    if total > 0:
        flash(
            f"'{barber.name}' possui {total} agendamento(s) e não pode ser excluído. "
            "Desative-o em vez de excluir para preservar o histórico.",
            "warning",
        )
        return redirect(url_for("barbers.index"))

    name = barber.name
    if barber.photo:
        delete_upload(barber.photo)

    # Não apaga o Usuario vinculado (se houver) — login e perfil profissional
    # têm ciclos de vida independentes desde a Fase 1-A. Gerenciar a conta de
    # acesso é responsabilidade de auth.delete_user, não deste blueprint.
    db.session.delete(barber)
    db.session.commit()
    flash(f"Profissional '{name}' excluído.", "info")
    return redirect(url_for("barbers.index"))


# ── Exceções de agenda ────────────────────────────────────────────────────────
def _can_manage_exceptions(barber_id: int) -> bool:
    if current_user.pode_gerenciar:
        return True
    return (
        current_user.profissional is not None
        and current_user.profissional.id == barber_id
    )


@barbers_bp.route("/<int:barber_id>/exceptions/add", methods=["POST"])
@login_required
@requer_unidade
def add_exception(barber_id: int):
    if not _can_manage_exceptions(barber_id):
        flash("Acesso negado.", "danger")
        return redirect(url_for("barbers.detail", barber_id=barber_id))

    barber = Profissional.query.filter_by(id=barber_id, unidade_id=g.unidade_id).first_or_404()
    form = ScheduleExceptionForm()

    if form.validate_on_submit():
        from app.models.barber_schedule_exception import BarberScheduleException
        from sqlalchemy.exc import IntegrityError

        start_t = _parse_time_safe(form.start_time.data) if form.exception_type.data == "custom_hours" else None
        end_t = _parse_time_safe(form.end_time.data) if form.exception_type.data == "custom_hours" else None

        exc = BarberScheduleException(
            empresa_id=g.empresa_id,
            unidade_id=g.unidade_id,
            barber_id=barber_id,
            date=form.date.data,
            exception_type=form.exception_type.data,
            start_time=start_t,
            end_time=end_t,
            reason=(form.reason.data or "").strip() or None,
        )
        try:
            db.session.add(exc)
            db.session.commit()
            flash(
                f"Exceção adicionada: {form.date.data.strftime('%d/%m/%Y')} — {exc.type_label}.",
                "success",
            )
        except IntegrityError:
            db.session.rollback()
            flash(
                f"Já existe uma exceção cadastrada para {form.date.data.strftime('%d/%m/%Y')}. "
                "Remova a existente antes de adicionar outra.",
                "warning",
            )
    else:
        for field_errors in form.errors.values():
            for e in field_errors:
                flash(e, "danger")

    return redirect(url_for("barbers.detail", barber_id=barber_id))


@barbers_bp.route("/<int:barber_id>/exceptions/<int:exc_id>/remove", methods=["POST"])
@login_required
@requer_unidade
def remove_exception(barber_id: int, exc_id: int):
    if not _can_manage_exceptions(barber_id):
        flash("Acesso negado.", "danger")
        return redirect(url_for("barbers.detail", barber_id=barber_id))

    from app.models.barber_schedule_exception import BarberScheduleException
    exc = BarberScheduleException.query.filter_by(
        id=exc_id, barber_id=barber_id
    ).first_or_404()
    date_str = exc.date.strftime("%d/%m/%Y")
    db.session.delete(exc)
    db.session.commit()
    flash(f"Exceção de {date_str} removida.", "info")
    return redirect(url_for("barbers.detail", barber_id=barber_id))


# ── Helpers internos ──────────────────────────────────────────────────────────
def _parse_time_safe(value: str):
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        return None
