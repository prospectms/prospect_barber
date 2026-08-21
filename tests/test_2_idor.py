"""Categoria 2 — acesso direto por ID a recurso de outra empresa em toda
rota de detalhe/edição/exclusão deve dar 404 (nunca 403 — não revela que
o ID existe em outro tenant)."""
import pytest


@pytest.fixture
def logado_empresa_a(client, login, empresa_a, empresa_b):
    """Loga como dono da empresa A com a unidade dela selecionada. empresa_b
    é aceito como parâmetro só para garantir que a fixture (e os IDs que os
    testes vão usar) já existem antes do request."""
    login(empresa_a["dono_email"], empresa_a["senha"])
    client.post("/auth/unidade", data={"unidade_id": empresa_a["unidade_id"]}, follow_redirects=True)
    return empresa_a, empresa_b


def _idor_cases(b):
    """(method, path, descrição) — todos usando IDs que pertencem à empresa B,
    acessados com a sessão logada da empresa A."""
    return [
        ("get",  f"/barbers/{b['prof_id']}", "barbers.detail"),
        ("get",  f"/barbers/{b['prof_id']}/edit", "barbers.edit (GET)"),
        ("post", f"/barbers/{b['prof_id']}/edit", "barbers.edit (POST)"),
        ("post", f"/barbers/{b['prof_id']}/delete", "barbers.delete"),
        ("post", f"/barbers/{b['prof_id']}/toggle", "barbers.toggle"),
        ("get",  f"/customers/{b['cliente_id']}", "customers.detail"),
        ("get",  f"/customers/{b['cliente_id']}/edit", "customers.edit (GET)"),
        ("post", f"/customers/{b['cliente_id']}/delete", "customers.delete"),
        ("get",  f"/services/{b['servico_id']}/edit", "services.edit (GET)"),
        ("post", f"/services/{b['servico_id']}/delete", "services.delete"),
        ("post", f"/services/{b['servico_id']}/toggle", "services.toggle"),
        ("post", f"/appointments/{b['agendamento_id']}/status", "appointments.update_status"),
        ("post", f"/appointments/{b['agendamento_id']}/delete", "appointments.delete"),
        ("get",  f"/auth/users/{b['dono_id']}/edit", "auth.edit_user (GET)"),
        ("post", f"/auth/users/{b['dono_id']}/delete", "auth.delete_user"),
        ("post", f"/auth/users/{b['dono_id']}/toggle", "auth.toggle_user"),
        ("get",  f"/auth/users/{b['dono_id']}/reset-password", "auth.reset_password (GET)"),
        ("post", f"/auth/users/{b['dono_id']}/unlock", "auth.unlock_user"),
        ("get",  f"/unidades/{b['unidade2_id']}/edit", "unidades.edit (GET)"),
        ("post", f"/unidades/{b['unidade2_id']}/edit", "unidades.edit (POST)"),
        ("post", f"/unidades/{b['unidade2_id']}/toggle", "unidades.toggle"),
        ("post", f"/unidades/{b['unidade2_id']}/delete", "unidades.delete"),
    ]


def test_idor_todas_as_rotas_de_detalhe_dao_404(client, logado_empresa_a):
    _empresa_a, empresa_b = logado_empresa_a
    falhas = []
    for method, path, descricao in _idor_cases(empresa_b):
        r = getattr(client, method)(path, follow_redirects=False)
        if r.status_code != 404:
            falhas.append((descricao, path, r.status_code))

    assert not falhas, "Rotas que NÃO retornaram 404 pra recurso de outra empresa:\n" + "\n".join(
        f"  {d} [{p}] -> {s}" for d, p, s in falhas
    )


def test_idor_nunca_da_403(client, logado_empresa_a):
    """Confirma explicitamente que a resposta é 404, não 403 — 403 revelaria
    que o recurso existe (só que sem permissão); 404 não revela nada."""
    _empresa_a, empresa_b = logado_empresa_a
    for method, path, descricao in _idor_cases(empresa_b):
        r = getattr(client, method)(path, follow_redirects=False)
        assert r.status_code != 403, f"{descricao} [{path}] retornou 403 (deveria ser 404)"


def test_idor_portal_cliente_agendamento_de_outra_unidade(client, empresa_a, empresa_b):
    """Slug da unidade A + appt_id que pertence à unidade B -> 404, mesmo
    sendo rota pública (sem login)."""
    r = client.get(
        f"/p/{empresa_a['unidade_slug']}/appointment/{empresa_b['agendamento_id']}/reschedule"
    )
    assert r.status_code == 404

    r = client.post(
        f"/p/{empresa_a['unidade_slug']}/appointment/{empresa_b['agendamento_id']}/confirm",
        data={"cpf": empresa_b["cliente_cpf"]},
    )
    assert r.status_code == 404
