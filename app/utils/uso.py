"""Contagem de uso mensal (Fase 2).

`UsoMensal` só serve pro aviso de aproximação do limite REAL da
plataforma (500 agendamentos/mês por empresa) — nunca bloqueia criação
de agendamento. Ver app/utils/limites.py pros limites que de fato
bloqueiam (unidade/usuário/serviço, via pode_criar()).

Agregado em nível de EMPRESA inteira (soma entre todas as unidades) —
mesma regra de pode_criar(), não confundir com contagem por unidade.
"""
from datetime import date

from app.extensions import db
from app.models.uso_mensal import UsoMensal

LIMITE_REAL_MENSAL = 500
LIMITE_AVISO_MENSAL = 450


def _ano_mes_atual() -> str:
    return date.today().strftime("%Y-%m")


def registrar_agendamento_criado(empresa_id: int) -> None:
    """Incrementa o contador do mês corrente pra essa empresa. Chamar
    SEMPRE que um Agendamento novo é criado de verdade (painel ou agenda
    pública) — NUNCA numa remarcação (agendamento_original_id preenchido:
    o Agendamento cancelado já tinha contado, o novo é o mesmo horário
    reagendado, não um uso adicional).

    Não faz commit — fica na mesma transação de quem chamou, junto com o
    INSERT do Agendamento em si (ou os dois persistem juntos, ou nenhum).
    """
    ano_mes = _ano_mes_atual()
    uso = UsoMensal.query.filter_by(empresa_id=empresa_id, ano_mes=ano_mes).first()
    if uso is None:
        uso = UsoMensal(empresa_id=empresa_id, ano_mes=ano_mes, agendamentos_count=0)
        db.session.add(uso)
    uso.agendamentos_count += 1


def uso_mensal_atual(empresa_id: int) -> int:
    """Quantidade de agendamentos reais (não remarcações) já criados pela
    empresa no mês corrente."""
    uso = UsoMensal.query.filter_by(empresa_id=empresa_id, ano_mes=_ano_mes_atual()).first()
    return uso.agendamentos_count if uso else 0


def aviso_uso_mensal(empresa_id: int) -> dict | None:
    """Dict com o aviso de aproximação do limite (a partir de 450/mês) se
    aplicável, ou None. Nunca bloqueia — só informa o dono/gerente."""
    atual = uso_mensal_atual(empresa_id)
    if atual < LIMITE_AVISO_MENSAL:
        return None
    return {
        "atual": atual,
        "limite": LIMITE_REAL_MENSAL,
        "restante": max(0, LIMITE_REAL_MENSAL - atual),
    }
