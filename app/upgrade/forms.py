import re

from flask_wtf import FlaskForm
from wtforms import RadioField, StringField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

# Celular brasileiro: 11 dígitos (DDD + 9 + 8 dígitos do assinante), só
# dígitos após remover formatação. DDD checado só por faixa (11-99), sem
# lista fechada dos códigos realmente atribuídos pela ANATEL -- manter essa
# lista seria mais frágil que o ganho (DDD pode ser realocado). "9 na
# frente" é regra oficial do número móvel desde 2016. Rejeitar assinante
# com todos os dígitos iguais cobre o caso real que a própria Asaas
# rejeitou no smoke test contra o sandbox (2026-08-12): "11999999999" tem
# formato estruturalmente válido (11 dígitos, DDD ok, começa com 9) mas é
# claramente forjado -- a Asaas rejeita isso do lado dela com um erro cru
# em português; aqui a gente barra antes de gastar a chamada de API, com
# mensagem nossa.
_DDD_MIN, _DDD_MAX = 11, 99


def _celular_valido(digitos: str) -> bool:
    if len(digitos) != 11:
        return False
    if not (_DDD_MIN <= int(digitos[:2]) <= _DDD_MAX):
        return False
    numero_assinante = digitos[2:]
    if numero_assinante[0] != "9":
        return False
    if len(set(numero_assinante)) == 1:
        return False
    return True


class CheckoutForm(FlaskForm):
    periodicidade = RadioField(
        "Periodicidade",
        choices=[("mensal", "Mensal"), ("anual", "Anual")],
        validators=[DataRequired(message="Escolha a periodicidade.")],
    )
    forma_pagamento = RadioField(
        "Forma de pagamento",
        choices=[("pix", "Pix"), ("cartao", "Cartão de crédito")],
        validators=[DataRequired(message="Escolha a forma de pagamento.")],
    )

    # Dados do cliente Asaas (empresa) -- pré-preenchidos quando já existem
    # em Empresa, mas sempre editáveis: são obrigatórios pra criar o cliente
    # na Asaas e a empresa pode não ter preenchido no cadastro inicial.
    documento = StringField(
        "CNPJ/CPF da empresa",
        validators=[DataRequired(message="CNPJ/CPF é obrigatório para cobrança."), Length(max=20)],
    )
    email = StringField(
        "E-mail de cobrança",
        validators=[DataRequired(message="E-mail é obrigatório."), Email(message="E-mail inválido."), Length(max=120)],
    )
    telefone = StringField("Telefone", validators=[Optional(), Length(max=20)])

    def validate_telefone(self, field):
        if not field.data:
            return
        digitos = re.sub(r"\D", "", field.data)
        if not _celular_valido(digitos):
            raise ValidationError(
                "Celular inválido. Informe DDD + número com 9 dígitos, "
                "começando em 9 (ex.: 11987654321)."
            )
        field.data = digitos

    # Campos exigidos só quando forma_pagamento == 'cartao' -- validados
    # manualmente na rota (DataRequired incondicional bloquearia o Pix).
    card_holder_name = StringField("Nome impresso no cartão", validators=[Optional(), Length(max=100)])
    card_number = StringField("Número do cartão", validators=[Optional(), Length(max=20)])
    card_expiry_month = StringField("Mês de validade", validators=[Optional(), Length(max=2)])
    card_expiry_year = StringField("Ano de validade", validators=[Optional(), Length(max=4)])
    card_ccv = StringField("CVV", validators=[Optional(), Length(max=4)])
    card_postal_code = StringField("CEP do titular", validators=[Optional(), Length(max=10)])
    card_address_number = StringField("Número do endereço", validators=[Optional(), Length(max=10)])

    def validate_campos_cartao(self) -> list:
        """Chamado explicitamente na rota (não é validate_<field> do WTForms)
        porque a obrigatoriedade depende do valor de forma_pagamento.
        Retorna lista de mensagens de erro; vazia = ok."""
        if self.forma_pagamento.data != "cartao":
            return []
        erros = []
        obrigatorios = [
            (self.card_holder_name, "Nome impresso no cartão é obrigatório."),
            (self.card_number, "Número do cartão é obrigatório."),
            (self.card_expiry_month, "Mês de validade é obrigatório."),
            (self.card_expiry_year, "Ano de validade é obrigatório."),
            (self.card_ccv, "CVV é obrigatório."),
            (self.card_postal_code, "CEP do titular é obrigatório."),
            (self.card_address_number, "Número do endereço é obrigatório."),
            (self.telefone, "Telefone é obrigatório para pagamento com cartão."),
        ]
        for campo, mensagem in obrigatorios:
            if not (campo.data or "").strip():
                erros.append(mensagem)
        return erros
