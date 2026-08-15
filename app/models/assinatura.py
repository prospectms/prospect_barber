from datetime import datetime, timezone

from app.extensions import db
from app.models.tenant import TenantMixin

STATUS_VALORES = ["pendente", "ativa", "inadimplente", "cancelada"]


class Assinatura(TenantMixin, db.Model):
    """Fonte real do status de pagamento da Empresa (Fase 3) — Empresa.
    status_assinatura é só espelho, escrito em `sincronizar_status_empresa()`
    sempre que este `status` muda. Nenhuma lógica nova deve ler
    Empresa.status_assinatura diretamente.

    1:1 com Empresa por ora (uma empresa tem no máximo uma assinatura ativa
    na plataforma). asaas_subscription_id é único: é a chave usada pelo
    webhook pra encontrar esta linha, já que o webhook roda fora de
    request/tenant context (current_empresa_id() é None lá, então o filtro
    automático de TenantMixin vira no-op — ok pra esse caso específico).

    status='pendente': checkout criado, aguardando o primeiro webhook
    PAYMENT_CONFIRMED/PAYMENT_RECEIVED. Empresa.plano_id só muda depois
    disso (decisão explícita: zero janela de acesso pago sem pagamento
    confirmado).
    status='inadimplente': PAYMENT_OVERDUE recebido. inadimplente_desde
    marca o início da contagem pro downgrade automático (dia 8, ver job
    diário). Empresa.plano_id NÃO muda neste momento — só no downgrade.
    """
    __tablename__ = "assinaturas"

    id = db.Column(db.Integer, primary_key=True)

    asaas_customer_id = db.Column(db.String(50), nullable=False)
    asaas_subscription_id = db.Column(db.String(50), unique=True, nullable=False, index=True)

    status = db.Column(db.String(20), nullable=False, default="pendente")
    plano_id = db.Column(db.Integer, db.ForeignKey("planos.id"), nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    periodicidade = db.Column(db.String(10), nullable=False)  # 'mensal'|'anual'
    forma_pagamento = db.Column(db.String(10), nullable=False)  # 'pix'|'cartao'

    inadimplente_desde = db.Column(db.DateTime, nullable=True)
    proximo_vencimento = db.Column(db.Date, nullable=True)

    # invoiceUrl da primeira cobrança gerada junto com a assinatura (ver
    # asaas_client.get_first_payment_invoice_url) -- é o único link real
    # de pagamento (Pix/Boleto) que a Asaas devolve; a resposta de criação
    # da assinatura em si não traz QR code/link nenhum. Sem isso o dono
    # não tem como pagar pela nossa própria UI. Capturado uma vez em
    # iniciar_checkout(), não é atualizado a cada ciclo de renovação.
    invoice_url = db.Column(db.String(255), nullable=True)

    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    atualizado_em = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    empresa = db.relationship("Empresa")
    plano = db.relationship("Plano")

    def __repr__(self) -> str:
        return f"<Assinatura empresa={self.empresa_id} status={self.status!r}>"


class AsaasWebhookEvent(db.Model):
    """Registro de idempotência: um evento de webhook do Asaas (identificado
    pelo próprio `id` que o Asaas manda no payload) só é aplicado uma vez.

    Não é TenantMixin — o webhook chega sem tenant context (é o Asaas
    batendo direto na rota pública), e o event_id já é globalmente único
    (vem do Asaas, não é gerado por nós). Sem relação com Empresa: a
    resolução de qual Assinatura/Empresa o evento afeta acontece via
    asaas_subscription_id dentro do payload, não aqui.
    """
    __tablename__ = "asaas_webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    asaas_event_id = db.Column(db.String(60), unique=True, nullable=False, index=True)
    evento = db.Column(db.String(40), nullable=False)
    recebido_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<AsaasWebhookEvent {self.asaas_event_id} {self.evento!r}>"
