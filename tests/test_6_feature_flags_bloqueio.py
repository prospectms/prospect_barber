"""Categoria 6 — raffle/subscriptions continuam bloqueados mesmo com
acesso direto por URL (não só escondidos do menu)."""
import pytest


@pytest.fixture
def logado(client, login, empresa_a):
    login(empresa_a["dono_email"], empresa_a["senha"])
    client.post("/auth/unidade", data={"unidade_id": empresa_a["unidade_id"]}, follow_redirects=True)
    return empresa_a


def test_raffle_index_bloqueado(client, logado):
    r = client.get("/raffle/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"] in ("/", "http://localhost/")


def test_raffle_rotas_com_id_bloqueadas_antes_do_lookup(client, logado):
    """Mesmo um raffle_id que nunca existiu deve dar 302 (bloqueado pelo
    decorator) e não 404 (o que exigiria ter rodado o get_or_404 -- ou
    seja, o bloqueio precisa vir ANTES de qualquer acesso a dado)."""
    for method, path in [
        ("get",  "/raffle/999999"),
        ("post", "/raffle/999999/draw"),
        ("post", "/raffle/999999/delete"),
        ("get",  "/raffle/new"),
        ("post", "/raffle/new"),
    ]:
        r = getattr(client, method)(path, follow_redirects=False)
        assert r.status_code == 302, f"{method.upper()} {path} -> {r.status_code} (esperado 302)"


def test_subscriptions_index_bloqueado(client, logado):
    r = client.get("/subscriptions/", follow_redirects=False)
    assert r.status_code == 302


def test_subscriptions_rotas_com_id_bloqueadas_antes_do_lookup(client, logado):
    for method, path in [
        ("get",  "/subscriptions/999999"),
        ("post", "/subscriptions/999999/renew"),
        ("post", "/subscriptions/999999/cancel"),
        ("get",  "/subscriptions/new"),
        ("post", "/subscriptions/new"),
    ]:
        r = getattr(client, method)(path, follow_redirects=False)
        assert r.status_code == 302, f"{method.upper()} {path} -> {r.status_code} (esperado 302)"


def test_bloqueio_mostra_aviso_temporariamente_indisponivel(client, logado):
    r = client.get("/raffle/", follow_redirects=True)
    assert "temporariamente indispon" in r.text.lower()

    r = client.get("/subscriptions/", follow_redirects=True)
    assert "temporariamente indispon" in r.text.lower()


def test_credit_check_ajax_nao_redireciona_so_diz_sem_credito(client, logado):
    """Exceção deliberada: endpoint AJAX chamado de dentro do form de
    agendamento não deve redirecionar (não é navegação de página) -- só
    devolve has_credit=false enquanto a flag estiver desligada."""
    r = client.get("/subscriptions/api/credit-check?customer_id=1&service_id=1", follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json() == {"has_credit": False}


def test_dashboard_e_agenda_publica_nao_mostram_link_de_raffle_subscriptions_para_o_publico(client, empresa_a):
    """Na agenda pública/portal do cliente (sem login) não pode aparecer
    nenhum link/menção a sorteio ou assinatura -- diferente do painel
    autenticado, que mostra e bloqueia só ao clicar."""
    r = client.get(f"/agendar/{empresa_a['unidade_slug']}")
    assert "raffle" not in r.text.lower()
    assert "sorteio" not in r.text.lower()
    assert "assinatura" not in r.text.lower()

    r = client.post(
        f"/p/{empresa_a['unidade_slug']}/lookup",
        data={"cpf": empresa_a["cliente_cpf"]},
        follow_redirects=True,
    )
    assert "raffle" not in r.text.lower()
    assert "sorteio" not in r.text.lower()
