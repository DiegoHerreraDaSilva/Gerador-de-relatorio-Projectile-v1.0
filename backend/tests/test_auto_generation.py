"""Geração automática (fase 1): família, rascunho, rodada, números, aprovação
e memória do mês anterior. Banco em SQLite na memória e Projectile falso —
nada sai pra rede."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from backend.app import management, notifications, projectile_db
from backend.app.api.shared import build_parse_response
from backend.app.auto_generation import builder, families, memory, service
from backend.app.core import authz
from backend.app.db.reports_schema import metadata, reports
from backend.app.main import app, require_session
from backend.app.services import auto_generation_store, management_store

_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x"}
_COLLABORATOR = {"name": "Colaborador", "login": "colab", "email": "c@x"}

_DETAILS = {
    "E8": {"name": "Legislation Package - Estribo 08.2026", "client": "Mercedes"},
    "E9": {"name": "Legislation Package - Estribo 09.2026", "client": "Mercedes"},
    "P1": {"name": "Projeto Um", "client": "ACME"},
    "F1": {"name": "Projeto Fechado", "client": "ACME"},
}


def _row(day, hours, note, package, project):
    return {"data": day, "observacao": note, "horas": hours, "pacote": package, "project_id": project}


_HOURS = {
    "2026-08": [
        _row(date(2026, 8, 3), 5.0, "Modelagem - ajuste de suporte", "1546.1-001 Estribo 08.2026", "E8"),
        _row(date(2026, 8, 4), 3.0, "Modelagem - ajuste de suporte", "1546.1-001 Estribo 08.2026", "E8"),
        _row(date(2026, 8, 5), 2.0, "Detalhamento - desenho 2D", "1546.1-001 Estribo 08.2026", "E8"),
        _row(date(2026, 8, 6), 4.0, "Reunião - alinhamento", "1600.1-001 Pacote Um", "P1"),
        _row(date(2026, 8, 7), 1.0, "Reunião - alinhamento", "1700.1-001 Fechado", "F1"),
    ],
    "2026-09": [
        _row(date(2026, 9, 3), 6.0, "Modelagem - ajuste de suporte", "1546.1-001 Estribo 09.2026", "E9"),
        _row(date(2026, 9, 4), 1.5, "Modelagem - nova peça", "1546.1-001 Estribo 09.2026", "E9"),
    ],
}


@pytest.fixture
def auto_db(monkeypatch):
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(auto_generation_store, "get_engine", lambda: engine)
    monkeypatch.setattr(management_store, "get_engine", lambda: engine)
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})

    def cached_rows(start, end, *a, **k):
        rows = _HOURS.get(start[:7], [])
        return [{**r, "horas": r["horas"]} for r in rows]

    def project_hours(ids, start, end, conn=None):
        return [r for r in _HOURS.get(start[:7], []) if r["project_id"] in ids]

    monkeypatch.setattr(management, "_get_cached_rows", cached_rows)
    monkeypatch.setattr(projectile_db, "fetch_project_details", lambda ids, conn=None: {i: _DETAILS[i] for i in ids if i in _DETAILS})
    monkeypatch.setattr(projectile_db, "fetch_project_hours", project_hours)
    # histórico fail-open: aqui fica "fora do ar" (a aprovação não depende dele)
    monkeypatch.setattr(service.GenerationGuard, "begin", lambda self, *a, **k: None)
    with management_store.write_session() as s:
        s.set_closed(management_store.mgmt_closed_projects, "project_id", "F1", True)
    yield engine
    app.dependency_overrides.pop(require_session, None)
    engine.dispose()


def _client(user=_MANAGER) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def _run(competence="2026-08", **kw):
    service.start_run(competence, _MANAGER, background=False, **kw)
    return {i["project_id"]: i for i in service.competence_view(competence)["items"]}


def _payload_from(draft: dict, numbers: dict[str, str] | None = None) -> dict:
    """O que o editor manda na aprovação (mesmo formato do GenerateFooter)."""
    header = draft["header"]
    return {
        "packages": [
            {
                "header": {
                    "project_code": (numbers or {}).get(p["id"], p["project_code"]),
                    "project_name": p["project_name"],
                    "location_date": header["location_date"],
                    "month_label": header["month_label"],
                    "signer1_name": header["signer1_name"] or "Fulano",
                    "signer1_company": header["signer1_company"],
                    "signer2_name": header["signer2_name"] or "Beltrano",
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
            for p in draft["packages"]
        ],
        "formats": draft["formats"],
        "include_performance": draft["include_performance"],
    }


# --- família ----------------------------------------------------------------------


def test_familia_ignora_o_mes_do_nome():
    assert families.strip_date("Legislation Package - Estribo 08.2026") == "Legislation Package - Estribo"
    assert families.family_key("Mercedes", "Legislation Package - Estribo 08.2026") == families.family_key("MERCEDES", "Legislation Package - Estribo 09.2026")
    # código do pacote e "2025/2026" não são datas de mês
    assert families.strip_date("1546.7.3-001 Câmera - ATEGO 08.2026") == "1546.7.3-001 Câmera - ATEGO"
    assert families.strip_date("MBB_OTC - Sistemas Veiculares 2025/2026") == "MBB_OTC - Sistemas Veiculares 2025/2026"
    assert families.normalize_key("Câmera") == families.normalize_key("CAMERA")


# --- rascunho = o que a busca por cliente manual monta --------------------------


def test_rascunho_tem_o_mesmo_conteudo_e_defaults_da_busca_manual():
    rows = _HOURS["2026-08"][:3]
    project = {"project_id": "E8", "name": _DETAILS["E8"]["name"], "client": "Mercedes"}
    draft = builder.build_draft("2026-08", project, rows, {"mode": "pacote"}, None, date(2026, 9, 1))

    manual = build_parse_response(*projectile_db.group_hours(rows, split_by_package=True))["packages"]
    assert [p["key"] for p in draft["packages"]] == [p["key"] for p in manual]
    for mine, theirs in zip(draft["packages"], manual, strict=True):
        assert [g["name"] for g in mine["groups"]] == [g["name"] for g in theirs["groups"]]
        assert [[a["hours"] for a in g["activities"]] for g in mine["groups"]] == [[a["hours"] for a in g["activities"]] for g in theirs["groups"]]
        # defaults de FileUpload.applyParseResponse
        assert mine["pacote_scope"] == theirs["key"]
        assert all(g["performance"] == 1 for g in mine["groups"])
        assert mine["project_code"] == "" and mine["language"] == "pt"
    # defaults de useReportStore.createInitialHeader
    assert draft["header"]["location_date"] == "Santo André, 01.09.2026"
    assert draft["header"]["month_label"] == "Agosto/2026"
    assert draft["header"]["signer1_company"] == "Schwaben Engineering"
    assert draft["header"]["signer2_company"] == "Mercedes-Benz do Brasil"
    assert builder.draft_hours(draft) == 10.0


def test_modo_projeto_vira_um_pacote_sem_escopo():
    rows = _HOURS["2026-08"][:3]
    project = {"project_id": "E8", "name": _DETAILS["E8"]["name"], "client": "Mercedes"}
    draft = builder.build_draft("2026-08", project, rows, {"mode": "projeto"}, None, date(2026, 9, 1))
    assert len(draft["packages"]) == 1 and draft["packages"][0]["pacote_scope"] is None


# --- rodada -------------------------------------------------------------------------


def test_rodada_gera_um_rascunho_por_projeto_e_pula_os_fechados(auto_db):
    items = _run()
    assert items["E8"]["status"] == "em_revisao"
    assert items["P1"]["status"] == "em_revisao"
    assert items["F1"]["status"] == "pulado"
    assert items["E8"]["source_hours"] == 10.0
    # rodar de novo não duplica nada
    assert len(_run()) == 3


def test_erro_em_um_projeto_nao_para_a_rodada(auto_db, monkeypatch):
    original = builder.build_draft

    def flaky(competence, project, *a, **k):
        if project["project_id"] == "P1":
            raise RuntimeError("Projectile devolveu lixo")
        return original(competence, project, *a, **k)

    monkeypatch.setattr(builder, "build_draft", flaky)
    items = _run()
    assert items["P1"]["status"] == "erro" and "lixo" in items["P1"]["error"]
    assert items["E8"]["status"] == "em_revisao"
    # regenerar o que deu erro, depois que o problema some
    monkeypatch.setattr(builder, "build_draft", original)
    service.regenerate(items["P1"]["id"], _MANAGER)
    assert service.detail(items["P1"]["id"])["status"] == "em_revisao"


def test_rodada_em_andamento_nao_roda_de_novo(auto_db):
    with auto_generation_store.write_session() as s:
        s.insert_run(
            {
                "id": "01J00000000000000000000000",
                "competence": "2026-08",
                "status": "running",
                "triggered_by": "outro",
                "started_at": auto_generation_store.utcnow(),
            }
        )
    with pytest.raises(service.RunInProgress):
        service.start_run("2026-08", _MANAGER, background=False)


def test_projeto_desativado_na_familia_e_pulado(auto_db):
    service.set_family_rule(families.family_key("ACME", "Projeto Um"), {"enabled": False}, _MANAGER)
    assert _run()["P1"]["status"] == "pulado"


# --- rascunho: trava otimista e estados --------------------------------------------


def test_salvar_com_versao_velha_e_conflito(auto_db):
    item = _run()["E8"]
    draft = service.detail(item["id"])["draft"]
    client = _client()
    ok = client.put(f"/auto-generation/reports/{item['id']}/draft", json={"draft": draft, "draft_version": 1})
    assert ok.status_code == 200 and ok.json()["draft_version"] == 2
    stale = client.put(f"/auto-generation/reports/{item['id']}/draft", json={"draft": draft, "draft_version": 1})
    assert stale.status_code == 409 and stale.json()["detail"]["current_version"] == 2


def test_rascunho_com_campo_desconhecido_e_recusado(auto_db):
    item = _run()["E8"]
    draft = service.detail(item["id"])["draft"]
    draft["packages"][0]["groups"][0]["activities"][0]["hours"] = -5
    response = _client().put(f"/auto-generation/reports/{item['id']}/draft", json={"draft": draft, "draft_version": 1})
    assert response.status_code == 422


def test_colaborador_nao_acessa_a_geracao_automatica(auto_db):
    assert _client(_COLLABORATOR).get("/auto-generation/competences").status_code == 403


# --- aprovação ----------------------------------------------------------------------


def _approve(item_id, numbers=None, version=None):
    detail = service.detail(item_id)
    body = {"payload": _payload_from(detail["draft"], numbers), "draft_version": version or detail["draft_version"]}
    return _client().post(f"/auto-generation/reports/{item_id}/approve", json=body)


def test_aprovar_exige_numero_no_formato(auto_db):
    item = _run()["E8"]
    pkg_id = service.detail(item["id"])["draft"]["packages"][0]["id"]
    missing = _approve(item["id"])
    assert missing.status_code == 400 and "Falta o número" in missing.json()["detail"]["errors"][0]
    wrong = _approve(item["id"], {pkg_id: "SE.26.0511"})  # caso real: um dígito a mais
    assert wrong.status_code == 400
    assert wrong.json()["detail"]["errors"][0] == 'Número "SE.26.0511" fora do formato SE.##.### (ex.: SE.26.053).'


def test_numero_repetido_na_competencia_ou_de_outro_projeto_no_historico_e_barrado(auto_db):
    items = _run()
    e8 = service.detail(items["E8"]["id"])
    p1 = service.detail(items["P1"]["id"])
    service.set_numbers(items["P1"]["id"], {p1["draft"]["packages"][0]["id"]: "SE.26.001"}, p1["draft_version"], _MANAGER)
    same_run = _approve(items["E8"]["id"], {e8["draft"]["packages"][0]["id"]: "SE.26.001"})
    assert same_run.status_code == 400 and "outro relatório desta competência" in same_run.json()["detail"]["errors"][0]

    with auto_db.begin() as conn:
        conn.execute(
            insert(reports).values(
                id="01J00000000000000000000001",
                report_number="SE.26.050",
                scope=None,
                competence_label="Agosto/2026",
                identity_hash="x" * 64,
                project_name_snapshot="Outro Projeto",
                status="active",
                created_by="alguem",
                created_by_name_snapshot="Alguém",
                created_at=datetime(2026, 9, 1),
                updated_at=datetime(2026, 9, 1),
            )
        )
    history = _approve(items["E8"]["id"], {e8["draft"]["packages"][0]["id"]: "SE.26.050"})
    assert history.status_code == 400 and "Outro Projeto" in history.json()["detail"]["errors"][0]


def test_aprovar_congela_o_payload_e_os_arquivos_saem_dele(auto_db):
    item = _run()["E8"]
    pkg_id = service.detail(item["id"])["draft"]["packages"][0]["id"]
    response = _approve(item["id"], {pkg_id: "SE.26.053"})
    assert response.status_code == 200, response.text
    detail = service.detail(item["id"])
    assert detail["status"] == "aprovado" and detail["has_approved_payload"]
    files = service.approved_files(item["id"])
    assert len(files) == 1 and files[0][0].endswith(".xlsx") and files[0][1][:2] == b"PK"
    # aprovado não se edita mais; reabrir volta pra revisão
    draft = detail["draft"]
    locked = _client().put(f"/auto-generation/reports/{item['id']}/draft", json={"draft": draft, "draft_version": detail["draft_version"]})
    assert locked.status_code == 409
    service.reopen(item["id"], _MANAGER)
    assert service.detail(item["id"])["status"] == "em_revisao"


def test_aprovar_com_rascunho_desatualizado_e_conflito(auto_db):
    item = _run()["E8"]
    detail = service.detail(item["id"])
    pkg_id = detail["draft"]["packages"][0]["id"]
    service.set_numbers(item["id"], {pkg_id: "SE.26.053"}, detail["draft_version"], _MANAGER)
    stale = _approve(item["id"], {pkg_id: "SE.26.053"}, version=detail["draft_version"])
    assert stale.status_code == 409


def test_memoria_do_mes_aprovado_nasce_no_mes_seguinte_sem_copiar_horas(auto_db):
    item = _run()["E8"]
    detail = service.detail(item["id"])
    draft = detail["draft"]
    # o gerente ajustou: nome do grupo, performance, descrição e assinantes
    draft["header"]["signer1_name"] = "Diego"
    draft["header"]["signer2_name"] = "Cliente MBB"
    group = draft["packages"][0]["groups"][0]
    group["name"] = "Modelagem 3D"
    group["performance"] = 0.9
    group["activities"][0]["description"] = "Ajuste do suporte do estribo"
    draft["packages"][0]["project_code"] = "SE.26.053"
    version = service.save_draft(item["id"], service.Draft.model_validate(draft), detail["draft_version"], _MANAGER)
    assert _approve(item["id"], version=version).status_code == 200

    september = _run("2026-09")["E9"]
    new = service.detail(september["id"])["draft"]
    assert new["memory_applied"] is True
    assert new["header"]["signer1_name"] == "Diego" and new["header"]["signer2_name"] == "Cliente MBB"
    pkg = new["packages"][0]
    assert pkg["project_code"] == "" and pkg["suggested_code"] == "SE.26.053"  # só sugestão
    renamed = next(g for g in pkg["groups"] if g["name"] == "Modelagem 3D")
    assert renamed["performance"] == 0.9
    same = next(a for a in renamed["activities"] if a["description"] == "Ajuste do suporte do estribo")
    assert same["hours"] == 6.0  # horas de setembro, não de agosto
    # atividade nova continua como veio (no modo por projeto é a observação inteira)
    assert any(a["description"] == "Modelagem - nova peça" for a in renamed["activities"])


def test_memoria_nao_sobrescreve_assinante_da_configuracao():
    draft = {"header": {"signer1_name": "Da regra"}, "packages": []}
    memory.apply(draft, {"signers": {"signer1_name": "Da memória", "signer2_name": "Cliente"}})
    assert draft["header"] == {"signer1_name": "Da regra", "signer2_name": "Cliente"}


# --- o que a tela lista ---------------------------------------------------------------


def test_lista_marca_horas_que_mudaram_e_projetos_novos(auto_db, monkeypatch):
    _run()
    _HOURS["2026-08"].append(_row(date(2026, 8, 20), 2.0, "Modelagem - ajuste de suporte", "1546.1-001 Estribo 08.2026", "E8"))
    _DETAILS["N1"] = {"name": "Projeto Novo", "client": "ACME"}
    _HOURS["2026-08"].append(_row(date(2026, 8, 21), 3.0, "Reunião - kickoff", "1800.1-001 Novo", "N1"))
    try:
        view = service.competence_view("2026-08")
        e8 = next(i for i in view["items"] if i["project_id"] == "E8")
        assert e8["badges"].get("hours_changed") is True and e8["hours_now"] == 12.0
        assert [p["project_id"] for p in view["new_projects"]] == ["N1"]
        # gerar só o novo
        service.start_run("2026-08", _MANAGER, project_ids=["N1"], background=False)
        assert any(i["project_id"] == "N1" for i in service.competence_view("2026-08")["items"])
    finally:
        _HOURS["2026-08"] = _HOURS["2026-08"][:5]
        _DETAILS.pop("N1", None)


def test_previa_do_mes_atual_nao_grava_nada(auto_db):
    preview = service.preview("2026-09")
    assert [p["project_id"] for p in preview["projects"]] == ["E9"]
    assert preview["projects"][0]["planned"] == "sera_gerado"
    assert service.competence_view("2026-09")["items"] == []


def test_competencia_invalida_e_400(auto_db):
    assert _client().get("/auto-generation/competences/2026-13").status_code == 400


def test_horas_sem_descricao_viram_aviso_e_selo_sem_alarme_de_horas_mudaram(auto_db):
    """Caso real (agosto/2026): o MBB_OTC tinha 603 h no Painel e 145 h no
    rascunho — 458 h lançadas sem descrição. Na busca manual elas viram aviso
    ("Adicionar como atividade"); aqui também, com selo na lista."""
    _HOURS["2026-08"].append(_row(date(2026, 8, 22), 4.5, "", "1546.1-001 Estribo 08.2026", "E8"))
    try:
        item = _run()["E8"]
        assert item["source_hours"] == 14.5  # total do Projectile
        assert item["badges"]["missing_hours"] == 4.5
        assert not item["badges"].get("hours_changed")  # nada mudou: só falta descrição
        issue = service.detail(item["id"])["draft"]["issues"][0]
        assert issue["reason"] == "descricao_vazia" and issue["raw_hours"] == 4.5
        # o revisor adicionou como atividade: o selo some no próximo salvamento
        detail = service.detail(item["id"])
        draft = detail["draft"]
        draft["packages"][0]["groups"][0]["activities"].append({"id": "novo", "description": "Horas avulsas", "hours": 4.5})
        draft["issues"] = []
        service.save_draft(item["id"], service.Draft.model_validate(draft), detail["draft_version"], _MANAGER)
        assert "missing_hours" not in next(i for i in service.competence_view("2026-08")["items"] if i["project_id"] == "E8")["badges"]
    finally:
        _HOURS["2026-08"] = _HOURS["2026-08"][:5]


def test_padrao_e_um_relatorio_por_projeto(auto_db):
    """Decisão do usuário (2026-09-28): sem configuração, um relatório pro
    projeto inteiro (sem escopo de pacote — conta como "Enviado" do projeto
    todo no Diagnóstico)."""
    item = _run()["E8"]
    draft = service.detail(item["id"])["draft"]
    assert draft["mode"] == "projeto"
    assert len(draft["packages"]) == 1 and draft["packages"][0]["pacote_scope"] is None
    assert draft["packages"][0]["project_name"] == "Legislation Package - Estribo 08.2026"


def test_configuracao_individual_do_projeto_aparece_na_lista_e_vale_no_mes_seguinte(auto_db):
    key = families.family_key("Mercedes", "Legislation Package - Estribo 08.2026")
    service.set_family_rule(key, {"mode": "pacote", "signer2_name": "Cliente Estribo"}, _MANAGER)
    e8 = _run()["E8"]
    assert e8["rule"] == {"mode": "pacote", "signer2_name": "Cliente Estribo"}
    assert e8["effective"]["mode"] == "pacote" and e8["effective"]["signer1_company"] == "Schwaben Engineering"
    assert service.detail(e8["id"])["draft"]["header"]["signer2_name"] == "Cliente Estribo"
    # setembro é outro projeto no Projectile, mesma família: a regra vale
    e9 = _run("2026-09")["E9"]
    assert service.detail(e9["id"])["draft"]["mode"] == "pacote"
    # e a lista traz o nome de cada pacote, pro número ser digitado por pacote
    assert e9["badges"]["package_names"] == ["1546.1-001 Estribo 09.2026"]


def test_bloco_mostra_o_modo_do_rascunho_e_nao_o_da_configuracao(auto_db):
    """Caso real: rascunho gerado por pacote antes do padrão virar "por
    projeto" mostrava "Um relatório pro projeto · 3 pacotes"."""
    key = families.family_key("Mercedes", "Legislation Package - Estribo 08.2026")
    service.set_family_rule(key, {"mode": "pacote"}, _MANAGER)
    e8 = _run()["E8"]
    service.set_family_rule(key, {}, _MANAGER)  # configuração mudou depois
    e8 = next(i for i in service.competence_view("2026-08")["items"] if i["project_id"] == "E8")
    assert e8["badges"]["mode"] == "pacote" and e8["effective"]["mode"] == "projeto"


def test_resumo_antigo_sem_campos_novos_e_recalculado(auto_db):
    e8 = _run()["E8"]
    with auto_generation_store.write_session() as s:  # como um rascunho de antes do campo
        s.update_report(e8["id"], badges_json={"packages": 1, "numbers": [""]})
    e8 = next(i for i in service.competence_view("2026-08")["items"] if i["project_id"] == "E8")
    assert e8["badges"]["mode"] == "projeto"
    assert e8["badges"]["package_names"] == ["Legislation Package - Estribo 08.2026"]


def test_modelo_do_numero_vira_regra_e_volta():
    from backend.app.auto_generation import rules

    assert rules.model_to_pattern("SE.##.###") == rules.DEFAULT_NUMBER_PATTERN
    assert rules.pattern_to_model(rules.DEFAULT_NUMBER_PATTERN) == "SE.##.###"
    for model in ("SE-##/####", "ABC ##_#", "Nº ###"):
        assert rules.pattern_to_model(rules.model_to_pattern(model)) == model
    assert rules.pattern_to_model(r"^SE\.\d{2}\.\d{3,4}$") is None  # regra à mão: tela mostra avançado
    saved = rules.validate_global({"number_model": "SE.##.####"})
    assert saved == {"number_pattern": r"^SE\.\d{2}\.\d{4}$"}
    assert rules.effective(saved, None)["number_model"] == "SE.##.####"
    with pytest.raises(ValueError):
        rules.validate_global({"number_model": "SE"})


def test_numero_no_modelo_configurado_passa(auto_db):
    service.set_global_config({"number_model": "SE.##.####"}, _MANAGER)
    item = _run()["E8"]
    pkg_id = service.detail(item["id"])["draft"]["packages"][0]["id"]
    assert _approve(item["id"], {pkg_id: "SE.26.0511"}).status_code == 200


# --- revisão por colaborador (fase 3) ---------------------------------------------

_ENGINEERING = [
    {"employee_id": "10", "name": "Colaborador do Projectile", "filiale": None, "cost_center": "CAD", "login": "Colab"},
    {"employee_id": "11", "name": "Outra Pessoa", "filiale": None, "cost_center": "CAE", "login": "outra"},
    {"employee_id": "12", "name": "Sem Login", "filiale": None, "cost_center": "CAE", "login": None},
]
_OTHER = {"name": "Outra", "login": "outra", "email": "o@x"}


@pytest.fixture
def reviewers(monkeypatch):
    monkeypatch.setattr(projectile_db, "fetch_engineering_employees", lambda start, end: _ENGINEERING)
    monkeypatch.setattr(service.reviews, "_reviewers_cache", {"at": 0.0, "items": None})


def _assign(item_id, login):
    return _client().put(f"/auto-generation/reports/{item_id}/reviewer", json={"login": login})


def test_atribuicao_e_envio_disparam_as_notificacoes(auto_db, reviewers, monkeypatch):
    eventos: list[str] = []
    monkeypatch.setattr(notifications, "notify_reviewer_assigned", lambda *a: eventos.append("assigned"))
    monkeypatch.setattr(notifications, "notify_awaiting_approval", lambda *a: eventos.append("submitted"))

    item = _run()["E8"]
    _assign(item["id"], "colab")
    service.submit_review(item["id"], _COLLABORATOR)

    assert eventos == ["assigned", "submitted"]


def test_revisor_vem_da_lista_da_engenharia_com_nome_do_projectile(auto_db, reviewers):
    item = _run()["E8"]
    listed = _client().get("/auto-generation/reviewers").json()["reviewers"]
    assert [r["login"] for r in listed] == ["Colab", "outra"]  # sem login não entra
    assert _assign(item["id"], "ninguem").status_code == 400
    # caixa diferente do login da sessão ("colab") ainda casa; nome é o do Projectile
    assigned = _assign(item["id"], "colab").json()
    assert assigned["reviewer_login"] == "Colab" and assigned["reviewer_name"] == "Colaborador do Projectile"
    assert _client(_COLLABORATOR).get("/auto-generation/reviewers").status_code == 403


def test_colaborador_so_enxerga_o_que_foi_atribuido_a_ele(auto_db, reviewers):
    items = _run()
    _assign(items["E8"]["id"], "colab")
    mine = _client(_COLLABORATOR).get("/my-reviews").json()
    assert [i["id"] for i in mine["to_review"]] == [items["E8"]["id"]]
    assert _client(_COLLABORATOR).get("/my-reviews/summary").json() == {"to_review": 1, "assigned": 1, "awaiting_approval": None}
    # de outra pessoa (ou não atribuído): 404, não 403 — não revela que existe
    assert _client(_OTHER).get(f"/my-reviews/{items['E8']['id']}").status_code == 404
    assert _client(_COLLABORATOR).get(f"/my-reviews/{items['P1']['id']}").status_code == 404
    assert _client(_OTHER).get("/my-reviews").json()["to_review"] == []


def test_revisar_mandar_devolver_e_aprovar(auto_db, reviewers):
    item = _run()["E8"]
    report_id = item["id"]
    _assign(report_id, "colab")
    # `_client()` troca a sessão de TODOS os clientes: um novo a cada chamada
    colab = lambda: _client(_COLLABORATOR)  # noqa: E731
    detail = colab().get(f"/my-reviews/{report_id}").json()
    draft = detail["draft"]
    draft["packages"][0]["groups"][0]["name"] = "Modelagem 3D"
    draft["packages"][0]["project_code"] = "SE.26.999"  # número é do gerente
    draft["include_performance"] = True  # e "incluir performance" também
    saved = colab().put(f"/my-reviews/{report_id}/draft", json={"draft": draft, "draft_version": detail["draft_version"]})
    assert saved.status_code == 200, saved.text
    stored = service.detail(report_id)["draft"]
    assert stored["packages"][0]["groups"][0]["name"] == "Modelagem 3D"
    assert stored["packages"][0]["project_code"] == "" and stored["include_performance"] is False

    assert colab().post(f"/my-reviews/{report_id}/submit", json={"comment": "Conferi as horas"}).json() == {"status": "revisado"}
    # mandou pra aprovação: o revisor não edita mais
    again = colab().put(f"/my-reviews/{report_id}/draft", json={"draft": draft, "draft_version": service.detail(report_id)["draft_version"]})
    assert again.status_code == 409
    listed = {i["id"]: i for i in service.competence_view("2026-08")["items"]}
    assert listed[report_id]["last_comment"]["comment"] == "Conferi as horas"

    # devolver exige dizer o que mudar
    assert _client().post(f"/auto-generation/reports/{report_id}/return", json={"comment": " "}).status_code == 400
    assert _client().post(f"/auto-generation/reports/{report_id}/return", json={"comment": "Separe a reunião"}).status_code == 200
    returned = colab().get("/my-reviews").json()["to_review"][0]
    assert returned["status"] == "devolvido" and returned["last_comment"]["comment"] == "Separe a reunião"
    colab().post(f"/my-reviews/{report_id}/submit", json={})
    assert _client().get("/my-reviews/summary").json()["awaiting_approval"] == 1

    pkg_id = stored["packages"][0]["id"]
    assert _approve(report_id, {pkg_id: "SE.26.053"}).status_code == 200
    assert [i["id"] for i in colab().get("/my-reviews").json()["done"]] == [report_id]
    # o revisor fica lembrado: no mês seguinte o rascunho da família já nasce atribuído
    september = _run("2026-09")["E9"]
    assert september["reviewer_login"] == "Colab" and september["reviewer_name"] == "Colaborador do Projectile"


def test_trocar_o_revisor_de_um_revisado_volta_pra_revisao(auto_db, reviewers):
    report_id = _run()["E8"]["id"]
    _assign(report_id, "colab")
    _client(_COLLABORATOR).post(f"/my-reviews/{report_id}/submit", json={})
    assert service.detail(report_id)["status"] == "revisado"
    _assign(report_id, "outra")
    assert service.detail(report_id)["status"] == "em_revisao"
    # quem saiu perde o acesso na hora
    assert _client(_COLLABORATOR).get(f"/my-reviews/{report_id}").status_code == 404
    assert _client(_OTHER).get(f"/my-reviews/{report_id}").status_code == 200


def test_revisor_escolhido_no_mes_atual_vale_quando_o_rascunho_nasce(auto_db, reviewers):
    family = service.preview("2026-09")["projects"][0]["family_key"]
    # o nome mandado pela tela é ignorado: vem do Projectile
    saved = _client().put(f"/auto-generation/rules/{family}", json={"reviewer_login": "COLAB", "reviewer_name": "Falso"})
    assert saved.json()["config"] == {"reviewer_login": "Colab", "reviewer_name": "Colaborador do Projectile"}
    assert _client().put(f"/auto-generation/rules/{family}", json={"reviewer_login": "ninguem"}).status_code == 400
    preview = service.preview("2026-09")["projects"][0]
    assert preview["effective"]["reviewer_login"] == "Colab"
    assert _run("2026-09")["E9"]["reviewer_login"] == "Colab"
    assert [i["project_name"] for i in _client(_COLLABORATOR).get("/my-reviews").json()["to_review"]] == ["Legislation Package - Estribo 09.2026"]


# --- envio ao cliente (fase 2) ------------------------------------------------------


@pytest.fixture
def graph(monkeypatch):
    """Graph falso: guarda o que seria enviado, nada sai pra rede."""
    sent: list[dict] = []
    monkeypatch.setattr(service.email_ingest, "send_report_email", lambda **kw: sent.append(kw))
    monkeypatch.setenv("ALBERTO_EMAIL", "g@x")
    return sent


def _approved(competence="2026-08", project="E8") -> str:
    item = _run(competence)[project]
    pkg_id = service.detail(item["id"])["draft"]["packages"][0]["id"]
    assert _approve(item["id"], {pkg_id: "SE.26.053"}).status_code == 200
    return item["id"]


def test_enviar_manda_os_arquivos_aprovados_e_lembra_os_destinatarios(auto_db, graph):
    report_id = _approved()
    defaults = _client().get(f"/auto-generation/reports/{report_id}/send").json()
    assert defaults["to"] == [] and defaults["files"] == [n for n, _ in service.approved_files(report_id)]
    assert defaults["subject"] == "Relatório de Horas - Legislation Package - Estribo 08.2026 - Agosto/2026"
    assert defaults["sender"] == "g@x" and defaults["counts_in_diagnostics"] is True

    body = {
        "to": ["cliente@mbb.com", " cliente@mbb.com "],
        "cc": ["chefe@mbb.com", "CLIENTE@mbb.com"],
        "subject": defaults["subject"],
        "message": defaults["message"],
    }
    response = _client().post(f"/auto-generation/reports/{report_id}/send", json=body)
    assert response.status_code == 200, response.text
    [mail] = graph
    assert mail["sender_email"] == "g@x"  # da sessão, nunca do cliente
    assert mail["to_email"] == ["cliente@mbb.com"] and mail["cc_emails"] == ["chefe@mbb.com"]
    assert [n for n, _ in mail["attachments"]] == defaults["files"]
    listed = {i["id"]: i for i in service.competence_view("2026-08")["items"]}[report_id]
    assert listed["status"] == "enviado" and listed["last_sent"]["to"] == ["cliente@mbb.com"]
    # o mês seguinte da família já abre com os mesmos destinatários (e a próxima aprovação não os apaga)
    next_id = _approved("2026-09", "E9")
    again = _client().get(f"/auto-generation/reports/{next_id}/send").json()
    assert again["to"] == ["cliente@mbb.com"] and again["cc"] == ["chefe@mbb.com"]


def test_envio_recusado_nao_marca_enviado(auto_db, graph, monkeypatch):
    item = _run()["E8"]
    body = {"to": ["cliente@mbb.com"], "subject": "Relatório"}
    assert _client().post(f"/auto-generation/reports/{item['id']}/send", json=body).status_code == 409  # não aprovado
    report_id = _approved()
    bad = _client().post(f"/auto-generation/reports/{report_id}/send", json={**body, "to": ["sem-arroba"]})
    assert bad.status_code == 400 and "sem-arroba" in bad.json()["detail"]
    assert _client(_COLLABORATOR).post(f"/auto-generation/reports/{report_id}/send", json=body).status_code == 403

    def graph_down(**kw):
        raise service.email_ingest.EmailIngestError("Graph fora do ar")

    monkeypatch.setattr(service.email_ingest, "send_report_email", graph_down)
    failed = _client().post(f"/auto-generation/reports/{report_id}/send", json=body)
    assert failed.status_code == 502 and "Graph fora do ar" not in failed.text
    assert service.detail(report_id)["status"] == "aprovado"


def test_remetente_fora_do_alberto_email_e_avisado(auto_db, graph, monkeypatch):
    monkeypatch.setenv("ALBERTO_EMAIL", "alberto@x")
    report_id = _approved()
    assert _client().get(f"/auto-generation/reports/{report_id}/send").json()["counts_in_diagnostics"] is False


def test_download_em_lote_junta_os_aprovados_num_zip(auto_db, graph):
    import io
    import zipfile

    first = _approved()
    p1 = _run()["P1"]
    pkg = service.detail(p1["id"])["draft"]["packages"][0]["id"]
    assert _approve(p1["id"], {pkg: "SE.26.054"}).status_code == 200
    response = _client().get("/auto-generation/files", params={"ids": [first, p1["id"]]})
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert len(names) == 2 and len(set(names)) == 2
    # um não aprovado recusa o lote inteiro
    draft_only = _run("2026-09")["E9"]["id"]
    assert _client().get("/auto-generation/files", params={"ids": [first, draft_only]}).status_code == 409
    assert _client().get("/auto-generation/files").status_code == 400


def test_envio_anexa_so_os_formatos_escolhidos(auto_db, graph):
    item = _run()["E8"]
    detail = service.detail(item["id"])
    draft = {**detail["draft"], "formats": ["xlsx", "pdf"]}
    version = service.save_draft(item["id"], service.Draft.model_validate(draft), detail["draft_version"], _MANAGER)
    pkg_id = draft["packages"][0]["id"]
    assert _approve(item["id"], {pkg_id: "SE.26.053"}, version=version).status_code == 200
    assert len(service.approved_files(item["id"])) == 2
    body = {"to": ["cliente@mbb.com"], "subject": "Relatório", "formats": ["pdf"]}
    assert _client().post(f"/auto-generation/reports/{item['id']}/send", json=body).status_code == 200
    assert [n.rsplit(".", 1)[-1] for n, _ in graph[0]["attachments"]] == ["pdf"]
    assert _client().post(f"/auto-generation/reports/{item['id']}/send", json={**body, "formats": ["docx"]}).status_code == 422


def test_varios_aprovados_num_email_so(auto_db, graph):
    first = _approved()
    p1 = _run()["P1"]
    pkg = service.detail(p1["id"])["draft"]["packages"][0]["id"]
    assert _approve(p1["id"], {pkg: "SE.26.054"}).status_code == 200
    body = {"report_ids": [first, p1["id"]], "to": ["cliente@mbb.com"], "subject": "Relatórios de Horas - Agosto/2026"}
    response = _client().post("/auto-generation/send", json=body)
    assert response.status_code == 200, response.text
    [mail] = graph  # UM e-mail
    names = [n for n, _ in mail["attachments"]]
    assert len(names) == 2 and len(set(names)) == 2  # cada arquivo um anexo, nome único
    listed = {i["id"]: i for i in service.competence_view("2026-08")["items"]}
    assert listed[first]["status"] == listed[p1["id"]]["status"] == "enviado"
    # um não aprovado recusa o e-mail inteiro — nada sai
    draft_only = _run("2026-09")["E9"]["id"]
    refused = _client().post("/auto-generation/send", json={**body, "report_ids": [first, draft_only]})
    assert refused.status_code == 409 and len(graph) == 1


def test_enviado_reabre_e_precisa_ser_enviado_de_novo(auto_db, graph):
    report_id = _approved()
    body = {"to": ["cliente@mbb.com"], "subject": "Relatório"}
    assert _client().post(f"/auto-generation/reports/{report_id}/send", json=body).status_code == 200
    assert _client().post(f"/auto-generation/reports/{report_id}/reopen", json={}).status_code == 200
    detail = service.detail(report_id)
    assert detail["status"] == "em_revisao" and detail["sent_at"] is None and not detail["has_approved_payload"]
    # o envio anterior continua na linha do tempo
    assert [e["action"] for e in detail["events"]][-2:] == ["sent", "reopened"]
    # sem aprovar de novo não dá pra enviar (o cliente só tem a versão antiga)
    assert _client().post(f"/auto-generation/reports/{report_id}/send", json=body).status_code == 409


def test_minhas_revisoes_so_mostram_competencias_da_janela(auto_db, reviewers):
    """Coordenador/colaborador só vê os últimos 12 meses e o ano atual —
    rascunho atribuído de uma competência antiga some da lista e do contador."""
    recent = _run()["E8"]["id"]
    _assign(recent, "colab")
    with auto_generation_store.write_session() as s:
        s.insert_report(
            {
                "id": "01J0ANTIGO0000000000000000",
                "run_id": "R-antigo",
                "competence": "2019-03",
                "project_id": "OLD",
                "family_key": "acme|antigo",
                "project_name": "Projeto Antigo",
                "client": "ACME",
                "status": "em_revisao",
                "reviewer_login": "Colab",
                "reviewer_name": "Colaborador do Projectile",
                "draft_version": 1,
                "draft_json": service.detail(recent)["draft"],
            }
        )
    colab = lambda: _client(_COLLABORATOR)  # noqa: E731
    assert [i["project_name"] for i in colab().get("/my-reviews").json()["to_review"]] == ["Legislation Package - Estribo 08.2026"]
    assert colab().get("/my-reviews/summary").json()["to_review"] == 1
    assert colab().get("/my-reviews/01J0ANTIGO0000000000000000").status_code == 404
    assert colab().post("/my-reviews/01J0ANTIGO0000000000000000/submit", json={}).status_code == 404


# --- número digitado na prévia do mês atual -------------------------------------------


def _plan(competence, project_id, number):
    return _client().put(f"/auto-generation/competences/{competence}/numbers/{project_id}", json={"number": number})


def test_numero_digitado_na_previa_vai_pro_rascunho_quando_ele_e_gerado(auto_db):
    assert _plan("2026-09", "E9", "SE.26.060").json() == {"number": "SE.26.060"}
    projects = {p["project_id"]: p for p in service.preview("2026-09")["projects"]}
    assert projects["E9"]["planned_number"] == "SE.26.060"
    item = _run("2026-09")["E9"]
    detail = service.detail(item["id"])
    assert detail["draft"]["packages"][0]["project_code"] == "SE.26.060"
    assert item["badges"]["numbers"] == ["SE.26.060"]
    # regenerar (descarta as edições) volta com o número reservado
    service.regenerate(item["id"], _MANAGER)
    assert service.detail(item["id"])["draft"]["packages"][0]["project_code"] == "SE.26.060"
    # o número reservado é de UMA competência: agosto não herda o de setembro
    assert all(p["planned_number"] is None for p in service.preview("2026-08")["projects"])


def test_numero_da_previa_e_validado_e_pode_ser_apagado(auto_db):
    bad = _plan("2026-08", "E8", "SE.26.0511")  # um dígito a mais (caso real)
    assert bad.status_code == 400 and "fora do formato SE.##.###" in bad.json()["detail"]
    assert _plan("2026-08", "NAO-EXISTE", "SE.26.001").status_code == 404
    assert _plan("2026-08", "E8", "SE.26.001").status_code == 200
    clash = _plan("2026-08", "P1", "SE.26.001")  # já reservado pra outro projeto do mês
    assert clash.status_code == 400 and "já está reservado" in clash.json()["detail"]
    assert _plan("2026-08", "E8", "").json() == {"number": None}  # vazio apaga
    assert _plan("2026-08", "P1", "SE.26.001").status_code == 200  # e libera o número
    assert _client(_COLLABORATOR).put("/auto-generation/competences/2026-08/numbers/E8", json={"number": "SE.26.002"}).status_code == 403


def test_numero_da_previa_so_cabe_em_relatorio_de_um_pacote():
    one = {"packages": [{"project_code": ""}]}
    service._apply_planned_number(one, "SE.26.070")
    assert one["packages"][0]["project_code"] == "SE.26.070"
    # vários pacotes: não dá pra saber a qual deles o número pertence
    many = {"packages": [{"project_code": ""}, {"project_code": ""}]}
    service._apply_planned_number(many, "SE.26.070")
    assert [p["project_code"] for p in many["packages"]] == ["", ""]
    service._apply_planned_number(one, None)  # sem número reservado: não mexe
    assert one["packages"][0]["project_code"] == "SE.26.070"


# --- envio incerto (sem e-mail real: Graph e banco são simulados) ----------------------------


_SEND_BODY = {"to": ["cliente@mbb.com"], "subject": "Relatório"}


def _send(report_id):
    return _client().post(f"/auto-generation/reports/{report_id}/send", json=_SEND_BODY)


def _item(report_id, competence="2026-08"):
    return next(i for i in service.competence_view(competence)["items"] if i["id"] == report_id)


def _fail_nth_write(monkeypatch, n):
    """`write_session` falha na n-ésima abertura (1 = a tentativa, 2 = o registro do desfecho)."""
    real = auto_generation_store.write_session
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == n:
            raise auto_generation_store.AutoGenerationStoreError("banco caiu")
        return real()

    monkeypatch.setattr(auto_generation_store, "write_session", flaky)
    return lambda: monkeypatch.setattr(auto_generation_store, "write_session", real)


def test_a_tentativa_e_gravada_antes_do_graph(auto_db, monkeypatch):
    report_id = _approved()
    seen = {}

    def graph(**kw):
        seen["uncertain_during_send"] = report_id in service.uncertain_sends([report_id])

    monkeypatch.setattr(service.email_ingest, "send_report_email", graph)
    assert _send(report_id).status_code == 200
    assert seen["uncertain_during_send"] is True
    assert service.uncertain_sends([report_id]) == {}  # o "sent" resolveu a tentativa


def test_banco_cai_depois_do_graph_vira_envio_incerto_e_bloqueia_reenvio(auto_db, graph, monkeypatch):
    report_id = _approved()
    restore = _fail_nth_write(monkeypatch, 2)
    response = _send(report_id)
    assert response.status_code == 409 and "FOI enviado" in response.json()["detail"]
    assert len(graph) == 1
    assert service.detail(report_id)["status"] == "aprovado"

    restore()  # o banco voltou — mas a tentativa continua sem desfecho
    again = _send(report_id)
    assert again.status_code == 409 and "sem confirmação" in again.json()["detail"]
    assert len(graph) == 1, "não pode mandar o e-mail de novo às cegas"
    assert _item(report_id)["send_uncertain"]["to"] == ["cliente@mbb.com"]


def test_confirmar_que_chegou_marca_enviado_sem_mandar_nada(auto_db, graph, monkeypatch):
    report_id = _approved()
    restore = _fail_nth_write(monkeypatch, 2)
    _send(report_id)
    restore()

    response = _client().post(f"/auto-generation/reports/{report_id}/send/resolve", json={"resolution": "sent"})
    assert response.status_code == 200 and response.json()["status"] == "enviado"
    assert len(graph) == 1
    item = _item(report_id)
    assert item["status"] == "enviado" and item["send_uncertain"] is None
    assert item["last_sent"]["to"] == ["cliente@mbb.com"]


def test_timeout_do_graph_e_incerto_e_nao_chegou_libera_o_reenvio(auto_db, monkeypatch):
    report_id = _approved()
    sent = []

    def timeout(**kw):
        error = service.email_ingest.EmailIngestError("timeout")
        error.maybe_delivered = True
        raise error

    monkeypatch.setattr(service.email_ingest, "send_report_email", timeout)
    response = _send(report_id)
    assert response.status_code == 409 and "confirmar se o e-mail foi enviado" in response.json()["detail"]
    assert _send(report_id).status_code == 409

    resolved = _client().post(f"/auto-generation/reports/{report_id}/send/resolve", json={"resolution": "not_sent"})
    assert resolved.status_code == 200 and _item(report_id)["send_uncertain"] is None
    monkeypatch.setattr(service.email_ingest, "send_report_email", lambda **kw: sent.append(kw))
    assert _send(report_id).status_code == 200 and len(sent) == 1


def test_graph_que_recusa_prova_que_nao_saiu_e_nao_fica_incerto(auto_db, monkeypatch):
    report_id = _approved()

    def refused(**kw):
        raise service.email_ingest.EmailIngestError("403")  # maybe_delivered = False

    monkeypatch.setattr(service.email_ingest, "send_report_email", refused)
    assert _send(report_id).status_code == 502
    assert service.uncertain_sends([report_id]) == {}
    sent = []
    monkeypatch.setattr(service.email_ingest, "send_report_email", lambda **kw: sent.append(kw))
    assert _send(report_id).status_code == 200 and len(sent) == 1


def test_sem_gravar_a_tentativa_nada_e_enviado(auto_db, graph, monkeypatch):
    report_id = _approved()
    _fail_nth_write(monkeypatch, 1)
    assert _send(report_id).status_code == 502
    assert graph == []


def test_envio_em_lote_recusa_se_um_deles_esta_incerto(auto_db, graph, monkeypatch):
    first = _approved(project="E8")
    second = _approved(project="P1")
    restore = _fail_nth_write(monkeypatch, 2)
    _send(first)
    restore()
    body = {**_SEND_BODY, "report_ids": [first, second]}
    response = _client().post("/auto-generation/send", json=body)
    assert response.status_code == 409 and "sem confirmação" in response.json()["detail"]
    assert len(graph) == 1
    assert _client().post("/auto-generation/send", json={**body, "report_ids": [second]}).status_code == 200  # o outro segue livre


def test_resolver_sem_envio_pendente_e_so_gerente(auto_db, graph):
    report_id = _approved()
    url = f"/auto-generation/reports/{report_id}/send/resolve"
    assert _client().post(url, json={"resolution": "sent"}).status_code == 409
    assert _client(_COLLABORATOR).post(url, json={"resolution": "sent"}).status_code == 403
    assert _client().post(url, json={"resolution": "talvez"}).status_code == 422


def test_clique_duplo_enquanto_envia_e_recusado(auto_db, graph):
    report_id = _approved()
    service._sending.add(report_id)
    try:
        assert _send(report_id).status_code == 409
    finally:
        service._sending.discard(report_id)
    assert graph == []
