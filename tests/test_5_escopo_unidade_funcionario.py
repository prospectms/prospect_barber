"""Categoria 5 — funcionário não alcança unidade fora de UsuarioUnidade.
Na fixture empresa_a/empresa_b, o funcionário só está vinculado à
unidade 1 (não à unidade 2)."""


def test_funcionario_login_auto_seleciona_a_unica_unidade_vinculada(client, login, empresa_a):
    login(empresa_a["func_email"], empresa_a["senha"])
    with client.session_transaction() as sess:
        assert sess.get("unidade_ativa_id") == empresa_a["unidade_id"]


def test_funcionario_nao_consegue_trocar_para_unidade_nao_vinculada(client, login, empresa_a):
    """A defesa real hoje, num POST normal, é o form.choices: unidade_id=2
    nem está na lista de opções que a rota monta pro funcionário, então o
    WTForms rejeita como "Not a valid choice" ANTES do código customizado
    (usuario_pode_acessar_unidade) ser alcançado. Ver
    test_usuario_pode_acessar_unidade_intercepta_mesmo_com_choices_permissivos
    pra prova de que a camada 2 (o check explícito) também funciona sozinha,
    caso a camada 1 (choices) algum dia tenha um bug."""
    login(empresa_a["func_email"], empresa_a["senha"])
    r = client.post(
        "/auth/unidade",
        data={"unidade_id": empresa_a["unidade2_id"]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Not a valid choice" in r.text

    with client.session_transaction() as sess:
        # continua na unidade original -- NAO trocou pra unidade2
        assert sess.get("unidade_ativa_id") == empresa_a["unidade_id"]


def test_usuario_pode_acessar_unidade_intercepta_mesmo_com_choices_permissivos(
    client, login, empresa_a, monkeypatch
):
    """Camada 2 de defesa, isolada: simula um bug futuro na camada 1 (choices
    montados errado, incluindo uma unidade fora do vínculo) via monkeypatch
    de unidades_do_usuario dentro de app.auth.routes -- é essa referência
    que o form realmente usa, não o módulo original. Com o form aceitando
    unidade_id=2 como escolha válida, confirma que usuario_pode_acessar_unidade
    (chamado depois de form.validate_on_submit(), independente dos choices)
    ainda bloqueia."""
    import app.auth.routes as auth_routes
    from app.models.unidade import Unidade

    login(empresa_a["func_email"], empresa_a["senha"])

    def unidades_permissivas_demais(usuario):
        return (
            Unidade.query.filter_by(empresa_id=usuario.empresa_id, ativa=True)
            .order_by(Unidade.nome)
            .all()
        )

    monkeypatch.setattr(auth_routes, "unidades_do_usuario", unidades_permissivas_demais)

    r = client.post(
        "/auth/unidade",
        data={"unidade_id": empresa_a["unidade2_id"]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    # Preciso ver o formulário aceitar a escolha (sem "Not a valid choice")
    # e ainda assim ser bloqueado pelo check explícito.
    assert "Not a valid choice" not in r.text
    assert "não tem acesso" in r.text or "Você não tem acesso" in r.text

    with client.session_transaction() as sess:
        assert sess.get("unidade_ativa_id") == empresa_a["unidade_id"]  # não mudou pra unidade2


def test_sessao_adulterada_para_unidade_nao_vinculada_e_revalidada_a_cada_request(client, login, empresa_a):
    """Mesmo se a sessão for adulterada diretamente (ex: cookie editado à
    mão) pra apontar pra uma unidade fora do vínculo, o before_request
    revalida em toda request e derruba unidade_ativa_id -- não basta ter
    setado uma vez."""
    login(empresa_a["func_email"], empresa_a["senha"])

    with client.session_transaction() as sess:
        sess["unidade_ativa_id"] = empresa_a["unidade2_id"]  # adulteração direta

    r = client.get("/appointments/", follow_redirects=False)
    # requer_unidade não encontra g.unidade_id válido (foi limpo no
    # before_request) e redireciona pro seletor, em vez de servir dado da
    # unidade 2.
    assert r.status_code == 302
    assert "/auth/unidade" in r.headers["Location"]

    with client.session_transaction() as sess:
        assert sess.get("unidade_ativa_id") is None


def test_funcionario_nao_ve_unidade2_no_seletor(client, login, empresa_a):
    login(empresa_a["func_email"], empresa_a["senha"])
    r = client.get("/auth/unidade")
    assert r.status_code == 200
    assert "Unidade a 1" in r.text  # unidade vinculada aparece (template mostra nome, não slug)
    assert "Unidade a 2" not in r.text  # unidade NÃO vinculada não aparece como opção


def test_dono_ve_as_duas_unidades_no_seletor(client, login, empresa_a):
    """Controle: dono não tem vínculo via UsuarioUnidade, mas acessa todas as
    unidades ativas da empresa por papel -- diferente do funcionário."""
    login(empresa_a["dono_email"], empresa_a["senha"])
    r = client.get("/auth/unidade")
    assert r.status_code == 200
    assert empresa_a["unidade_id"]
    assert "Unidade a 1" in r.text
    assert "Unidade a 2" in r.text
