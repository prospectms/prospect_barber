from app.extensions import db

PLANO_NOMES = ["free", "essencial", "pro", "ilimitado"]


class Plano(db.Model):
    """Plano de assinatura da PLATAFORMA (Empresa paga pra usar o Prospect
    Barber) — não confundir com `SubscriptionPlan`, que é o clube de
    assinaturas que a própria barbearia oferece pros clientes dela.

    Não é TenantMixin: é tabela de referência global (como uma tabela de
    preços), não dado de uma empresa — mesma categoria de `Empresa` em si.

    max_unidades/max_usuarios/max_servicos nulos = sem limite (planos
    pagos superiores). Contagem de uso sempre em nível de EMPRESA inteira
    (soma entre todas as unidades), nunca por unidade isolada — ver
    app/utils/limites.py.
    """
    __tablename__ = "planos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), nullable=False, unique=True)  # free|essencial|pro|ilimitado

    max_unidades = db.Column(db.Integer, nullable=True)
    max_usuarios = db.Column(db.Integer, nullable=True)
    max_servicos = db.Column(db.Integer, nullable=True)

    preco_mensal = db.Column(db.Numeric(10, 2), nullable=False)
    preco_anual = db.Column(db.Numeric(10, 2), nullable=False)

    # Lista de strings (ex.: ["relatorios", "clube_recorrencia"]) — checada
    # por @requer_modulo. Guardado como JSON puro, sem model à parte: não
    # há necessidade de consultar/filtrar por módulo individualmente.
    modulos_incluidos = db.Column(db.JSON, nullable=False, default=list)

    empresas = db.relationship("Empresa", back_populates="plano")

    @property
    def preco_mensal_formatado(self) -> str:
        return f"R$ {self.preco_mensal:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @property
    def preco_anual_formatado(self) -> str:
        return f"R$ {self.preco_anual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def tem_modulo(self, nome_modulo: str) -> bool:
        return nome_modulo in (self.modulos_incluidos or [])

    def __repr__(self) -> str:
        return f"<Plano {self.nome}>"
