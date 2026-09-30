"""Geração personalizada: recorte livre de colaborador/cliente/projeto/pacote,
período qualquer, entrando na mesma esteira da automática. Banco em SQLite na
memória e Projectile falso — nada sai pra rede."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app import management, projectile_db
from backend.app.auto_generation import builder, custom, service
from backend.app.core import authz
from backend.app.db.reports_schema import metadata
from backend.app.generator import parse_period_label
from backend.app.main import app, require_session
from backend.app.services import auto_generation_store as store
from backend.app.services import management_store

_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x"}
_COLLABORATOR = {"name": "Colaborador", "login": "colab", "email": "c@x"}

_DETAILS = {
    "E8": {"name": "Legislation Package - Estribo 08.2026", "client": "Mercedes"},
    "E9": {"name": "Legislation Package - Estribo 09.2026", "client": "Mercedes"},
    "P1": {"name": "Projeto Um", "client": "ACME"},
    "F1": {"name": "Projeto Fechado", "client": "ACME"},
}
_ENGINEERING = [
    {"employee_id": "10", "name": "Lucca Silva", "filiale": None, "cost_center": "CAD", "login": "lucca"},
    {"employee_id": "20", "name": "Ana Souza", "filiale": None, "cost_center": "CAE", "login": "ana"},
]
_PKG_A8 = "1546.1-001 Estribo 08.2026"
_PKG_B8 = "1546.2-001 Outro 08.2026"
_PKG_A9 = "1546.1-001 Estribo 09.2026"


def _row(day, hours, note, package, project, employee, start):
    return {
        "data": day,
        "observacao": note,
        "horas": hours,
        "pacote": package,
        "project_id": project,
        "employee_id": employee,
        "person": "Lucca" if employee == "10" else "Ana",
        "inicio": start,
        "fim": start,
    }


_HOURS = [
    _row(date(2026, 8, 3), 5.0, "Modelagem - ajuste de suporte", _PKG_A8, "E8", "10", "0800"),
    _row(date(2026, 8, 4), 3.0, "Modelagem - ajuste de suporte", _PKG_A8, "E8", "20", "0800"),
    _row(date(2026, 8, 5), 2.0, "Detalhamento - desenho 2D", _PKG_B8, "E8", "10", "0900"),
    _row(date(2026, 8, 6), 4.0, "Reunião - alinhamento", "1600.1-001 Pacote Um", "P1", "10", "1000"),
    _row(date(2026, 8, 7), 1.0, "Reunião - alinhamento", "1700.1-001 Fechado", "F1", "20", "1100"),
    _row(date(2026, 9, 3), 6.0, "Modelagem - ajuste de suporte", _PKG_A9, "E9", "10", "0800"),
    _row(date(2026, 9, 4), 1.5, "Modelagem - nova peça", _PKG_A9, "E9", "20", "0900"),
]


@pytest.fixture
def custom_db(monkeypatch):
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(store, "get_engine", lambda: engine)
    monkeypatch.setattr(management_store, "get_engine", lambda: engine)
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})

    def custom_hours(start, end, project_ids=None, employee_ids=None, conn=None):
        if not project_ids and not employee_ids:
            return []
        return [
            dict(r)
            for r in _HOURS
            if start <= r["data"].isoformat() <= end
            and (not project_ids or r["project_id"] in project_ids)
            and (not employee_ids or r["employee_id"] in employee_ids)
        ]

    def cached_rows(start, end, *a, **k):
        return [dict(r) for r in _HOURS if start <= r["data"].isoformat() <= end]

    def project_hours(ids, start, end, conn=None):
        return [dict(r) for r in _HOURS if start <= r["data"].isoformat() <= end and r["project_id"] in ids]

    monkeypatch.setattr(projectile_db, "fetch_custom_hours", custom_hours)
    monkeypatch.setattr(projectile_db, "fetch_project_hours", project_hours)
    monkeypatch.setattr(management, "_get_cached_rows", cached_rows)
    monkeypatch.setattr(projectile_db, "fetch_project_details", lambda ids, conn=None: {i: _DETAILS[i] for i in ids if i in _DETAILS})
    monkeypatch.setattr(projectile_db, "fetch_project_ids_for_clients", lambda clients, conn=None: [p for p, d in _DETAILS.items() if d["client"] in clients])
    monkeypatch.setattr(projectile_db, "fetch_engineering_employees", lambda start, end: _ENGINEERING)
    monkeypatch.setattr(custom, "_employees_cache", {"since": None, "at": 0.0, "items": None})
    monkeypatch.setattr(service.reviews, "_reviewers_cache", {"at": 0.0, "items": None})
    monkeypatch.setattr(service.custom_flow, "_current_competence", lambda: "2026-08")  # "mês atual" dos testes
    monkeypatch.setattr(service.GenerationGuard, "begin", lambda self, *a, **k: None)
    yield engine
    app.dependency_overrides.pop(require_session, None)
    engine.dispose()


def _client(user=_MANAGER) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def _scope(blocks, start="2026-08", end="2026-08", split_by="nenhum", unit="projeto", **extra):
    return {"period": {"start": start, "end": end}, "blocks": blocks, "split_by": split_by, "package_unit": unit, **extra}


def _plan(scope):
    return service._custom_plan(scope)


def _total(reports):
    return round(sum(r.hours for r in reports), 2)


def _draft_hours(report):
    return builder.draft_hours(report.draft)


# --- período ------------------------------------------------------------------------


def test_rotulo_do_periodo_e_lido_de_volta_pelo_gerador():
    assert builder.period_label("2026-08", "2026-08") == "Agosto/2026"
    assert builder.period_label("2026-07", "2026-11") == "Julho a Novembro/2026"
    assert builder.period_label("2025-12", "2026-02") == "Dezembro/2025 a Fevereiro/2026"
    assert parse_period_label(builder.period_label("2026-07", "2026-11")) == ((2026, 7), (2026, 11))
    assert parse_period_label(builder.period_label("2025-12", "2026-02")) == ((2025, 12), (2026, 2))


# --- recorte: união, cruzamento, pacotes ------------------------------------------------


def test_blocos_se_somam_sem_contar_a_mesma_linha_duas_vezes(custom_db):
    # bloco 1 = projeto E8 inteiro (5+3+2); bloco 2 = tudo do Lucca (5+2+4): 5 e 2 se repetem
    _resolved, reports, warnings = _plan(_scope([{"project_ids": ["E8"]}, {"employee_ids": ["10"]}]))
    assert _total(reports) == 14.0
    assert any("2 lançamento(s)" in w and "mais de um recorte" in w for w in warnings)


def test_dois_lancamentos_iguais_no_mesmo_bloco_continuam_dois(custom_db, monkeypatch):
    twin = dict(_HOURS[0])
    monkeypatch.setattr(projectile_db, "fetch_custom_hours", lambda *a, **k: [dict(_HOURS[0]), twin])
    _resolved, reports, _w = _plan(_scope([{"project_ids": ["E8"]}]))
    assert _total(reports) == 10.0


def test_filtros_do_mesmo_bloco_se_cruzam(custom_db):
    # Lucca nos projetos da Mercedes em agosto: 5 (E8/pacote A) + 2 (E8/pacote B)
    _resolved, reports, _w = _plan(_scope([{"clients": ["Mercedes"], "employee_ids": ["10"]}]))
    assert _total(reports) == 7.0
    assert reports[0].partial and reports[0].draft["packages"][0]["pacote_scope"] == custom.PARTIAL_SCOPE


def test_cliente_com_projeto_escolhido_pega_so_a_intersecao(custom_db):
    _resolved, reports, _w = _plan(_scope([{"clients": ["Mercedes"], "project_ids": ["E8", "P1"]}]))
    assert _total(reports) == 10.0  # P1 é da ACME: fica de fora


def test_pacotes_de_um_projeto(custom_db):
    scope = _scope([{"project_ids": ["E8"], "packages": [_PKG_A8]}], unit="pacote")
    _resolved, reports, _w = _plan(scope)
    [report] = reports
    assert _draft_hours(report) == 8.0 and [p["key"] for p in report.draft["packages"]] == [_PKG_A8]
    # unidade "pacote" com o pacote inteiro: escopo = o nome do pacote, como na busca manual
    assert report.draft["packages"][0]["pacote_scope"] == _PKG_A8 and not report.partial
    # unidade "projeto" com só alguns pacotes: NÃO é o projeto inteiro
    _resolved, reports, _w = _plan(_scope([{"project_ids": ["E8"], "packages": [_PKG_A8]}], unit="projeto"))
    assert reports[0].partial and reports[0].draft["packages"][0]["pacote_scope"] == custom.PARTIAL_SCOPE


def test_projeto_inteiro_sem_filtro_fica_sem_escopo(custom_db):
    _resolved, reports, _w = _plan(_scope([{"project_ids": ["E8"]}]))
    assert not reports[0].partial and reports[0].draft["packages"][0]["pacote_scope"] is None


def test_um_bloco_inteiro_cobre_o_projeto_mesmo_com_outro_bloco_filtrado(custom_db):
    blocks = [{"project_ids": ["E8"]}, {"project_ids": ["E8"], "employee_ids": ["10"]}]
    _resolved, reports, _w = _plan(_scope(blocks))
    assert not reports[0].partial


def test_cobertura_por_projeto_e_pacote():
    whole = custom.Block({"E8"}, set(), [], [])
    by_person = custom.Block({"E8"}, set(), ["10"], [])
    by_package = custom.Block({"E8"}, {"pacote a"}, [], [])
    everything = custom.Block(None, set(), ["10"], [])
    assert custom.covers_whole([whole], "E8", "X", "projeto")
    assert not custom.covers_whole([by_person], "E8", "X", "projeto")
    assert not custom.covers_whole([by_package], "E8", "Pacote A", "projeto")
    assert custom.covers_whole([by_package], "E8", "Pacote A", "pacote")
    assert not custom.covers_whole([by_package], "E8", "Pacote B", "pacote")
    assert not custom.covers_whole([everything], "E8", "X", "projeto")


# --- organização: split_by × package_unit --------------------------------------------------


@pytest.mark.parametrize(
    "split_by,unit,expected",
    [
        ("nenhum", "projeto", 1),
        ("nenhum", "pacote", 1),
        ("projeto", "projeto", 3),
        ("projeto", "pacote", 3),
        ("pacote", "projeto", 4),
        ("pacote", "pacote", 4),
        ("colaborador", "projeto", 2),
        ("colaborador", "pacote", 2),
    ],
)
def test_cada_organizacao_soma_as_mesmas_horas(custom_db, split_by, unit, expected):
    blocks = [{"clients": ["Mercedes", "ACME"]}]
    _resolved, reports, _w = _plan(_scope(blocks, split_by=split_by, unit=unit))
    assert len(reports) == expected
    assert _total(reports) == 15.0
    assert round(sum(_draft_hours(r) for r in reports), 2) == 15.0


def test_titulos_e_pacotes_por_organizacao(custom_db):
    blocks = [{"clients": ["Mercedes", "ACME"]}]
    by_person = _plan(_scope(blocks, split_by="colaborador"))[1]
    assert sorted(r.title for r in by_person) == ["Ana", "Lucca"]
    by_project = _plan(_scope(blocks, split_by="projeto"))[1]
    assert {r.title for r in by_project} == {_DETAILS[p]["name"] for p in ("E8", "P1", "F1")}
    one = _plan(_scope(blocks))[1][0]
    assert one.title == "Personalizado" and len(one.draft["packages"]) == 3
    titled = _plan(_scope(blocks, split_by="projeto", title="Fechamento"))[1]
    assert all(r.title.startswith("Fechamento — ") for r in titled)


def test_pacotes_de_projetos_diferentes_tem_source_key_proprio(custom_db):
    # bug do builder: com vários projetos no modo projeto, todo pacote usava o nome do "único projeto"
    _resolved, [report], _w = _plan(_scope([{"project_ids": ["E8", "P1"]}]))
    keys = [p["source_key"] for p in report.draft["packages"]]
    assert len(keys) == 2 and len(set(keys)) == 2


def test_pacote_com_o_mesmo_nome_em_projetos_diferentes_nao_se_funde(custom_db, monkeypatch):
    rows = [
        _row(date(2026, 8, 3), 2.0, "Geral - a", "Pacote Comum", "E8", "10", "0800"),
        _row(date(2026, 8, 3), 3.0, "Geral - b", "Pacote Comum", "P1", "10", "0900"),
    ]
    monkeypatch.setattr(projectile_db, "fetch_custom_hours", lambda *a, **k: [dict(r) for r in rows])
    _resolved, [report], _w = _plan(_scope([{"project_ids": ["E8", "P1"]}], unit="pacote"))
    assert len(report.draft["packages"]) == 2 and sorted(builder.draft_hours({"packages": [p]}) for p in report.draft["packages"]) == [2.0, 3.0]


def test_varios_meses_juntam_o_mesmo_trabalho_pela_familia(custom_db):
    blocks = [{"clients": ["Mercedes"]}]
    resolved, [report], _w = _plan(_scope(blocks, start="2026-08", end="2026-09"))
    assert resolved.label == "Agosto a Setembro/2026"
    # E8 e E9 são o MESMO trabalho ("… Estribo"): um pacote só, com as horas dos dois meses
    [package] = report.draft["packages"]
    assert package["project_name"] == "Legislation Package - Estribo" and _draft_hours(report) == 17.5
    assert report.draft["header"]["month_label"] == "Agosto a Setembro/2026"
    by_project = _plan(_scope(blocks, start="2026-08", end="2026-09", split_by="projeto"))[1]
    assert len(by_project) == 1  # um relatório da família, não um por mês
    # unidade pacote não junta: o capJob traz o mês no nome
    per_package = _plan(_scope(blocks, start="2026-08", end="2026-09", unit="pacote"))[1][0]
    assert len(per_package.draft["packages"]) == 3


# --- validação --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scope,message",
    [
        (_scope([]), "pelo menos um recorte"),
        (_scope([{}]), "está vazio"),
        (_scope([{"project_ids": ["E8", "P1"], "packages": [_PKG_A8]}]), "exatamente um projeto"),
        (_scope([{"employee_ids": ["999"]}]), "Colaborador não encontrado"),
        (_scope([{"employee_ids": ["10"]}], start="2026-09", end="2026-08"), "antes do inicial"),
        (_scope([{"employee_ids": ["10"]}], start="2026-13", end="2026-13"), "Período inválido"),
        (_scope([{"employee_ids": ["10"]}], start="2020-01", end="2026-08"), "máximo"),
        (_scope([{"project_ids": ["E8"]}], start="2025-01", end="2025-01"), "Nenhuma hora"),
    ],
)
def test_recorte_invalido_e_recusado_com_a_mensagem(custom_db, scope, message):
    with pytest.raises(service.InvalidRequest) as error:
        _plan(scope)
    assert message in str(error.value)


def test_relatorios_demais_sao_recusados(custom_db, monkeypatch):
    monkeypatch.setattr(custom, "MAX_REPORTS", 2)
    with pytest.raises(service.InvalidRequest) as error:
        _plan(_scope([{"clients": ["Mercedes", "ACME"]}], split_by="projeto"))
    assert "máximo por geração é 2" in str(error.value)


def test_bloco_sem_horas_vira_aviso(custom_db):
    _resolved, reports, warnings = _plan(_scope([{"project_ids": ["E8"]}, {"clients": ["Ninguém"]}]))
    assert _total(reports) == 10.0 and any("recorte 2" in w for w in warnings)


def test_horas_sem_descricao_nao_geram_relatorio_vazio(custom_db, monkeypatch):
    rows = [dict(_HOURS[0], observacao=""), dict(_HOURS[3])]
    monkeypatch.setattr(projectile_db, "fetch_custom_hours", lambda *a, **k: [dict(r) for r in rows])
    _resolved, reports, warnings = _plan(_scope([{"project_ids": ["E8", "P1"]}], split_by="projeto"))
    assert [r.title for r in reports] == ["Projeto Um"]
    assert any("só tem horas sem descrição" in w for w in warnings)


# --- serviço: prévia, criação, isolamento --------------------------------------------------------


def test_previa_nao_grava_nada(custom_db):
    preview = service.preview_custom(_scope([{"clients": ["Mercedes"]}], split_by="projeto"))
    assert preview["period_label"] == "Agosto/2026" and preview["total_hours"] == 10.0
    assert [r["title"] for r in preview["reports"]] == [_DETAILS["E8"]["name"]]
    assert store.list_custom() == []


def test_criar_grava_na_esteira_e_nao_vaza_pra_rodada_mensal(custom_db):
    result = service.create_custom(_scope([{"clients": ["Mercedes", "ACME"]}], split_by="projeto"), _MANAGER)
    assert len(result["created"]) == 3
    view = service.custom_view()
    assert len(view["items"]) == 3 and view["counts"] == {"em_revisao": 3}
    first = view["items"][0]
    assert first["kind"] == "avulso" and first["competence"] == "2026-08" and first["project_id"].startswith("custom:")
    assert first["scope_json"]["label"] == "Agosto/2026" and first["badges"]["custom"] is True
    # a lista do mês e "projetos novos" não enxergam o personalizado
    month = service.competence_view("2026-08")
    assert month["items"] == [] and month["new_projects"] == []
    service.start_run("2026-08", _MANAGER, background=False)
    month = service.competence_view("2026-08")
    assert {i["project_id"] for i in month["items"]} == {"E8", "P1", "F1"}
    assert len(service.custom_view()["items"]) == 3


def test_quem_revisa_so_ve_o_periodo_e_o_resumo_do_recorte(custom_db):
    scope = _scope([{"clients": ["Mercedes"], "employee_ids": ["10"]}], reviewer_login="lucca")
    [created] = service.create_custom(scope, _MANAGER)["created"]
    manager_view = service.custom_view()["items"][0]
    exposed = {"label", "summary", "package_unit", "config", "blocks"}
    assert set(manager_view["scope_json"]) == exposed
    assert manager_view["scope_json"]["summary"] == "Mercedes · Lucca Silva"
    reviewer = {"name": "Lucca Silva", "login": "lucca", "email": "l@x"}
    listed = _client(reviewer).get("/my-reviews").json()["to_review"]
    assert [i["id"] for i in listed] == [created["id"]]
    for_reviewer = exposed - {"blocks"}  # quem entrou no recorte é do gerente
    assert set(listed[0]["scope_json"]) == for_reviewer
    detail = _client(reviewer).get(f"/my-reviews/{created['id']}").json()
    # o recorte em si (blocos, ids de colaborador) nunca vai pro revisor
    assert set(detail["scope_json"]) == for_reviewer and "employee" not in str(detail["scope_json"]).lower()
    assert "blocks" not in str(detail["scope_json"])


def test_editar_e_salvar_o_rascunho_usa_o_fluxo_de_sempre(custom_db):
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)["created"]
    detail = service.detail(created["id"])
    assert detail["status"] == "em_revisao" and detail["draft"]["packages"][0]["pacote_scope"] is None
    pkg_id = detail["draft"]["packages"][0]["id"]
    version = service.set_numbers(created["id"], {pkg_id: "SE.26.101"}, detail["draft_version"], _MANAGER)
    assert version == detail["draft_version"] + 1
    service.skip(created["id"], _MANAGER)
    assert service.detail(created["id"])["status"] == "pulado"


def test_revisor_na_criacao_vem_da_lista_da_engenharia(custom_db):
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}], reviewer_login="LUCCA"), _MANAGER)["created"]
    detail = service.detail(created["id"])
    assert detail["reviewer_login"] == "lucca" and detail["reviewer_name"] == "Lucca Silva"
    with pytest.raises(service.InvalidRequest):
        service.create_custom(_scope([{"project_ids": ["E8"]}], reviewer_login="ninguem"), _MANAGER)
    assert len(service.custom_view()["items"]) == 1  # nada foi criado na falha


def test_regenerar_relê_o_recorte_e_descarta_as_edicoes(custom_db, monkeypatch):
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)["created"]
    detail = service.detail(created["id"])
    draft = detail["draft"]
    draft["packages"][0]["groups"][0]["name"] = "Editado"
    service.save_draft(created["id"], service.Draft.model_validate(draft), detail["draft_version"], _MANAGER)
    service.regenerate(created["id"], _MANAGER)
    fresh = service.detail(created["id"])
    assert fresh["draft"]["packages"][0]["groups"][0]["name"] != "Editado" and fresh["draft_version"] > detail["draft_version"]
    # o recorte não tem mais horas: recusa em vez de gravar um rascunho vazio
    monkeypatch.setattr(projectile_db, "fetch_custom_hours", lambda *a, **k: [])
    with pytest.raises(service.InvalidRequest):
        service.regenerate(created["id"], _MANAGER)


def test_regenerar_com_a_parte_que_sumiu_do_recorte(custom_db, monkeypatch):
    [a, b] = sorted(service.create_custom(_scope([{"clients": ["Mercedes", "ACME"]}], split_by="projeto"), _MANAGER)["created"][:2], key=lambda c: c["title"])
    only_acme = [dict(r) for r in _HOURS if r["project_id"] == "P1"]
    monkeypatch.setattr(projectile_db, "fetch_custom_hours", lambda *a, **k: [dict(r) for r in only_acme])
    with pytest.raises(service.WorkflowError):
        service.regenerate(a["id"] if "Estribo" in a["title"] else b["id"], _MANAGER)


# --- configuração do projeto: a mesma dos relatórios mensais --------------------------------------


def _family(project_id):
    from backend.app.auto_generation import families

    return families.family_key(_DETAILS[project_id]["client"], _DETAILS[project_id]["name"])


def _rule(project_id, **rule):
    with store.write_session() as s:
        s.set_rule(_family(project_id), rule, "teste")


def test_relatorio_de_um_projeto_herda_assinantes_arquivos_e_revisor_dele(custom_db):
    _rule("E8", signer1_name="Diego", signer2_name="Cliente MBB", formats=["pdf"], reviewer_login="ana", reviewer_name="Ana Souza")
    _resolved, [report], warnings = _plan(_scope([{"project_ids": ["E8"]}]))
    header = report.draft["header"]
    assert (header["signer1_name"], header["signer2_name"]) == ("Diego", "Cliente MBB")
    assert report.draft["formats"] == ["pdf"]
    assert (report.reviewer_login, report.reviewer_name) == ("ana", "Ana Souza")
    assert not any("configurações diferentes" in w for w in warnings)


def test_projeto_sem_regra_usa_o_padrao_geral(custom_db):
    with store.write_session() as s:
        s.set_config({"signer1_name": "Padrão", "formats": ["xlsx", "pdf"]})
    _resolved, [report], _w = _plan(_scope([{"project_ids": ["P1"]}]))
    assert report.draft["header"]["signer1_name"] == "Padrão" and report.draft["formats"] == ["xlsx", "pdf"]
    assert report.reviewer_login is None


def test_varios_projetos_com_a_mesma_configuracao_usam_ela(custom_db):
    for project in ("E8", "P1"):
        _rule(project, signer1_name="Diego", formats=["pdf"])
    _resolved, [report], warnings = _plan(_scope([{"project_ids": ["E8", "P1"]}]))
    assert report.draft["header"]["signer1_name"] == "Diego" and report.draft["formats"] == ["pdf"]
    assert not any("configurações diferentes" in w for w in warnings)


def test_projetos_com_configuracoes_diferentes_usam_o_padrao_geral_e_avisam(custom_db):
    with store.write_session() as s:
        s.set_config({"signer1_name": "Padrão"})
    _rule("E8", signer1_name="Diego", reviewer_login="ana", reviewer_name="Ana Souza")
    _rule("P1", signer1_name="Outro", formats=["pdf"])
    _resolved, [report], warnings = _plan(_scope([{"project_ids": ["E8", "P1"]}]))
    assert report.draft["header"]["signer1_name"] == "Padrão" and report.draft["formats"] == ["xlsx"]
    assert report.reviewer_login is None
    aviso = next(w for w in warnings if "configurações diferentes" in w)
    assert "assinante Schwaben" in aviso and "arquivos" in aviso and "revisor" in aviso and "padrão geral" in aviso


def test_dividido_por_projeto_cada_relatorio_leva_a_configuracao_do_seu_projeto(custom_db):
    _rule("E8", signer1_name="Diego")
    _rule("P1", signer1_name="Outro")
    _resolved, reports, warnings = _plan(_scope([{"project_ids": ["E8", "P1"]}], split_by="projeto"))
    signers = {r.title: r.draft["header"]["signer1_name"] for r in reports}
    assert signers == {_DETAILS["E8"]["name"]: "Diego", "Projeto Um": "Outro"}
    assert not any("configurações diferentes" in w for w in warnings)


def test_configuracao_vale_pela_familia_inclusive_em_varios_meses(custom_db):
    _rule("E8", signer1_name="Diego")  # a regra é da FAMÍLIA: E9 é o mesmo trabalho
    _resolved, [report], _w = _plan(_scope([{"clients": ["Mercedes"]}], start="2026-08", end="2026-09"))
    assert report.draft["header"]["signer1_name"] == "Diego"


def test_associacao_manual_de_familia_tambem_vale(custom_db):
    _rule("E8", signer1_name="Diego")
    with store.write_session() as s:
        s.set_family_override("P1", _family("E8"), "teste")  # o P1 passou a ser da família do E8
    _resolved, [report], _w = _plan(_scope([{"project_ids": ["P1"]}]))
    assert report.draft["header"]["signer1_name"] == "Diego"


def test_revisor_lembrado_na_memoria_vale_sem_regra(custom_db):
    with store.write_session() as s:
        s.set_memory(_family("E8"), {"reviewer": {"login": "lucca", "name": "Lucca Silva"}}, "R0")
    _resolved, [report], _w = _plan(_scope([{"project_ids": ["E8"]}]))
    assert (report.reviewer_login, report.reviewer_name) == ("lucca", "Lucca Silva")
    # a regra do projeto vence a memória
    _rule("E8", reviewer_login="ana", reviewer_name="Ana Souza")
    assert _plan(_scope([{"project_ids": ["E8"]}]))[1][0].reviewer_login == "ana"


def test_criar_grava_o_revisor_do_projeto_e_o_do_pedido_vence(custom_db):
    _rule("E8", reviewer_login="ana", reviewer_name="Ana Souza")
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)["created"]
    assert service.detail(created["id"])["reviewer_login"] == "ana"
    service.delete_custom(created["id"], _MANAGER)
    [chosen] = service.create_custom(_scope([{"project_ids": ["E8"]}], reviewer_login="lucca"), _MANAGER)["created"]
    detail = service.detail(chosen["id"])
    assert (detail["reviewer_login"], detail["reviewer_name"]) == ("lucca", "Lucca Silva")


def test_a_rodada_leva_a_configuracao_do_projeto_pros_pedidos(custom_db):
    _rule("E8", signer1_name="Diego", formats=["pdf"], reviewer_login="ana", reviewer_name="Ana Souza")
    service.schedule_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)
    service.start_run("2026-08", _MANAGER, background=False)
    [item] = service.custom_view()["items"]
    draft = service.detail(item["id"])["draft"]
    assert draft["header"]["signer1_name"] == "Diego" and draft["formats"] == ["pdf"] and item["reviewer_login"] == "ana"


def test_previa_mostra_o_aviso_de_configuracoes_diferentes(custom_db):
    _rule("E8", signer1_name="Diego")
    _rule("P1", signer1_name="Outro")
    preview = service.preview_custom(_scope([{"project_ids": ["E8", "P1"]}]))
    assert any("configurações diferentes" in w and "Personalizado" in w for w in preview["warnings"])


# --- configuração PRÓPRIA do pedido (o painel "Configuração" dos personalizados) -----------------------


OWN = {"signer1_name": "Própria", "signer2_company": "Cliente Próprio", "formats": ["pdf"]}


def test_configuracao_do_pedido_vale_por_cima_da_do_projeto(custom_db):
    _rule("E8", signer1_name="Do projeto", signer1_company="Empresa do projeto", formats=["xlsx"])
    _resolved, [report], _w = _plan(_scope([{"project_ids": ["E8"]}], config=OWN))
    header = report.draft["header"]
    assert header["signer1_name"] == "Própria" and header["signer2_company"] == "Cliente Próprio"
    assert report.draft["formats"] == ["pdf"]
    assert header["signer1_company"] == "Empresa do projeto"  # o que o pedido não define, herda do projeto


def test_config_do_pedido_nao_gera_aviso_de_configuracoes_diferentes(custom_db):
    _rule("E8", signer1_name="Diego")
    _rule("P1", signer1_name="Outro")
    _resolved, [report], warnings = _plan(_scope([{"project_ids": ["E8", "P1"]}], config={"signer1_name": "Única"}))
    assert report.draft["header"]["signer1_name"] == "Única"
    assert not any("configurações diferentes" in w for w in warnings)


def test_campo_vazio_na_config_herda(custom_db):
    _rule("E8", signer1_name="Diego")
    _resolved, [report], _w = _plan(_scope([{"project_ids": ["E8"]}], config={"signer1_name": "  ", "formats": None}))
    assert report.draft["header"]["signer1_name"] == "Diego"


def test_pedido_agendado_guarda_a_config_e_a_rodada_aplica(custom_db):
    service.schedule_custom(_scope([{"project_ids": ["E8"]}], config=OWN), _MANAGER)
    [request] = service.custom_view()["requests"]
    assert request["config"] == OWN and request["package_unit"] == "projeto"
    service.start_run("2026-08", _MANAGER, background=False)
    [item] = service.custom_view()["items"]
    draft = service.detail(item["id"])["draft"]
    assert draft["header"]["signer1_name"] == "Própria" and draft["formats"] == ["pdf"]


def test_editar_a_configuracao_do_pedido_agendado(custom_db):
    entry = service.schedule_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)
    manager = _client()
    saved = manager.put(
        f"/auto-generation/custom/requests/{entry['id']}/config",
        json={"package_unit": "pacote", "config": {"signer1_name": "Nova", "formats": ["xlsx", "pdf"]}},
    )
    assert saved.status_code == 200
    body = saved.json()["request"]
    assert body["package_unit"] == "pacote" and body["config"] == {"signer1_name": "Nova", "formats": ["xlsx", "pdf"]}
    service.start_run("2026-08", _MANAGER, background=False)
    [item] = service.custom_view()["items"]
    draft = service.detail(item["id"])["draft"]
    assert draft["mode"] == "pacote" and draft["header"]["signer1_name"] == "Nova"
    # limpar tudo volta a herdar
    entry2 = service.schedule_custom(_scope([{"project_ids": ["P1"]}], config=OWN), _MANAGER)
    cleared = manager.put(f"/auto-generation/custom/requests/{entry2['id']}/config", json={"package_unit": "projeto", "config": None})
    assert cleared.json()["request"]["config"] == {}
    assert manager.put("/auto-generation/custom/requests/inexistente/config", json={"package_unit": "projeto"}).status_code == 404


def test_editar_a_configuracao_de_um_personalizado_gerado_e_regenerar(custom_db):
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)["created"]
    manager = _client()
    saved = manager.put(
        f"/auto-generation/custom/{created['id']}/config", json={"package_unit": "pacote", "config": {"signer1_name": "Nova", "formats": ["pdf"]}}
    )
    assert saved.status_code == 200
    view = next(i for i in service.custom_view()["items"] if i["id"] == created["id"])
    assert view["scope_json"]["package_unit"] == "pacote" and view["scope_json"]["config"]["signer1_name"] == "Nova"
    # o rascunho NÃO muda sozinho…
    assert service.detail(created["id"])["draft"]["header"]["signer1_name"] == ""
    # …muda ao regenerar
    service.regenerate(created["id"], _MANAGER)
    draft = service.detail(created["id"])["draft"]
    assert draft["header"]["signer1_name"] == "Nova" and draft["formats"] == ["pdf"] and draft["mode"] == "pacote"


def test_aprovado_e_enviado_nao_mudam_de_configuracao_e_mensal_nao_tem(custom_db):
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)["created"]
    _approve(created["id"])
    manager = _client()
    blocked = manager.put(f"/auto-generation/custom/{created['id']}/config", json={"package_unit": "projeto", "config": None})
    assert blocked.status_code == 409 and "reabra antes" in blocked.json()["detail"]
    service.start_run("2026-08", _MANAGER, background=False)
    monthly = service.competence_view("2026-08")["items"][0]
    refused = manager.put(f"/auto-generation/custom/{monthly['id']}/config", json={"package_unit": "projeto", "config": None})
    assert refused.status_code == 409 and "personalizado" in refused.json()["detail"]


def test_config_invalida_e_recusada(custom_db):
    entry = service.schedule_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)
    manager = _client()
    url = f"/auto-generation/custom/requests/{entry['id']}/config"
    assert manager.put(url, json={"package_unit": "projeto", "config": {"formats": []}}).status_code == 422
    assert manager.put(url, json={"package_unit": "projeto", "config": {"formats": ["doc"]}}).status_code == 422
    assert manager.put(url, json={"package_unit": "projeto", "config": {"desconhecido": 1}}).status_code == 422
    assert manager.put(url, json={"package_unit": "xyz"}).status_code == 422
    assert manager.put(url, json={"package_unit": "projeto", "config": {"signer1_name": "x" * 201}}).status_code == 422


def test_so_o_gerente_muda_a_configuracao(custom_db):
    entry = service.schedule_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)
    [created] = service.create_custom(_scope([{"project_ids": ["P1"]}]), _MANAGER)["created"]
    colab = _client(_COLLABORATOR)
    body = {"package_unit": "projeto", "config": None}
    assert colab.put(f"/auto-generation/custom/requests/{entry['id']}/config", json=body).status_code == 403
    assert colab.put(f"/auto-generation/custom/{created['id']}/config", json=body).status_code == 403


# --- o que o cartão do pedido mostra ---------------------------------------------------------------------


def test_pedido_guarda_os_recortes_em_nomes(custom_db):
    blocks = [{"clients": ["Mercedes"], "project_ids": ["E8"], "packages": [_PKG_A8], "employee_ids": ["10"]}, {"clients": ["ACME"]}]
    entry = service.schedule_custom(_scope(blocks), _MANAGER)
    assert entry["blocks"] == [
        {"clients": ["Mercedes"], "projects": ["Legislation Package - Estribo 08.2026"], "packages": [_PKG_A8], "employees": ["Lucca Silva"]},
        # bloco só com o cliente: não lista os projetos dele
        {"clients": ["ACME"], "projects": [], "packages": [], "employees": []},
    ]
    assert service.custom_view()["requests"][0]["blocks"] == entry["blocks"]


def test_pedido_antigo_sem_recortes_e_completado_ao_listar(custom_db):
    entry = service.schedule_custom(_scope([{"project_ids": ["E8"], "employee_ids": ["10"]}]), _MANAGER)
    with store.write_session() as s:  # simula um pedido de antes do campo existir
        old = [{k: v for k, v in e.items() if k != "blocks"} for e in s.custom_requests("2026-08")]
        s.set_custom_requests("2026-08", old)
    assert "blocks" not in store.get_custom_requests()["2026-08"][0]
    [request] = service.custom_view()["requests"]
    assert request["id"] == entry["id"]
    assert request["blocks"] == [{"clients": [], "projects": ["Legislation Package - Estribo 08.2026"], "packages": [], "employees": ["Lucca Silva"]}]
    assert store.get_custom_requests()["2026-08"][0]["blocks"] == request["blocks"]  # gravado: não refaz


def test_relatorio_gerado_expoe_os_recortes_em_nomes(custom_db):
    service.create_custom(_scope([{"project_ids": ["E8"], "employee_ids": ["20"]}]), _MANAGER)
    [item] = service.custom_view()["items"]
    assert item["scope_json"]["blocks"] == [{"clients": [], "projects": ["Legislation Package - Estribo 08.2026"], "packages": [], "employees": ["Ana Souza"]}]


# --- apagar --------------------------------------------------------------------------------------


def _events(report_id):
    return store.list_events(report_id)


def test_apagar_tira_o_rascunho_e_a_linha_do_tempo(custom_db):
    [a, b] = service.create_custom(_scope([{"clients": ["Mercedes", "ACME"]}], split_by="projeto"), _MANAGER)["created"][:2]
    assert _events(a["id"])
    service.delete_custom(a["id"], _MANAGER)
    assert store.get_report(a["id"]) is None and _events(a["id"]) == []
    assert a["id"] not in {i["id"] for i in service.custom_view()["items"]}
    assert store.get_report(b["id"]) is not None  # só o escolhido
    with pytest.raises(service.NotFound):
        service.delete_custom(a["id"], _MANAGER)


@pytest.mark.parametrize("prepare", ["skip", "review"])
def test_apaga_em_qualquer_estado_de_rascunho(custom_db, prepare):
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}], reviewer_login="lucca"), _MANAGER)["created"]
    if prepare == "skip":
        service.skip(created["id"], _MANAGER)
    else:
        service.submit_review(created["id"], {"login": "lucca", "name": "Lucca", "email": "l@x"})
        assert service.detail(created["id"])["status"] == "revisado"
    service.delete_custom(created["id"], _MANAGER)
    assert store.get_report(created["id"]) is None


def test_aprovado_e_enviado_precisam_ser_reabertos_antes(custom_db, monkeypatch):
    monkeypatch.setattr(service.email_ingest, "send_report_email", lambda **kw: None)
    monkeypatch.setenv("ALBERTO_EMAIL", "g@x")
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)["created"]
    _approve(created["id"])
    with pytest.raises(service.WorkflowError) as error:
        service.delete_custom(created["id"], _MANAGER)
    assert "reabra antes" in str(error.value) and store.get_report(created["id"]) is not None
    subject, message = service._default_texts(service._load(created["id"]))
    service.send_report(created["id"], ["c@x.com"], [], subject, message, _MANAGER)
    with pytest.raises(service.WorkflowError):
        service.delete_custom(created["id"], _MANAGER)
    service.reopen(created["id"], _MANAGER)
    service.delete_custom(created["id"], _MANAGER)
    assert store.get_report(created["id"]) is None


def test_relatorio_mensal_nao_se_apaga_por_aqui(custom_db):
    service.start_run("2026-08", _MANAGER, background=False)
    monthly = service.competence_view("2026-08")["items"][0]
    with pytest.raises(service.WorkflowError) as error:
        service.delete_custom(monthly["id"], _MANAGER)
    assert "personalizado" in str(error.value) and store.get_report(monthly["id"]) is not None


def test_revisor_perde_o_relatorio_apagado(custom_db):
    reviewer = {"name": "Lucca Silva", "login": "lucca", "email": "l@x"}
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}], reviewer_login="lucca"), _MANAGER)["created"]
    assert [i["id"] for i in _client(reviewer).get("/my-reviews").json()["to_review"]] == [created["id"]]
    assert _client().delete(f"/auto-generation/custom/{created['id']}").status_code == 200
    assert _client(reviewer).get("/my-reviews").json()["to_review"] == []
    assert _client(reviewer).get(f"/my-reviews/{created['id']}").status_code == 404


def test_rota_de_apagar_e_so_do_gerente(custom_db):
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}]), _MANAGER)["created"]
    assert _client(_COLLABORATOR).delete(f"/auto-generation/custom/{created['id']}").status_code == 403
    assert store.get_report(created["id"]) is not None
    manager = _client()
    assert manager.delete("/auto-generation/custom/inexistente").status_code == 404
    assert manager.delete(f"/auto-generation/custom/{created['id']}").json() == {"ok": True}


# --- agendamento: só o mês atual, gerado junto com a rodada ------------------------------------


def _schedule(blocks=None, **kw):
    return service.schedule_custom(_scope(blocks or [{"clients": ["Mercedes", "ACME"]}], split_by="projeto", **kw), _MANAGER)


def test_agendar_nao_cria_rascunho_agora(custom_db):
    entry = _schedule()
    assert entry["status"] == "agendado" and entry["competence"] == "2026-08" and entry["label"] == "Agosto/2026"
    assert entry["summary"] == "Mercedes · ACME"
    assert store.list_custom() == []
    view = service.custom_view()
    assert view["items"] == [] and [r["id"] for r in view["requests"]] == [entry["id"]]


@pytest.mark.parametrize("start,end", [("2026-07", "2026-07"), ("2026-07", "2026-08"), ("2026-09", "2026-09")])
def test_so_vale_pro_mes_atual(custom_db, start, end):
    with pytest.raises(service.InvalidRequest) as error:
        service.schedule_custom(_scope([{"clients": ["Mercedes"]}], start=start, end=end), _MANAGER)
    assert "só pro mês atual (Agosto/2026)" in str(error.value)
    assert store.get_custom_requests() == {}


def test_pedido_invalido_e_recusado_na_hora(custom_db):
    with pytest.raises(service.InvalidRequest):
        service.schedule_custom(_scope([{"employee_ids": ["999"]}]), _MANAGER)
    with pytest.raises(service.InvalidRequest):
        service.schedule_custom(_scope([{"clients": ["Mercedes"]}], reviewer_login="ninguem"), _MANAGER)
    assert store.get_custom_requests() == {}


def test_a_rodada_gera_os_pedidos_junto_com_os_projetos(custom_db):
    entry = _schedule(reviewer_login="lucca")
    service.start_run("2026-08", _MANAGER, background=False)
    month = service.competence_view("2026-08")
    assert {i["project_id"] for i in month["items"]} == {"E8", "P1", "F1"}  # os mensais de sempre
    view = service.custom_view()
    assert len(view["items"]) == 3 and view["requests"] == []  # o pedido saiu da fila
    assert all(i["kind"] == "avulso" and i["reviewer_login"] == "lucca" for i in view["items"])
    assert entry["id"] not in {r["id"] for r in view["requests"]}
    run = store.get_run("2026-08")
    assert run["counts_json"]["personalizados"] == 1  # 1 pedido gerado (vira 3 itens)


def test_rodar_de_novo_nao_duplica_o_pedido(custom_db):
    _schedule()
    service.start_run("2026-08", _MANAGER, background=False)
    first = len(service.custom_view()["items"])
    service.start_run("2026-08", _MANAGER, background=False)
    assert len(service.custom_view()["items"]) == first


def test_gerar_so_alguns_projetos_nao_leva_o_pedido(custom_db):
    _schedule()
    service.start_run("2026-08", _MANAGER, project_ids=["P1"], background=False)
    assert store.list_custom() == [] and len(service.custom_view()["requests"]) == 1
    service.start_run("2026-08", _MANAGER, background=False)
    assert len(store.list_custom()) == 3


def test_pedido_de_outro_mes_espera_a_rodada_dele(custom_db, monkeypatch):
    monkeypatch.setattr(service.custom_flow, "_current_competence", lambda: "2026-09")
    _schedule_sep = service.schedule_custom(_scope([{"project_ids": ["E9"]}], start="2026-09", end="2026-09"), _MANAGER)
    service.start_run("2026-08", _MANAGER, background=False)
    assert store.list_custom() == [] and [r["id"] for r in service.custom_view()["requests"]] == [_schedule_sep["id"]]
    service.start_run("2026-09", _MANAGER, background=False)
    assert len(store.list_custom()) == 1


def test_pedido_que_falha_fica_com_o_motivo_e_nao_derruba_a_rodada(custom_db, monkeypatch):
    good = _schedule([{"project_ids": ["E8"]}])
    empty = _schedule([{"project_ids": ["F1"], "employee_ids": ["10"]}])  # o Lucca não tem hora no F1
    service.start_run("2026-08", _MANAGER, background=False)
    assert store.get_run("2026-08")["status"] == "done"
    view = service.custom_view()
    assert len(view["items"]) == 1  # o bom saiu
    [left] = view["requests"]
    assert left["id"] == empty["id"] and left["status"] == "erro" and "Nenhuma hora" in left["error"]
    assert good["id"] not in {r["id"] for r in view["requests"]}
    # com hora (recorte ajustado no Projectile), a próxima rodada tenta de novo
    monkeypatch.setattr(projectile_db, "fetch_custom_hours", lambda *a, **k: [dict(_HOURS[3])])
    service.start_run("2026-08", _MANAGER, background=False)
    assert service.custom_view()["requests"] == [] and len(store.list_custom()) == 2


def test_cancelar_pedido_agendado(custom_db):
    entry = _schedule()
    service.delete_custom_request(entry["id"], _MANAGER)
    assert service.custom_view()["requests"] == []
    with pytest.raises(service.NotFound):
        service.delete_custom_request(entry["id"], _MANAGER)
    service.start_run("2026-08", _MANAGER, background=False)
    assert store.list_custom() == []  # cancelado não gera


def test_rota_de_cancelar_e_so_do_gerente(custom_db):
    entry = _schedule()
    assert _client(_COLLABORATOR).delete(f"/auto-generation/custom/requests/{entry['id']}").status_code == 403
    assert len(service.custom_view()["requests"]) == 1
    manager = _client()
    assert manager.delete("/auto-generation/custom/requests/inexistente").status_code == 404
    assert manager.delete(f"/auto-generation/custom/requests/{entry['id']}").json() == {"ok": True}


# --- aprovação e envio: sem memória de família -------------------------------------------------


def _approve(report_id, number="SE.26.101"):
    detail = service.detail(report_id)
    header = detail["draft"]["header"]
    payload = {
        "packages": [
            {
                "header": {
                    "project_code": number if i == 0 else f"SE.26.1{i:02d}",
                    "project_name": p["project_name"],
                    "location_date": header["location_date"],
                    "month_label": header["month_label"],
                    "signer1_name": "Fulano",
                    "signer1_company": header["signer1_company"],
                    "signer2_name": "Beltrano",
                    "signer2_company": header["signer2_company"],
                },
                "groups": [
                    {
                        "name": g["name"],
                        "performance": g["performance"],
                        "activities": [{"description": a["description"], "hours": a["hours"]} for a in g["activities"]],
                    }
                    for g in p["groups"]
                ],
                "pacote_scope": p["pacote_scope"],
                "language": p["language"],
            }
            for i, p in enumerate(detail["draft"]["packages"])
        ],
        "formats": detail["draft"]["formats"],
        "include_performance": False,
    }
    pkg_ids = [p["id"] for p in detail["draft"]["packages"]]
    service.set_numbers(report_id, {pid: payload["packages"][i]["header"]["project_code"] for i, pid in enumerate(pkg_ids)}, detail["draft_version"], _MANAGER)
    fresh = service.detail(report_id)
    return service.approve(report_id, payload, fresh["draft_version"], _MANAGER)


def test_aprovar_e_enviar_avulso_nao_toca_a_memoria_das_familias(custom_db, monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(service.email_ingest, "send_report_email", lambda **kw: sent.append(kw))
    monkeypatch.setenv("ALBERTO_EMAIL", "g@x")
    [created] = service.create_custom(_scope([{"project_ids": ["E8"]}], title="Fechamento"), _MANAGER)["created"]
    assert _approve(created["id"])["status"] == "aprovado"
    assert store.get_memories() == {}
    files = service.approved_files(created["id"])
    assert len(files) == 1 and files[0][1][:2] == b"PK"

    defaults = service.send_defaults(created["id"], _MANAGER)
    assert defaults["to"] == [] and defaults["cc"] == []
    assert defaults["subject"].startswith("Relatório de Horas - ") and "Agosto/2026" in defaults["subject"]
    assert "do projeto" not in defaults["message"]  # o recorte pode ser uma pessoa, vários projetos…
    service.send_report(created["id"], ["cliente@mbb.com"], [], defaults["subject"], defaults["message"], _MANAGER)
    assert len(sent) == 1 and service.detail(created["id"])["status"] == "enviado"
    assert store.get_memories() == {}
    # reabrir vale pro avulso como pro mensal
    service.reopen(created["id"], _MANAGER)
    assert service.detail(created["id"])["status"] == "em_revisao"


def test_periodo_de_varios_meses_chega_ao_arquivo_e_ao_historico(custom_db):
    [created] = service.create_custom(_scope([{"clients": ["Mercedes"]}], start="2026-08", end="2026-09"), _MANAGER)["created"]
    assert _approve(created["id"])["status"] == "aprovado"
    frozen = service.detail(created["id"])
    assert frozen["draft"]["header"]["month_label"] == "Agosto a Setembro/2026"
    assert [n for n, _ in service.approved_files(created["id"])][0].endswith(".xlsx")


def test_numero_do_avulso_nao_repete_o_de_um_mensal_do_mesmo_mes(custom_db):
    service.start_run("2026-08", _MANAGER, background=False)
    e8 = next(i for i in service.competence_view("2026-08")["items"] if i["project_id"] == "E8")
    detail = service.detail(e8["id"])
    service.set_numbers(e8["id"], {detail["draft"]["packages"][0]["id"]: "SE.26.101"}, detail["draft_version"], _MANAGER)
    [created] = service.create_custom(_scope([{"employee_ids": ["10"]}]), _MANAGER)["created"]
    with pytest.raises(service.ApprovalRejected) as error:
        _approve(created["id"], "SE.26.101")
    assert "outro relatório desta competência" in " ".join(error.value.errors)


# --- rotas ----------------------------------------------------------------------------------------


def test_rotas_do_gerente_e_recusa_de_campos_desconhecidos(custom_db):
    body = _scope([{"clients": ["Mercedes"]}], split_by="projeto")
    manager = _client()
    preview = manager.post("/auto-generation/custom/preview", json=body)
    assert preview.status_code == 200 and preview.json()["total_hours"] == 10.0
    assert manager.get("/auto-generation/custom").json() == {"items": [], "counts": {}, "requests": []}
    scheduled = manager.post("/auto-generation/custom", json=body)
    assert scheduled.status_code == 201 and scheduled.json()["request"]["status"] == "agendado"
    listed = manager.get("/auto-generation/custom").json()
    assert listed["items"] == [] and [r["id"] for r in listed["requests"]] == [scheduled.json()["request"]["id"]]
    assert manager.post("/auto-generation/custom", json={**body, "extra": 1}).status_code == 422
    assert manager.post("/auto-generation/custom", json={**body, "blocks": []}).status_code == 422
    bad = manager.post("/auto-generation/custom", json=_scope([{"employee_ids": ["999"]}]))
    assert bad.status_code == 400 and "Colaborador não encontrado" in bad.json()["detail"]


def test_colaborador_nao_cria_nem_ve_personalizados(custom_db):
    colab = _client(_COLLABORATOR)
    assert colab.get("/auto-generation/custom").status_code == 403
    assert colab.post("/auto-generation/custom/preview", json=_scope([{"project_ids": ["E8"]}])).status_code == 403
    assert colab.post("/auto-generation/custom", json=_scope([{"project_ids": ["E8"]}])).status_code == 403
