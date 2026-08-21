"""Categoria 10 — CRUD de Unidade (auditoria de completude pré-lançamento).

Unidade só tinha rota de criação até aqui — sem edição nem exclusão pela
UI, um typo no nome/endereço era permanente e não havia como desativar
uma unidade fechada. Isolamento cross-tenant (dono da empresa A não
edita/apaga unidade da empresa B) já está coberto em test_2_idor.py; este
arquivo cobre as regras de negócio novas em si.

Fixture própria por teste (não empresa_a/empresa_b, module-scoped e
reaproveitada por outras categorias) -- os testes aqui editam/desativam/
apagam unidade o tempo todo, o que colidiria entre testes do mesmo
arquivo se a empresa fosse compartilhada (mesmo padrão já usado em
test_7_limites_planos.py e test_9_fase3_asaas.py)."""
import itertools

import pytest

from app.models.unidade import Unidade

_contador = itertools.count()


def _criar_empresa_com_unidades(db, com_dependencias=False):
    """Empresa com dono + 2 unidades (uma vazia, uma com dependência real
    se com_dependencias=True) + 1 unidade já inativa (pra testes de
    "última unidade ativa" sem precisar de uma 3ª unidade extra)."""
    from app.models.empresa import Empresa
    from app.models.unidade import Unidade
    from app.models.usuario import Usuario
    from app.models.plano import Plano
    from app.models.profissional import Profissional
    from app.models.servico import Servico
    from app.models.agendamento import Agendamento
    from app.models.cliente import Cliente
    from datetime import date, time

    n = next(_contador)
    plano_ilimitado = Plano.query.filter_by(nome="ilimitado").first()

    empresa = Empresa(nome=f"Empresa CRUD Unidade {n}", slug=f"empresa-crud-unidade-{n}",
                       plano_id=plano_ilimitado.id, status_assinatura="ativa")
    db.session.add(empresa)
    db.session.flush()

    unidade_a = Unidade(empresa_id=empresa.id, nome=f"Unidade A {n}", slug=f"unidade-a-{n}", ativa=True)
    unidade_b = Unidade(empresa_id=empresa.id, nome=f"Unidade B {n}", slug=f"unidade-b-{n}", ativa=True)
    unidade_inativa = Unidade(empresa_id=empresa.id, nome=f"Unidade Inativa {n}", slug=f"unidade-inativa-{n}", ativa=False)
    db.session.add_all([unidade_a, unidade_b, unidade_inativa])
    db.session.flush()

    dono = Usuario(empresa_id=empresa.id, nome=f"Dono {n}", email=f"dono@crud-unidade-{n}.example.com", papel="dono")
    dono.set_password("senha123")
    db.session.add(dono)
    db.session.flush()

    if com_dependencias:
        prof = Profissional(empresa_id=empresa.id, unidade_id=unidade_a.id, name=f"Prof {n}", is_active=True)
        db.session.add(prof)
        servico = Servico(empresa_id=empresa.id, unidade_id=unidade_a.id, name=f"Corte {n}",
                           price=30, duration_minutes=30, is_active=True)
        db.session.add(servico)
        cliente = Cliente(empresa_id=empresa.id, name=f"Cliente {n}", phone=f"1199{n:07d}"[:11])
        db.session.add(cliente)
        db.session.flush()
        db.session.add(Agendamento(
            empresa_id=empresa.id, unidade_id=unidade_a.id, customer_id=cliente.id,
            barber_id=prof.id, service_id=servico.id,
            scheduled_date=date.today(), scheduled_time=time(10, 0), status="pending",
        ))

    db.session.commit()
    return {
        "empresa_id": empresa.id,
        "unidade_a_id": unidade_a.id, "unidade_a_slug": unidade_a.slug,
        "unidade_b_id": unidade_b.id, "unidade_b_slug": unidade_b.slug,
        "unidade_inativa_id": unidade_inativa.id,
        "dono_email": dono.email, "senha": "senha123",
    }


@pytest.fixture
def empresa_vazia(app, db, planos, login, client):
    with app.app_context():
        dados = _criar_empresa_com_unidades(db, com_dependencias=False)
    login(dados["dono_email"], dados["senha"])
    client.post("/auth/unidade", data={"unidade_id": dados["unidade_a_id"]}, follow_redirects=True)
    return dados


@pytest.fixture
def empresa_com_dependencias(app, db, planos, login, client):
    with app.app_context():
        dados = _criar_empresa_com_unidades(db, com_dependencias=True)
    login(dados["dono_email"], dados["senha"])
    client.post("/auth/unidade", data={"unidade_id": dados["unidade_a_id"]}, follow_redirects=True)
    return dados


# ── edição ───────────────────────────────────────────────────────────────────
def test_edit_atualiza_campos(app, db, client, empresa_vazia):
    e = empresa_vazia
    r = client.post(
        f"/unidades/{e['unidade_b_id']}/edit",
        data={
            "nome": "Unidade Renomeada", "slug": f"{e['unidade_b_slug']}-renomeada",
            "endereco": "Rua Nova, 123", "telefone": "11988887777",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "atualizada com sucesso" in r.text.lower()

    with app.app_context():
        u = Unidade.query.get(e["unidade_b_id"])
        assert u.nome == "Unidade Renomeada"
        assert u.slug == f"{e['unidade_b_slug']}-renomeada"
        assert u.endereco == "Rua Nova, 123"
        assert u.telefone == "11988887777"


def test_edit_slug_duplicado_e_rejeitado(client, empresa_vazia):
    e = empresa_vazia
    r = client.post(
        f"/unidades/{e['unidade_b_id']}/edit",
        data={"nome": "Unidade X", "slug": e["unidade_a_slug"], "endereco": "", "telefone": ""},
    )
    assert r.status_code == 200  # re-renderiza o form, não redireciona
    assert "já está em uso" in r.text.lower()


def test_edit_mesmo_slug_sem_mudanca_nao_bloqueia_a_si_mesma(client, empresa_vazia):
    """Salvar sem trocar o slug não pode falhar achando que colide consigo mesma."""
    e = empresa_vazia
    r = client.post(
        f"/unidades/{e['unidade_b_id']}/edit",
        data={"nome": "Unidade B Só Nome Mudou", "slug": e["unidade_b_slug"], "endereco": "", "telefone": ""},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "atualizada com sucesso" in r.text.lower()


# ── ativar/desativar ─────────────────────────────────────────────────────────
def test_toggle_desativa_e_reativa_unidade_nao_unica(app, db, client, empresa_vazia):
    e = empresa_vazia
    r = client.post(f"/unidades/{e['unidade_b_id']}/toggle", follow_redirects=True)
    assert "desativada" in r.text.lower()
    with app.app_context():
        assert Unidade.query.get(e["unidade_b_id"]).ativa is False

    r = client.post(f"/unidades/{e['unidade_b_id']}/toggle", follow_redirects=True)
    assert "ativada" in r.text.lower()
    with app.app_context():
        assert Unidade.query.get(e["unidade_b_id"]).ativa is True


def test_toggle_bloqueia_desativar_unica_unidade_ativa(app, db, client, empresa_vazia):
    e = empresa_vazia
    # desativa a unidade B primeiro, deixando só a A ativa (a "inativa" já
    # nasce desativada, não conta)
    client.post(f"/unidades/{e['unidade_b_id']}/toggle")

    r = client.post(f"/unidades/{e['unidade_a_id']}/toggle", follow_redirects=True)
    assert "não é possível desativar a única unidade ativa" in r.text.lower()
    with app.app_context():
        assert Unidade.query.get(e["unidade_a_id"]).ativa is True


# ── exclusão ─────────────────────────────────────────────────────────────────
def test_delete_bloqueia_com_dependencias(app, db, client, empresa_com_dependencias):
    e = empresa_com_dependencias
    r = client.post(f"/unidades/{e['unidade_a_id']}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert "não pode ser" in r.text.lower() and "exclu" in r.text.lower()
    with app.app_context():
        assert Unidade.query.get(e["unidade_a_id"]) is not None  # não foi apagada


def test_delete_funciona_sem_dependencias(app, db, client, empresa_vazia):
    e = empresa_vazia
    r = client.post(f"/unidades/{e['unidade_b_id']}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert "excluída" in r.text.lower()
    with app.app_context():
        assert Unidade.query.get(e["unidade_b_id"]) is None


def test_delete_bloqueia_ultima_unidade_da_empresa(app, db, client, empresa_vazia):
    e = empresa_vazia
    # remove as unidades sem dependência (B e a inativa), deixando só A
    client.post(f"/unidades/{e['unidade_b_id']}/delete")
    client.post(f"/unidades/{e['unidade_inativa_id']}/delete")

    with app.app_context():
        restantes = Unidade.query.filter_by(empresa_id=e["empresa_id"]).count()
        assert restantes == 1

    r = client.post(f"/unidades/{e['unidade_a_id']}/delete", follow_redirects=True)
    assert "não é possível excluir a única unidade" in r.text.lower()
    with app.app_context():
        assert Unidade.query.get(e["unidade_a_id"]) is not None


# ── permissão ────────────────────────────────────────────────────────────────
def test_gerente_nao_acessa_gestao_de_unidades(app, db, client, login, planos):
    with app.app_context():
        dados = _criar_empresa_com_unidades(db, com_dependencias=False)
        from app.models.usuario import Usuario
        gerente = Usuario(empresa_id=dados["empresa_id"], nome="Gerente", email="gerente@crud-unidade.example.com", papel="gerente")
        gerente.set_password("senha123")
        db.session.add(gerente)
        db.session.commit()

    login("gerente@crud-unidade.example.com", "senha123")
    client.post("/auth/unidade", data={"unidade_id": dados["unidade_a_id"]}, follow_redirects=True)

    for method, path in [
        ("get", "/unidades/"),
        ("get", f"/unidades/{dados['unidade_b_id']}/edit"),
        ("post", f"/unidades/{dados['unidade_b_id']}/toggle"),
        ("post", f"/unidades/{dados['unidade_b_id']}/delete"),
    ]:
        r = getattr(client, method)(path, follow_redirects=False)
        assert r.status_code == 302  # redireciona pro dashboard, sem permissão


# ── nav ──────────────────────────────────────────────────────────────────────
def test_link_unidades_aparece_no_menu_pro_dono(client, empresa_vazia):
    r = client.get("/")
    assert 'href="/unidades/"' in r.text


def test_link_unidades_nao_aparece_no_menu_pro_gerente(app, db, client, login, planos):
    with app.app_context():
        dados = _criar_empresa_com_unidades(db, com_dependencias=False)
        from app.models.usuario import Usuario
        gerente = Usuario(empresa_id=dados["empresa_id"], nome="Gerente", email="gerente2@crud-unidade.example.com", papel="gerente")
        gerente.set_password("senha123")
        db.session.add(gerente)
        db.session.commit()

    login("gerente2@crud-unidade.example.com", "senha123")
    client.post("/auth/unidade", data={"unidade_id": dados["unidade_a_id"]}, follow_redirects=True)
    r = client.get("/")
    assert 'href="/unidades/"' not in r.text
