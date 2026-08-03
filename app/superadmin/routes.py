from flask import Blueprint, render_template, request, g
from flask_login import login_required, current_user
from app.extensions import db
from app.models.empresa import Empresa
from app.models.unidade import Unidade
from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.agendamento import Agendamento
from app.models.profissional import Profissional
from app.models.servico import Servico
from app.models.audit_log import AuditLog
from app.utils.decorators import requer_superadmin

superadmin_bp = Blueprint("superadmin", __name__)

# Escopo desta fase: visão de LEITURA por empresa + trilha de auditoria.
# Não implementa "entrar como" (impersonar e operar o painel daquela
# empresa) — isso exigiria integrar com o seletor de unidade (unidade
# ativa hoje é resolvida a partir de usuario.empresa_id em vários pontos
# de app/utils/tenant_context.py) e mexer no before_request global. Ficou
# de fora por decisão de escopo, não por esquecimento — dá pra somar depois
# sem quebrar nada do que existe aqui.


def _log_acesso(empresa: Empresa, acao: str, detalhe: str = None) -> None:
    db.session.add(AuditLog(
        usuario_id=current_user.id,
        empresa_id=empresa.id,
        acao=acao,
        detalhe=detalhe,
        ip=request.remote_addr,
    ))
    db.session.commit()


@superadmin_bp.route("/")
@login_required
@requer_superadmin
def empresas():
    # Empresa não é TenantMixin — ela É o tenant, então listagem global é
    # o comportamento correto aqui (só quem chega é @requer_superadmin).
    todas = Empresa.query.order_by(Empresa.nome).all()
    return render_template("superadmin/empresas.html", empresas=todas)


@superadmin_bp.route("/empresas/<int:empresa_id>")
@login_required
@requer_superadmin
def empresa_detail(empresa_id: int):
    empresa = Empresa.query.get_or_404(empresa_id)

    # Todo dado abaixo pertence a uma empresa que não é a do superadmin —
    # setar g.empresa_id para a empresa alvo faz o TenantMixin filtrar
    # automaticamente por ELA (em vez de tenant_bypass(), que desligaria o
    # filtro por completo e misturaria dado de todas as empresas de uma
    # vez — não é o que queremos numa tela de detalhe de UMA empresa).
    g.empresa_id = empresa.id

    unidades = Unidade.query.order_by(Unidade.nome).all()
    usuarios = Usuario.query.order_by(Usuario.papel, Usuario.nome).all()
    stats = {
        "unidades":      len(unidades),
        "usuarios":      len(usuarios),
        "clientes":      Cliente.query.count(),
        "profissionais": Profissional.query.count(),
        "servicos":      Servico.query.count(),
        "agendamentos":  Agendamento.query.count(),
    }

    _log_acesso(empresa, "acessar_empresa", f"Visualizou detalhe de '{empresa.nome}'")

    return render_template(
        "superadmin/empresa_detail.html",
        empresa=empresa, unidades=unidades, usuarios=usuarios, stats=stats,
    )


@superadmin_bp.route("/auditoria")
@login_required
@requer_superadmin
def auditoria():
    # AuditLog não é TenantMixin de propósito (ver app/models/audit_log.py)
    # — superadmin precisa ver a trilha inteira, não só da própria empresa.
    logs = AuditLog.query.order_by(AuditLog.criado_em.desc()).limit(200).all()
    return render_template("superadmin/auditoria.html", logs=logs)
