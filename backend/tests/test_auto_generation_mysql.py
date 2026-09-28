"""Geração automática no MySQL de verdade (schema `reports_db_test`): lock
de escrita, JSON grande (payload congelado com gráfico) e a aprovação
gravando no histórico — o que o SQLite dos testes de regra não prova."""
from __future__ import annotations

import base64

import pytest

from backend.app import management, projectile_db
from backend.app.auto_generation import service
from backend.app.services import report_queries

from .test_auto_generation import _DETAILS, _HOURS, _MANAGER, _payload_from

pytestmark = pytest.mark.reports_db


@pytest.fixture
def mysql_auto(reports_db_engine, monkeypatch):
    monkeypatch.setattr(management, "_get_cached_rows", lambda start, end, *a, **k: list(_HOURS.get(start[:7], [])))
    monkeypatch.setattr(projectile_db, "fetch_project_details",
                        lambda ids, conn=None: {i: _DETAILS[i] for i in ids if i in _DETAILS})
    monkeypatch.setattr(projectile_db, "fetch_project_hours",
                        lambda ids, start, end, conn=None: [r for r in _HOURS.get(start[:7], []) if r["project_id"] in ids])
    monkeypatch.setattr(management, "get_closed_registry", lambda: {"closed_projects": ["F1"], "closed_clients": []})
    yield reports_db_engine


def test_aprovacao_no_mysql_grava_historico_e_congela_payload_com_grafico(mysql_auto):
    service.start_run("2026-08", _MANAGER, background=False)
    item = next(i for i in service.competence_view("2026-08")["items"] if i["project_id"] == "E8")
    detail = service.detail(item["id"])
    payload = _payload_from(detail["draft"], {detail["draft"]["packages"][0]["id"]: "SE.26.053"})
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 200_000).decode()   # gráfico grande
    payload["packages"][0]["chart_image_bar"] = None
    payload["packages"][0]["file_name"] = "Estribo"

    result = service.approve(item["id"], payload, detail["draft_version"], _MANAGER)

    assert result["history_links"], "a aprovação precisa aparecer no histórico"
    report_id = result["history_links"][0].split(":")[0]
    history = report_queries.get_report(report_id)
    assert history["report_number"] == "SE.26.053" and history["competence_label"] == "Agosto/2026"
    assert service.detail(item["id"])["status"] == "aprovado"
    files = service.approved_files(item["id"])
    assert files[0][0] == "Estribo.xlsx" and files[0][1][:2] == b"PK"
    # JSON grande no MySQL: o payload congelado volta inteiro
    from backend.app.services import auto_generation_store as store
    with store.write_session() as s:
        s.update_report(item["id"], approved_payload_json={**payload, "_teste_grande": png})
    assert len(store.get_report(item["id"])["approved_payload_json"]["_teste_grande"]) == len(png)


def test_segunda_rodada_no_mysql_nao_duplica(mysql_auto):
    service.start_run("2026-08", _MANAGER, background=False)
    service.start_run("2026-08", _MANAGER, background=False)
    assert len(service.competence_view("2026-08")["items"]) == 3
