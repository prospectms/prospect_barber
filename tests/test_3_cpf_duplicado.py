"""Categoria 3 — mesmo CPF em duas empresas diferentes não colide; cada
Cliente é resolvido dentro da própria empresa. empresa_a/empresa_b (ver
conftest.py) já são criadas de propósito com o MESMO CPF."""


def test_fixtures_tem_mesmo_cpf_em_empresas_diferentes(empresa_a, empresa_b):
    assert empresa_a["cliente_cpf"] == empresa_b["cliente_cpf"]
    assert empresa_a["empresa_id"] != empresa_b["empresa_id"]
    assert empresa_a["cliente_id"] != empresa_b["cliente_id"]


def test_portal_cliente_resolve_o_cliente_certo_da_propria_unidade(client, empresa_a, empresa_b):
    """Mesmo CPF, unidades de empresas diferentes -> cada uma devolve o
    Cliente da SUA empresa, não o da outra."""
    r = client.post(
        f"/p/{empresa_a['unidade_slug']}/lookup",
        data={"cpf": empresa_a["cliente_cpf"]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert empresa_a["cliente_nome"] in r.text
    assert empresa_b["cliente_nome"] not in r.text

    r = client.post(
        f"/p/{empresa_b['unidade_slug']}/lookup",
        data={"cpf": empresa_b["cliente_cpf"]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert empresa_b["cliente_nome"] in r.text
    assert empresa_a["cliente_nome"] not in r.text


def test_get_or_create_nao_colide_entre_empresas(app, db, empresa_a, empresa_b):
    """Chamando Cliente.get_or_create com o mesmo CPF nas duas empresas deve
    reaproveitar o cliente de CADA empresa (created=False, mesmo id já
    existente), nunca vazar/reaproveitar o cliente da outra."""
    with app.app_context():
        from app.models.cliente import Cliente

        c_a, created_a = Cliente.get_or_create(
            empresa_id=empresa_a["empresa_id"], name="Outro Nome",
            phone="11900000000", cpf=empresa_a["cliente_cpf"],
        )
        assert created_a is False
        assert c_a.id == empresa_a["cliente_id"]

        c_b, created_b = Cliente.get_or_create(
            empresa_id=empresa_b["empresa_id"], name="Outro Nome",
            phone="11900000000", cpf=empresa_b["cliente_cpf"],
        )
        assert created_b is False
        assert c_b.id == empresa_b["cliente_id"]
        assert c_b.id != c_a.id


def test_customers_search_por_cpf_nao_vaza_de_outra_empresa(client, login, empresa_a, empresa_b):
    login(empresa_a["dono_email"], empresa_a["senha"])
    client.post("/auth/unidade", data={"unidade_id": empresa_a["unidade_id"]}, follow_redirects=True)

    cpf_digits = empresa_a["cliente_cpf"]
    r = client.get(f"/customers/?q={cpf_digits}")
    assert r.status_code == 200
    assert empresa_a["cliente_nome"] in r.text
    assert empresa_b["cliente_nome"] not in r.text
