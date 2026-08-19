"""adiciona assinaturas.invoice_url (Fase 3 - smoke test sandbox)

Achado no smoke test contra o sandbox real do Asaas (2026-08-12): a
resposta de criação da assinatura NUNCA traz QR code/link de pagamento --
o único jeito de o cliente pagar de fato é o invoiceUrl da primeira
cobrança (GET /v3/payments?subscription=<id>), que precisa ser buscado à
parte logo após criar a assinatura e guardado, pra exibir um botão "Pagar
agora" na tela de status. Sem isso o checkout inteiro era decorativo.

Coluna nova e nullable -- sem backfill (linhas existentes de Assinatura,
se houver, nunca tiveram esse link capturado; ficam com invoice_url NULL,
o que já é tratado no template como "não conseguimos recuperar o link").

Revision ID: 3f1a9d6e8b2c
Revises: 2b7e4f9c6a1d
Create Date: 2026-08-13 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '3f1a9d6e8b2c'
down_revision = '2b7e4f9c6a1d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('assinaturas', sa.Column('invoice_url', sa.String(length=255), nullable=True))


def downgrade():
    # batch_alter_table: DROP COLUMN só é nativo em SQLite >= 3.35 --
    # não vale depender da versão do sqlite3 do ambiente. Transparente no
    # Postgres (roda como ALTER TABLE direto, sem recriar nada).
    with op.batch_alter_table('assinaturas') as batch_op:
        batch_op.drop_column('invoice_url')
