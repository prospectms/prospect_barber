from app.extensions import db


class UsoMensal(db.Model):
    """Contador de agendamentos por empresa/mês — usado só pro aviso de
    aproximação do limite real da plataforma (500/mês), nunca pra bloquear
    criação de agendamento (ver app/utils/limites.py).

    Agregado em nível de EMPRESA inteira (soma entre todas as unidades),
    não por unidade — bate com como os planos definem limite (não existe
    "limite de agendamento por unidade" nesta fase).

    Não é TenantMixin por decisão de simetria com Plano/Empresa: é
    incrementado sempre via empresa_id explícito (ver hook de criação em
    appointments/routes.py e booking/routes.py), nunca listado/filtrado
    numa rota comum que precisaria do filtro automático.
    """
    __tablename__ = "uso_mensal"

    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresas.id"), nullable=False, index=True)
    ano_mes = db.Column(db.String(7), nullable=False)  # "AAAA-MM"
    agendamentos_count = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("empresa_id", "ano_mes", name="uq_uso_mensal_empresa_mes"),
    )

    def __repr__(self) -> str:
        return f"<UsoMensal empresa={self.empresa_id} {self.ano_mes} count={self.agendamentos_count}>"
