from flask_wtf import FlaskForm
from wtforms import RadioField, StringField
from wtforms.validators import DataRequired, Email, Length, Optional


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
