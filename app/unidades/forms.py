from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.models.empresa import slugify


class UnidadeForm(FlaskForm):
    nome = StringField(
        "Nome da unidade",
        validators=[DataRequired(message="Informe o nome da unidade."), Length(2, 150)],
    )
    slug = StringField(
        "Endereço da agenda pública (ex: barbearia-do-joao-zona-sul)",
        validators=[DataRequired(message="Escolha um identificador para a unidade."), Length(2, 80)],
    )
    endereco = StringField("Endereço", validators=[Optional(), Length(max=255)])
    telefone = StringField("Telefone", validators=[Optional(), Length(max=20)])

    submit = SubmitField("Criar unidade")

    def validate_slug(self, field):
        from app.extensions import db
        slug = slugify(field.data)
        if not slug:
            raise ValidationError("Identificador inválido — use letras, números e hífen.")
        field.data = slug
        # Slug de Unidade é único GLOBAL (não por empresa) — usado na URL
        # pública /agendar/<slug>. Diferente de CadastroEmpresaForm (onde
        # essa mesma checagem roda pré-login, sem g.empresa_id setado),
        # aqui o dono já está autenticado — Unidade.query.filter_by(...)
        # sairia filtrado só pra empresa dele pelo TenantMixin, e um slug
        # em uso por OUTRA empresa passaria batido no formulário (o INSERT
        # ainda falharia pela unique constraint da coluna, só que com um
        # erro feio em vez de uma mensagem de validação limpa). SQL bruto
        # (não ORM) escapa do with_loader_criteria de propósito — não é o
        # mesmo caso de tenant_bypass() (reservado a rotas de superadmin):
        # aqui só estamos checando se uma STRING pública já existe, não
        # lendo dado de outra empresa.
        existe = db.session.execute(
            db.text("SELECT 1 FROM unidades WHERE slug = :slug"), {"slug": slug}
        ).first()
        if existe:
            raise ValidationError(f"O endereço '{slug}' já está em uso. Escolha outro.")
