from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, BooleanField,
    SubmitField, SelectField, SelectMultipleField, TextAreaField,
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Optional, ValidationError,
)

from app.models.empresa import slugify


# ── Login ────────────────────────────────────────────────────────────────────
class LoginForm(FlaskForm):
    """Login por e-mail — não existe mais `username` global (Fase 1-A: e-mail
    passou a ser único por empresa, não globalmente). A desambiguação entre
    empresas quando o e-mail é compartilhado acontece na rota, não aqui."""
    email = StringField(
        "E-mail",
        validators=[DataRequired(message="Informe o e-mail."), Email(message="E-mail inválido.")],
    )
    password = PasswordField(
        "Senha",
        validators=[DataRequired(message="Informe a senha.")],
    )
    remember_me = BooleanField("Lembrar-me por 30 dias")
    submit = SubmitField("Entrar")


class SelecionarEmpresaForm(FlaskForm):
    """Passo 2 do login, só aparece quando o e-mail informado existe em mais
    de uma empresa. `usuario_id` chega como hidden pré-validado pela rota
    (lista fechada de IDs que já bateram a senha na etapa anterior)."""
    usuario_id = SelectField("Empresa", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Continuar")


# ── Alterar senha (usuário logado) ────────────────────────────────────────────
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Senha atual",
        validators=[DataRequired(message="Informe a senha atual.")],
    )
    new_password = PasswordField(
        "Nova senha",
        validators=[
            DataRequired(),
            Length(6, 128, message="A senha deve ter no mínimo 6 caracteres."),
        ],
    )
    confirm_password = PasswordField(
        "Confirmar nova senha",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="As senhas não coincidem."),
        ],
    )
    submit = SubmitField("Alterar senha")


# ── Perfil do usuário (nome/email + perfil profissional, se houver) ───────────
class ProfileForm(FlaskForm):
    nome = StringField(
        "Nome completo",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(), Email(message="E-mail inválido.")],
    )
    # Campos exclusivos de quem também é Profissional
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])
    bio = TextAreaField("Bio", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Salvar perfil")

    def __init__(self, usuario_id: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._usuario_id = usuario_id

    def validate_email(self, field):
        # Usuario.query já vem filtrado por g.empresa_id automaticamente
        # (TenantMixin) — não precisa repetir o filtro de empresa aqui.
        from app.models.usuario import Usuario
        existing = Usuario.query.filter(
            Usuario.email == field.data.strip().lower(),
            Usuario.id != self._usuario_id,
        ).first()
        if existing:
            raise ValidationError("Este e-mail já está em uso por outro usuário da sua empresa.")


# ── Criar usuário (dono/gerente) ──────────────────────────────────────────────
class RegisterUserForm(FlaskForm):
    nome = StringField(
        "Nome completo",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(), Email(message="E-mail inválido.")],
    )
    password = PasswordField(
        "Senha",
        validators=[DataRequired(), Length(6, 128, message="Mínimo 6 caracteres.")],
    )
    confirm_password = PasswordField(
        "Confirmar senha",
        validators=[DataRequired(), EqualTo("password", message="As senhas não coincidem.")],
    )
    papel = SelectField(
        "Perfil de acesso",
        choices=[("funcionario", "Funcionário"), ("gerente", "Gerente")],
        default="funcionario",
    )
    # Vínculo de unidades — obrigatório só para funcionário (gerente acessa
    # todas as unidades da empresa por papel, não precisa de vínculo explícito).
    unidades_ids = SelectMultipleField("Unidades", coerce=int, validators=[Optional()])

    # Campos do perfil profissional (opcionais — nem todo usuário vira Profissional)
    criar_perfil_profissional = BooleanField("Também é um profissional que atende na agenda")
    phone = StringField("Telefone", validators=[Optional(), Length(max=20)])
    specialty = StringField("Especialidade", validators=[Optional(), Length(max=100)])

    submit = SubmitField("Criar usuário")

    def validate_email(self, field):
        from app.models.usuario import Usuario
        if Usuario.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("Já existe um usuário com este e-mail na sua empresa.")

    def validate_unidades_ids(self, field):
        if self.papel.data == "funcionario" and not field.data:
            raise ValidationError("Selecione ao menos uma unidade para o funcionário.")


# ── Editar usuário (dono/gerente) ─────────────────────────────────────────────
class EditUserForm(FlaskForm):
    nome = StringField(
        "Nome completo",
        validators=[DataRequired(message="Nome é obrigatório."), Length(2, 100)],
    )
    email = StringField(
        "E-mail",
        validators=[DataRequired(), Email(message="E-mail inválido.")],
    )
    papel = SelectField(
        "Perfil de acesso",
        choices=[("funcionario", "Funcionário"), ("gerente", "Gerente"), ("dono", "Dono")],
    )
    unidades_ids = SelectMultipleField("Unidades", coerce=int, validators=[Optional()])
    ativo = BooleanField("Conta ativa")
    submit = SubmitField("Salvar alterações")

    def __init__(self, usuario_id: int = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._usuario_id = usuario_id

    def validate_email(self, field):
        from app.models.usuario import Usuario
        existing = Usuario.query.filter(
            Usuario.email == field.data.strip().lower(),
            Usuario.id != self._usuario_id,
        ).first()
        if existing:
            raise ValidationError("E-mail já cadastrado para outro usuário da sua empresa.")

    def validate_unidades_ids(self, field):
        if self.papel.data == "funcionario" and not field.data:
            raise ValidationError("Selecione ao menos uma unidade para o funcionário.")


# ── Redefinir senha (dono/gerente redefine para outro usuário) ────────────────
class AdminResetPasswordForm(FlaskForm):
    new_password = PasswordField(
        "Nova senha",
        validators=[DataRequired(), Length(6, 128, message="Mínimo 6 caracteres.")],
    )
    confirm_password = PasswordField(
        "Confirmar senha",
        validators=[DataRequired(), EqualTo("new_password", message="As senhas não coincidem.")],
    )
    submit = SubmitField("Redefinir senha")


# ── Seletor de unidade ativa (painel) ─────────────────────────────────────────
class SelecionarUnidadeForm(FlaskForm):
    unidade_id = SelectField("Unidade", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Trocar unidade")


# ── Cadastro de empresa (público — cria Empresa + Unidade padrão + dono) ──────
class CadastroEmpresaForm(FlaskForm):
    empresa_nome = StringField(
        "Nome da barbearia / empresa",
        validators=[DataRequired(message="Informe o nome da empresa."), Length(2, 150)],
    )
    empresa_documento = StringField(
        "CNPJ ou CPF (opcional)", validators=[Optional(), Length(max=20)],
    )
    empresa_telefone = StringField("Telefone da empresa", validators=[Optional(), Length(max=20)])

    unidade_nome = StringField(
        "Nome da unidade",
        validators=[DataRequired(message="Informe o nome da unidade."), Length(2, 150)],
    )
    unidade_slug = StringField(
        "Endereço da agenda pública (ex: barbearia-do-joao)",
        validators=[DataRequired(message="Escolha um identificador para a unidade."), Length(2, 80)],
    )
    unidade_endereco = StringField("Endereço", validators=[Optional(), Length(max=255)])
    unidade_telefone = StringField("Telefone da unidade", validators=[Optional(), Length(max=20)])

    dono_nome = StringField(
        "Seu nome",
        validators=[DataRequired(message="Informe seu nome."), Length(2, 100)],
    )
    dono_email = StringField(
        "Seu e-mail (login)",
        validators=[DataRequired(), Email(message="E-mail inválido.")],
    )
    dono_password = PasswordField(
        "Senha",
        validators=[DataRequired(), Length(6, 128, message="Mínimo 6 caracteres.")],
    )
    dono_confirm_password = PasswordField(
        "Confirmar senha",
        validators=[DataRequired(), EqualTo("dono_password", message="As senhas não coincidem.")],
    )

    submit = SubmitField("Criar minha empresa")

    def validate_unidade_slug(self, field):
        from app.models.unidade import Unidade
        slug = slugify(field.data)
        if not slug:
            raise ValidationError("Identificador inválido — use letras, números e hífen.")
        field.data = slug
        # Público/anônimo: g.empresa_id não está setado aqui, então o filtro
        # automático de tenant não interfere — a busca já é global de propósito
        # (slug de Unidade é único no sistema inteiro, não por empresa).
        if Unidade.query.filter_by(slug=slug).first():
            raise ValidationError(f"O endereço '{slug}' já está em uso. Escolha outro.")
