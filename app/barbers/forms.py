from datetime import datetime
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, TextAreaField,
    BooleanField, SubmitField, SelectField, DateField,
)
from wtforms.validators import (
    DataRequired, Length, Optional, ValidationError,
)


def _parse_time(value: str):
    return datetime.strptime(value.strip(), "%H:%M").time()


# ── Formulário de criação (perfil profissional — login é vínculo à parte) ─────
class CreateBarberForm(FlaskForm):
    """Cria um Profissional. Não pede credenciais de login — usuario_id é
    nullable desde a Fase 1-A (relaxado de propósito: um profissional pode
    existir só para aparecer na agenda, sem conta própria). Vínculo com um
    Usuario existente é opcional, feito em `usuario_id` (contas da empresa
    que ainda não têm perfil profissional — ver auth.new_user para criar
    login+perfil junto)."""

    usuario_id = SelectField(
        "Vincular a um usuário existente (opcional)",
        coerce=int, validators=[Optional()],
    )

    name = StringField(
        "Nome completo",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    whatsapp = StringField("WhatsApp", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])
    bio = TextAreaField("Bio / Apresentação", validators=[Optional(), Length(max=500)])

    work_start_time = StringField("Início do atendimento", validators=[Optional()])
    work_end_time = StringField("Fim do atendimento", validators=[Optional()])
    lunch_start = StringField("Início do almoço", validators=[Optional()])
    lunch_end = StringField("Fim do almoço", validators=[Optional()])

    photo = FileField(
        "Foto do profissional",
        validators=[FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Apenas imagens.")],
    )

    submit = SubmitField("Cadastrar profissional")

    def __init__(self, unidade_id: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._unidade_id = unidade_id

    def validate_usuario_id(self, field):
        if not field.data:
            return
        from app.models.usuario import Usuario
        usuario = Usuario.query.get(field.data)
        if not usuario:
            raise ValidationError("Usuário inválido.")
        if usuario.profissional:
            raise ValidationError("Este usuário já tem um perfil de profissional vinculado.")

    def validate_name(self, field):
        from app.models.profissional import Profissional
        from app.extensions import db
        if Profissional.query.filter(
            Profissional.unidade_id == self._unidade_id,
            db.func.lower(Profissional.name) == field.data.strip().lower(),
        ).first():
            raise ValidationError("Já existe um profissional com este nome nesta unidade.")

    def validate_work_start_time(self, field):
        if not field.data:
            return
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 08:00).")

    def validate_work_end_time(self, field):
        if not field.data:
            return
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 18:00).")
        if self.work_start_time.data:
            try:
                start = _parse_time(self.work_start_time.data)
                if end <= start:
                    raise ValidationError("Horário de fim deve ser posterior ao de início.")
            except ValueError:
                pass

    def validate_lunch_start(self, field):
        if not field.data:
            return
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 12:00).")

    def validate_lunch_end(self, field):
        if not field.data:
            if self.lunch_start.data:
                raise ValidationError("Informe o fim do almoço.")
            return
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 13:00).")
        if self.lunch_start.data:
            try:
                start = _parse_time(self.lunch_start.data)
                if end <= start:
                    raise ValidationError("Fim do almoço deve ser posterior ao início.")
            except ValueError:
                pass


# ── Formulário de edição (somente perfil, sem credenciais) ────────────────────
class EditBarberForm(FlaskForm):

    name = StringField(
        "Nome completo",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    whatsapp = StringField("WhatsApp", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])
    bio = TextAreaField("Bio / Apresentação", validators=[Optional(), Length(max=500)])

    work_start_time = StringField("Início do atendimento", validators=[Optional()])
    work_end_time = StringField("Fim do atendimento", validators=[Optional()])
    lunch_start = StringField("Início do almoço", validators=[Optional()])
    lunch_end = StringField("Fim do almoço", validators=[Optional()])

    photo = FileField(
        "Nova foto",
        validators=[FileAllowed(["jpg", "jpeg", "png", "webp", "gif"], "Apenas imagens.")],
    )
    remove_photo = BooleanField("Remover foto atual")
    is_active = BooleanField("Profissional ativo")

    submit = SubmitField("Salvar alterações")

    def __init__(self, barber_id: int = None, unidade_id: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._barber_id = barber_id
        self._unidade_id = unidade_id

    def validate_name(self, field):
        from app.models.profissional import Profissional
        from app.extensions import db
        existing = Profissional.query.filter(
            Profissional.unidade_id == self._unidade_id,
            db.func.lower(Profissional.name) == field.data.strip().lower(),
            Profissional.id != self._barber_id,
        ).first()
        if existing:
            raise ValidationError("Já existe um profissional com este nome nesta unidade.")

    def validate_work_start_time(self, field):
        if not field.data:
            return
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 08:00).")

    def validate_work_end_time(self, field):
        if not field.data:
            return
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 18:00).")
        if self.work_start_time.data:
            try:
                start = _parse_time(self.work_start_time.data)
                if end <= start:
                    raise ValidationError("Horário de fim deve ser posterior ao de início.")
            except ValueError:
                pass

    def validate_lunch_start(self, field):
        if not field.data:
            return
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 12:00).")

    def validate_lunch_end(self, field):
        if not field.data:
            if self.lunch_start.data:
                raise ValidationError("Informe o fim do almoço.")
            return
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM  (ex: 13:00).")
        if self.lunch_start.data:
            try:
                start = _parse_time(self.lunch_start.data)
                if end <= start:
                    raise ValidationError("Fim do almoço deve ser posterior ao início.")
            except ValueError:
                pass


# ── Exceção de agenda ─────────────────────────────────────────────────────────
class ScheduleExceptionForm(FlaskForm):

    date = DateField("Data", validators=[DataRequired(message="Selecione uma data.")])
    exception_type = SelectField(
        "Tipo",
        choices=[("day_off", "Folga"), ("custom_hours", "Horário especial")],
        validators=[DataRequired()],
    )
    start_time = StringField("Início", validators=[Optional()])
    end_time = StringField("Fim", validators=[Optional()])
    reason = StringField("Motivo (opcional)", validators=[Optional(), Length(max=255)])

    submit = SubmitField("Salvar exceção")

    def validate_date(self, field):
        from datetime import date
        if field.data and field.data < date.today():
            raise ValidationError("A data não pode ser no passado.")

    def validate_start_time(self, field):
        if self.exception_type.data != "custom_hours":
            return
        if not field.data:
            raise ValidationError("Informe o horário de início.")
        try:
            _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM.")

    def validate_end_time(self, field):
        if self.exception_type.data != "custom_hours":
            return
        if not field.data:
            raise ValidationError("Informe o horário de fim.")
        try:
            end = _parse_time(field.data)
        except ValueError:
            raise ValidationError("Use o formato HH:MM.")
        if self.start_time.data:
            try:
                start = _parse_time(self.start_time.data)
                if end <= start:
                    raise ValidationError("Horário de fim deve ser posterior ao de início.")
            except ValueError:
                pass
