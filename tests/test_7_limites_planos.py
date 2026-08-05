"""Fase 2 — limites de plano, módulos pagos e uso mensal.

Fixtures próprias (mais enxutas que empresa_a/empresa_b da Fase 1-A,
que sempre vêm com 2 unidades + funcionário + agendamento — bom pra
isolamento, ruim pra deixar uma empresa "exatamente no limite" antes do
teste tentar passar dele). Cada teste monta sua própria empresa com o
plano e a quantidade de recursos pré-existentes que o cenário pede,
sempre linhas reais no banco — não mocks.
"""
from datetime import date

import pytest

from app.utils.limites import pode_criar


def _criar_empresa(db, tag, plano_id, n_unidades_extra=0, n_usuarios_extra=0, n_servicos_extra=0):
    from app.models.empresa import Empresa
    from app.models.unidade import Unidade
    from app.models.usuario import Usuario
    from app.models.servico import Servico

    empresa = Empresa(nome=f"Empresa {tag}", slug=f"empresa-{tag}", plano_id=plano_id, status_assinatura="ativa")
    db.session.add(empresa)
    db.session.flush()

    unidade = Unidade(empresa_id=empresa.id, nome=f"Unidade {tag}", slug=f"unidade-{tag}", ativa=True)
    db.session.add(unidade)
    db.session.flush()

    dono = Usuario(empresa_id=empresa.id, nome=f"Dono {tag}", email=f"dono@{tag}.example.com", papel="dono")
    dono.set_password("senha123")
    db.session.add(dono)

    unidades_extra = []
    for i in range(n_unidades_extra):
        u = Unidade(empresa_id=empresa.id, nome=f"Unidade {tag} extra {i}", slug=f"unidade-{tag}-extra-{i}", ativa=True)
        db.session.add(u)
        unidades_extra.append(u)

    for i in range(n_usuarios_extra):
        u = Usuario(empresa_id=empresa.id, nome=f"Usuario {tag} extra {i}", email=f"extra{i}@{tag}.example.com", papel="funcionario")
        u.set_password("senha123")
        db.session.add(u)

    db.session.flush()
    for i in range(n_servicos_extra):
        db.session.add(Servico(
            empresa_id=empresa.id, unidade_id=unidade.id,
            name=f"Servico {tag} extra {i}", price=10, duration_minutes=15, is_active=True,
        ))

    db.session.commit()
    return {
        "empresa_id": empresa.id,
        "unidade_id": unidade.id,
        "unidades_extra_ids": [u.id for u in unidades_extra],
        "dono_email": dono.email,
        "senha": "senha123",
    }


@pytest.fixture
def login_dono(client, login):
    def _login(dados):
        login(dados["dono_email"], dados["senha"])
        client.post("/auth/unidade", data={"unidade_id": dados["unidade_id"]}, follow_redirects=True)
    return _login


# ── 1. Empresa free não cria 2ª unidade ────────────────────────────────────────
def test_free_nao_cria_segunda_unidade(app, db, client, login_dono, planos):
    with app.app_context():
        dados = _criar_empresa(db, "free1", planos["free"])  # já nasce com 1 unidade (max_unidades=1)

    login_dono(dados)
    r = client.post(
        "/unidades/new",
        data={"nome": "Unidade Nova", "slug": "empresa-free1-nova", "endereco": "", "telefone": ""},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert r.request.path == "/upgrade/"

    with app.app_context():
        from app.models.unidade import Unidade
        assert Unidade.query.filter_by(empresa_id=dados["empresa_id"]).count() == 1


# ── 2. Empresa Pro (max_unidades=5) não cria a 6ª ─────────────────────────────
def test_pro_cria_ate_5_unidades_mas_nao_a_6a(app, db, client, login_dono, planos):
    with app.app_context():
        # 1 unidade base + 3 extra = 4 -> a 5ª (via rota) deve funcionar
        dados = _criar_empresa(db, "pro1", planos["pro"], n_unidades_extra=3)

    login_dono(dados)

    r = client.post(
        "/unidades/new",
        data={"nome": "Unidade 5", "slug": "empresa-pro1-u5", "endereco": "", "telefone": ""},
        follow_redirects=True,
    )
    assert r.request.path != "/upgrade/"  # 5ª unidade permitida

    r = client.post(
        "/unidades/new",
        data={"nome": "Unidade 6", "slug": "empresa-pro1-u6", "endereco": "", "telefone": ""},
        follow_redirects=True,
    )
    assert r.request.path == "/upgrade/"  # 6ª unidade bloqueada

    with app.app_context():
        from app.models.unidade import Unidade
        assert Unidade.query.filter_by(empresa_id=dados["empresa_id"]).count() == 5


# ── 3. Empresa free trava no 3º usuário ───────────────────────────────────────
def test_free_trava_no_terceiro_usuario(app, db, client, login_dono, planos):
    with app.app_context():
        # dono (1) + 1 extra = 2 usuários (max_usuarios=2 no free)
        dados = _criar_empresa(db, "free2", planos["free"], n_usuarios_extra=1)

    login_dono(dados)
    r = client.post(
        "/auth/users/new",
        data={
            "nome": "Terceiro Usuario", "email": "terceiro@free2.example.com",
            "password": "senha123", "confirm_password": "senha123",
            "papel": "gerente", "unidades_ids": [],
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert r.request.path == "/upgrade/"

    with app.app_context():
        from app.models.usuario import Usuario
        assert Usuario.query.filter_by(empresa_id=dados["empresa_id"]).count() == 2


# ── 4. Empresa Essencial não trava em usuário/serviço (limite null) ──────────
def test_essencial_nao_trava_em_usuario_nem_servico(app, db, client, login_dono, planos):
    with app.app_context():
        # bem acima de qualquer limite razoável -- só pra provar que
        # max_usuarios/max_servicos=None realmente não bloqueia nunca.
        dados = _criar_empresa(db, "essencial1", planos["essencial"], n_usuarios_extra=20, n_servicos_extra=20)

    login_dono(dados)

    r = client.post(
        "/auth/users/new",
        data={
            "nome": "Mais Um", "email": "maisum@essencial1.example.com",
            "password": "senha123", "confirm_password": "senha123",
            "papel": "funcionario", "unidades_ids": [dados["unidade_id"]],
        },
        follow_redirects=True,
    )
    assert r.request.path != "/upgrade/"

    r = client.post(
        "/services/new",
        data={"name": "Servico Extra", "description": "", "price": "20", "duration_minutes": "20"},
        follow_redirects=True,
    )
    assert r.request.path != "/upgrade/"

    with app.app_context():
        from app.models.usuario import Usuario
        from app.models.servico import Servico
        assert Usuario.query.filter_by(empresa_id=dados["empresa_id"]).count() == 22  # dono + 20 + 1
        assert Servico.query.filter_by(empresa_id=dados["empresa_id"]).count() == 21  # 20 + 1


# ── 5. Módulo pago bloqueado sem plano correto ────────────────────────────────
def test_modulo_relatorios_bloqueado_sem_plano_correto(app, db, client, login_dono, planos):
    with app.app_context():
        dados_free = _criar_empresa(db, "free3", planos["free"])
        dados_pro = _criar_empresa(db, "pro2", planos["pro"])

    login_dono(dados_free)
    r = client.get("/reports/", follow_redirects=True)
    assert r.request.path == "/upgrade/"

    client.get("/auth/logout")

    login_dono(dados_pro)
    r = client.get("/reports/", follow_redirects=True)
    assert r.request.path != "/upgrade/"
    assert r.status_code == 200


# ── 6. Notificação a partir de 450 sem bloquear criação ───────────────────────
def test_aviso_450_dispara_sem_bloquear_criacao_de_agendamento(app, db, client, login_dono, planos):
    with app.app_context():
        dados = _criar_empresa(db, "uso1", planos["pro"])
        from app.models.profissional import Profissional
        from app.models.servico import Servico
        from app.models.cliente import Cliente
        from app.models.uso_mensal import UsoMensal

        prof = Profissional(empresa_id=dados["empresa_id"], unidade_id=dados["unidade_id"], name="Prof Uso1", is_active=True)
        servico = Servico(empresa_id=dados["empresa_id"], unidade_id=dados["unidade_id"], name="Corte", price=30, duration_minutes=30, is_active=True)
        cliente = Cliente(empresa_id=dados["empresa_id"], name="Cliente Uso1", phone="11999990000")
        db.session.add_all([prof, servico, cliente])
        db.session.flush()
        prof_id, servico_id, cliente_id = prof.id, servico.id, cliente.id

        ano_mes = date.today().strftime("%Y-%m")
        db.session.add(UsoMensal(empresa_id=dados["empresa_id"], ano_mes=ano_mes, agendamentos_count=449))
        db.session.commit()

    login_dono(dados)

    r = client.post(
        "/appointments/new",
        data={
            "customer_id": str(cliente_id), "barber_id": str(prof_id), "service_id": str(servico_id),
            "scheduled_date": date.today().isoformat(), "scheduled_time": "09:00", "notes": "",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "criado com sucesso" in r.text.lower()  # não foi bloqueado

    with app.app_context():
        from app.utils.uso import uso_mensal_atual
        assert uso_mensal_atual(dados["empresa_id"]) == 450

    r = client.get("/")
    assert "450" in r.text and "Ver planos" in r.text  # banner aparece exatamente no limiar


# ── 7. pode_criar() soma entre unidades, não confunde com contagem por unidade ─
def test_pode_criar_soma_servicos_entre_todas_as_unidades(app, db, client, login_dono, planos):
    with app.app_context():
        # free: max_servicos=6. 2 unidades, 3 serviços em cada (a unidade
        # base já é 1; crio mais 1 unidade e distribuo os serviços).
        dados = _criar_empresa(db, "multiunit1", planos["free"], n_unidades_extra=1)
        unidade_b_id = dados["unidades_extra_ids"][0]

        from app.models.servico import Servico
        for i in range(3):
            db.session.add(Servico(empresa_id=dados["empresa_id"], unidade_id=dados["unidade_id"],
                                    name=f"A{i}", price=10, duration_minutes=15, is_active=True))
        for i in range(3):
            db.session.add(Servico(empresa_id=dados["empresa_id"], unidade_id=unidade_b_id,
                                    name=f"B{i}", price=10, duration_minutes=15, is_active=True))
        db.session.commit()

        # Checagem direta de pode_criar(): 6 serviços no total (3+3), nenhuma
        # unidade isolada tem mais que 3 -- se a contagem fosse por unidade
        # (bug), isso liberaria; a soma correta bloqueia.
        pode, motivo = pode_criar(dados["empresa_id"], "servico")
        assert pode is False
        assert motivo == "upgrade_necessario"

    # Confirma pela rota tambem: tentar criar um 7º serviço (em qualquer
    # unidade) é bloqueado.
    login_dono(dados)
    r = client.post(
        "/services/new",
        data={"name": "Setimo", "description": "", "price": "10", "duration_minutes": "15"},
        follow_redirects=True,
    )
    assert r.request.path == "/upgrade/"

    with app.app_context():
        from app.models.servico import Servico
        assert Servico.query.filter_by(empresa_id=dados["empresa_id"]).count() == 6
