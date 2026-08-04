def test_fixtures_criam_duas_empresas_reais(empresa_a, empresa_b):
    assert empresa_a["empresa_id"] != empresa_b["empresa_id"]
    assert empresa_a["cliente_cpf"] == empresa_b["cliente_cpf"]  # mesmo CPF, empresas diferentes


def test_login_funciona(client, login, empresa_a):
    r = login(empresa_a["dono_email"], empresa_a["senha"])
    assert r.status_code == 200
    assert "Dashboard" in r.text or "dashboard" in r.request.path
