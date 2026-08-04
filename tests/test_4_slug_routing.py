"""Categoria 4 — agenda pública e portal do cliente resolvem a unidade
certa pelo slug; slug inexistente ou de unidade inativa dá 404 (nunca 500,
e as duas situações são indistinguíveis pra quem está de fora)."""


def test_agenda_publica_resolve_a_unidade_certa(client, empresa_a, empresa_b):
    r = client.get(f"/agendar/{empresa_a['unidade_slug']}")
    assert r.status_code == 200
    assert empresa_a["servico_nome"] in r.text
    assert empresa_b["servico_nome"] not in r.text

    r = client.get(f"/agendar/{empresa_b['unidade_slug']}")
    assert r.status_code == 200
    assert empresa_b["servico_nome"] in r.text
    assert empresa_a["servico_nome"] not in r.text


def test_agenda_publica_slug_inexistente_da_404(client, empresa_a):
    r = client.get("/agendar/esse-slug-nao-existe-em-lugar-nenhum")
    assert r.status_code == 404


def test_agenda_publica_slug_de_unidade_inativa_da_404(client, empresa_a):
    r = client.get(f"/agendar/{empresa_a['unidade_inativa_slug']}")
    assert r.status_code == 404


def test_agenda_publica_404_de_inexistente_e_inativa_sao_iguais(client, empresa_a):
    """Não pode dar pra saber, de fora, se um slug nunca existiu ou se só
    está desativado — mesmo status code e mesmo corpo de resposta."""
    r_inexistente = client.get("/agendar/esse-slug-nao-existe-em-lugar-nenhum")
    r_inativa = client.get(f"/agendar/{empresa_a['unidade_inativa_slug']}")

    assert r_inexistente.status_code == r_inativa.status_code == 404
    assert "Página não encontrada" in r_inexistente.text
    assert "Página não encontrada" in r_inativa.text


def test_portal_cliente_slug_inexistente_da_404(client):
    r = client.get("/p/esse-slug-nao-existe/lookup")
    assert r.status_code == 404


def test_portal_cliente_slug_de_unidade_inativa_da_404(client, empresa_a):
    r = client.get(f"/p/{empresa_a['unidade_inativa_slug']}/lookup")
    assert r.status_code == 404


def test_portal_cliente_slots_slug_invalido_da_404_nao_500(client):
    """Endpoint AJAX também passa pelo resolver — precisa dar 404, não
    quebrar com 500 por causa de unidade=None mais adiante no código."""
    r = client.get("/p/slug-invalido/slots?barber_id=1&service_id=1&date=2026-01-01")
    assert r.status_code == 404


def test_agenda_publica_slots_slug_invalido_da_404_nao_500(client):
    r = client.get("/agendar/slug-invalido/slots?barber_id=1&service_id=1&date=2026-01-01")
    assert r.status_code == 404
