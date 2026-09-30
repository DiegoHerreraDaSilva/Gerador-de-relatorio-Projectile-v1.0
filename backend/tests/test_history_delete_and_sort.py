"""Lixeira do Histórico (só gerente): apagar = mover pra lixeira (restaurável), apagar definitivamente, purga
automática depois de 30 dias — e ordenar as colunas. SQLite, sem Docker."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, insert, select, update

from backend.app.auto_generation import scheduler
from backend.app.db.reports_schema import (
    audit_log,
    report_activities,
    report_artifacts,
    report_generation,
    report_groups,
    report_source_snapshots,
    report_versions,
    reports,
)
from backend.app.services import auto_generation_store, report_admin, report_persistence, report_queries

from .test_history_isolation import _ALICE, _MANAGER, _NOW, _as, _id, history  # noqa: F401 — fixture reaproveitada

ALL_TABLES = (reports, report_versions, report_generation, report_artifacts, report_source_snapshots)


@pytest.fixture
def artifacts_dir(history, monkeypatch, tmp_path):  # noqa: F811
    """Os arquivos do seed passam a morar dentro do diretório de artefatos."""
    base = tmp_path / "artifacts"
    (base / "r1").mkdir(parents=True)
    monkeypatch.setattr(report_persistence, "ARTIFACTS_DIR", str(base))
    files = []
    with history.begin() as conn:
        for artifact_id, name in ((_id(40), "alice.xlsx"), (_id(41), "bob.xlsx")):
            path = base / "r1" / name
            path.write_bytes(b"x")
            conn.execute(report_artifacts.update().where(report_artifacts.c.id == artifact_id).values(storage_path=str(path)))
            files.append(str(path))
    return files


def _count(engine, table) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


def _trash(client, ids):
    return client.request("DELETE", "/reports", json={"ids": ids})


def _restore(client, ids):
    return client.post("/reports/restore", json={"ids": ids})


def _purge(client, ids):
    return client.request("DELETE", "/reports/trash", json={"ids": ids})


def _deleted_at(engine, report_id):
    with engine.connect() as conn:
        return conn.execute(select(reports.c.deleted_at).where(reports.c.id == report_id)).scalar_one()


# --- apagar = lixeira ------------------------------------------------------------------------------


def test_apagar_move_pra_lixeira_e_nao_apaga_nada(history, artifacts_dir):
    response = _trash(_as(_MANAGER), [_id(1)])
    assert response.status_code == 200
    body = response.json()
    assert [t["report_number"] for t in body["trashed"]] == ["SE.01.001"] and body["not_found"] == []

    assert _deleted_at(history, _id(1)) is not None
    for table in ALL_TABLES:
        assert _count(history, table) > 0, f"{table.name} não pode perder linha"
    assert all(os.path.exists(p) for p in artifacts_dir), "os arquivos ficam no disco até a purga"


def test_na_lixeira_some_do_historico_do_detalhe_e_do_download(history, artifacts_dir):
    manager = _as(_MANAGER)
    assert manager.get("/reports").json()["total"] == 1
    _trash(manager, [_id(1)])
    assert manager.get("/reports").json()["total"] == 0
    assert manager.get("/reports/ids").json()["total"] == 0
    assert manager.get(f"/reports/{_id(1)}").status_code == 404
    assert manager.get(f"/reports/{_id(1)}/versions").status_code == 404
    assert manager.get(f"/artifacts/{_id(40)}/download").status_code == 404


def test_a_lixeira_lista_so_o_apagado_e_so_pro_gerente(history, artifacts_dir):
    manager = _as(_MANAGER)
    assert manager.get("/reports", params={"trash": "true"}).json()["total"] == 0
    _trash(manager, [_id(1)])
    trash = manager.get("/reports", params={"trash": "true"}).json()
    assert [r["id"] for r in trash["items"]] == [_id(1)]
    assert trash["items"][0]["deleted_by"] == "gerente" and trash["items"][0]["deleted_at"]
    assert manager.get("/reports/ids", params={"trash": "true"}).json()["ids"] == [_id(1)]
    assert _as(_ALICE).get("/reports", params={"trash": "true"}).status_code == 403


def test_restaurar_traz_tudo_de_volta(history, artifacts_dir):
    manager = _as(_MANAGER)
    _trash(manager, [_id(1)])
    response = _restore(manager, [_id(1), _id(99)])
    assert response.status_code == 200
    assert [r["id"] for r in response.json()["restored"]] == [_id(1)] and response.json()["not_found"] == [_id(99)]
    assert _deleted_at(history, _id(1)) is None
    assert manager.get(f"/reports/{_id(1)}").status_code == 200
    assert manager.get(f"/artifacts/{_id(40)}/download").content == b"x"  # o fixture grava "x" nos arquivos
    assert _restore(manager, [_id(1)]).json()["restored"] == []  # já está vivo


def test_trash_repetido_ou_ja_na_lixeira_nao_duplica(history, artifacts_dir):
    manager = _as(_MANAGER)
    assert len(_trash(manager, [_id(1), _id(1)]).json()["trashed"]) == 1
    again = _trash(manager, [_id(1)]).json()
    assert again["trashed"] == [] and again["not_found"] == [_id(1)]


# --- apagar definitivamente --------------------------------------------------------------------------


def test_purga_so_vale_pra_quem_ja_esta_na_lixeira(history, artifacts_dir):
    manager = _as(_MANAGER)
    refused = _purge(manager, [_id(1)]).json()
    assert refused["deleted"] == [] and refused["not_found"] == [_id(1)]
    assert _count(history, reports) == 1  # relatório vivo não é apagado por aqui


def test_purga_apaga_tudo_e_os_arquivos_do_disco(history, artifacts_dir):
    manager = _as(_MANAGER)
    _trash(manager, [_id(1)])
    body = _purge(manager, [_id(1)]).json()
    assert [d["report_number"] for d in body["deleted"]] == ["SE.01.001"] and body["deleted"][0]["versions"] == 2
    assert body["files_removed"] == 2
    for table in ALL_TABLES:
        assert _count(history, table) == 0, table.name
    assert not any(os.path.exists(p) for p in artifacts_dir)


def test_purga_nunca_apaga_arquivo_fora_do_diretorio_de_artefatos(history, tmp_path, monkeypatch):
    base = tmp_path / "artifacts"
    base.mkdir()
    monkeypatch.setattr(report_persistence, "ARTIFACTS_DIR", str(base))
    outside = tmp_path / "importante.txt"
    outside.write_text("fica")
    with history.begin() as conn:
        conn.execute(report_artifacts.update().where(report_artifacts.c.id == _id(40)).values(storage_path=str(outside)))
    manager = _as(_MANAGER)
    _trash(manager, [_id(1)])
    _purge(manager, [_id(1)])
    assert outside.exists()


# --- auditoria, papéis e limites ----------------------------------------------------------------------


def test_a_auditoria_registra_lixeira_restauracao_e_purga(history, artifacts_dir):
    manager = _as(_MANAGER)
    _trash(manager, [_id(1)])
    _restore(manager, [_id(1)])
    _trash(manager, [_id(1)])
    _purge(manager, [_id(1)])
    with history.connect() as conn:
        actions = [r.action for r in conn.execute(select(audit_log.c.action).order_by(audit_log.c.created_at))]
    assert actions.count("report_generated") == 2  # a trilha antiga continua
    for action in ("report_trashed", "report_restored", "report_deleted"):
        assert action in actions


def test_so_gerente_apaga_restaura_purga_ou_lista_ids(history):
    alice = _as(_ALICE)
    assert _trash(alice, [_id(1)]).status_code == 403
    assert _restore(alice, [_id(1)]).status_code == 403
    assert _purge(alice, [_id(1)]).status_code == 403
    assert alice.get("/reports/ids").status_code == 403
    assert _deleted_at(history, _id(1)) is None


def test_ids_inexistentes_vazios_e_acima_do_limite(history, artifacts_dir):
    manager = _as(_MANAGER)
    assert _trash(manager, [_id(99)]).json() == {"trashed": [], "not_found": [_id(99)]}
    for call in (_trash, _restore, _purge):
        assert call(manager, []).status_code == 422
        assert call(manager, [f"{i:026d}" for i in range(201)]).status_code == 422


# --- as outras leituras ignoram a lixeira ---------------------------------------------------------------


def test_gerar_de_novo_um_relatorio_da_lixeira_traz_ele_de_volta(history):
    _trash(_as(_MANAGER), [_id(1)])
    with history.begin() as conn:
        report_id, created = report_persistence._find_or_create_report(
            conn, "x" * 64, "SE.01.001", None, "Setembro/2026", None, None, "Projeto X", "alice", "Alice", _NOW
        )
    assert (report_id, created) == (_id(1), False)  # mesma identidade: não cria um segundo
    assert _deleted_at(history, _id(1)) is None
    assert _count(history, reports) == 1


def test_numero_de_relatorio_na_lixeira_volta_a_ficar_livre(history, monkeypatch):
    monkeypatch.setattr(auto_generation_store, "get_engine", lambda: history)
    assert auto_generation_store.find_history_numbers(["SE.01.001"])
    _trash(_as(_MANAGER), [_id(1)])
    assert auto_generation_store.find_history_numbers(["SE.01.001"]) == []
    _restore(_as(_MANAGER), [_id(1)])
    assert auto_generation_store.find_history_numbers(["SE.01.001"])


def test_horas_do_analytics_nao_contam_relatorio_na_lixeira(history):
    with history.begin() as conn:
        conn.execute(insert(report_groups), [{"id": _id(60), "report_version_id": _id(21), "name": "G", "performance": 1, "position": 0, "created_at": _NOW}])
        conn.execute(
            insert(report_activities), [{"id": _id(61), "report_group_id": _id(60), "description": "a", "hours": 8.0, "position": 0, "created_at": _NOW}]
        )

    def by_project():
        with history.connect() as conn:
            return report_queries._hours_breakdown(conn, reports.c.project_name_snapshot, "project_name")

    assert [r["project_name"] for r in by_project()] == ["Projeto X"]
    _trash(_as(_MANAGER), [_id(1)])
    assert by_project() == []


# --- purga automática ------------------------------------------------------------------------------------


def test_purga_automatica_so_apaga_o_que_passou_de_30_dias(history, artifacts_dir):
    now = datetime(2026, 10, 30, 12, 0)
    _add_report(history, 1, "SE.02.000", "Velho", "Julho/2026", datetime(2026, 7, 1).date(), "carlos", 1, _NOW)
    _add_report(history, 2, "SE.03.000", "Recente", "Julho/2026", datetime(2026, 7, 1).date(), "bia", 1, _NOW)
    with history.begin() as conn:
        conn.execute(update(reports).where(reports.c.id == _id(101)).values(deleted_at=now - timedelta(days=31), deleted_by="gerente"))
        conn.execute(update(reports).where(reports.c.id == _id(102)).values(deleted_at=now - timedelta(days=29), deleted_by="gerente"))
        conn.execute(update(reports).where(reports.c.id == _id(1)).values(deleted_at=now - timedelta(days=90), deleted_by="gerente"))
    assert report_admin.purge_expired(now=now) == 2  # o velho e o do seed; o de 29 dias fica
    with history.connect() as conn:
        assert [r.id for r in conn.execute(select(reports.c.id))] == [_id(102)]
    assert not any(os.path.exists(p) for p in artifacts_dir)  # os arquivos do que foi purgado saíram


def test_purga_automatica_nunca_toca_relatorio_vivo(history):
    assert report_admin.purge_expired(now=datetime(2030, 1, 1)) == 0
    assert _count(history, reports) == 1


def test_o_agendador_purga_a_lixeira_uma_vez_por_dia(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "_last_purge_day", None)
    monkeypatch.setattr(report_admin, "purge_expired", lambda: calls.append(1) or 3)
    day = datetime(2026, 10, 30, 6, 0)
    assert scheduler.purge_trash_daily(day) == 3
    assert scheduler.purge_trash_daily(day + timedelta(hours=6)) == 0  # mesmo dia: não repete
    assert scheduler.purge_trash_daily(day + timedelta(days=1)) == 3
    assert len(calls) == 2


def test_falha_na_purga_nao_derruba_o_agendador_e_tenta_de_novo(monkeypatch):
    monkeypatch.setattr(scheduler, "_last_purge_day", None)

    def broken():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(report_admin, "purge_expired", broken)
    assert scheduler.purge_trash_daily(datetime(2026, 10, 30)) == 0  # não levanta
    monkeypatch.setattr(report_admin, "purge_expired", lambda: 1)
    assert scheduler.purge_trash_daily(datetime(2026, 10, 30)) == 1  # falhou antes: o dia não foi marcado


def _add_report(history, n, number, project, label, start, who, versions, updated):
    with history.begin() as conn:
        conn.execute(
            insert(report_source_snapshots),
            [
                {"id": _id(200 + n * 10 + v), "source_system": "t", "data_json": {}, "data_hash": f"{n}{v}", "schema_version": 1, "captured_at": _NOW}
                for v in range(versions)
            ],
        )
        conn.execute(
            insert(reports),
            [
                {
                    "id": _id(100 + n),
                    "identity_hash": f"{n}" * 64,
                    "report_number": number,
                    "scope": None,
                    "competence_label": label,
                    "competence_start": start,
                    "competence_end": start,
                    "project_name_snapshot": project,
                    "created_by": who,
                    "created_by_name_snapshot": who.title(),
                    "current_version_id": _id(300 + n * 10 + versions - 1),
                    "status": "generated",
                    "created_at": updated,
                    "updated_at": updated,
                }
            ],
        )
        conn.execute(
            insert(report_versions),
            [
                {
                    "id": _id(300 + n * 10 + v),
                    "report_id": _id(100 + n),
                    "version_number": v + 1,
                    "source_snapshot_id": _id(200 + n * 10 + v),
                    "created_by": who,
                    "created_from": "x",
                    "created_at": updated,
                }
                for v in range(versions)
            ],
        )


@pytest.fixture
def lista(history):  # noqa: F811
    """Três relatórios: o do seed (SE.01.001, Projeto X, set/2026, Alice, v2, 10/09) e dois novos."""
    _add_report(history, 1, "SE.02.000", "Zebra", "Agosto/2026", datetime(2026, 8, 1).date(), "carlos", 3, datetime(2026, 9, 1))
    _add_report(history, 2, "SE.00.500", "Abacate", "Julho/2026", datetime(2026, 7, 1).date(), "bia", 1, datetime(2026, 9, 20))
    return history


def _numbers(client, **params):
    return [r["report_number"] for r in client.get("/reports", params={"page_size": 50, **params}).json()["items"]]


def test_ordena_por_cada_coluna_nos_dois_sentidos(lista):
    manager = _as(_MANAGER)
    assert _numbers(manager, sort="numero", order="asc") == ["SE.00.500", "SE.01.001", "SE.02.000"]
    assert _numbers(manager, sort="numero", order="desc") == ["SE.02.000", "SE.01.001", "SE.00.500"]
    assert _numbers(manager, sort="projeto", order="asc") == ["SE.00.500", "SE.01.001", "SE.02.000"]  # Abacate, Projeto X, Zebra
    assert _numbers(manager, sort="competencia", order="asc") == ["SE.00.500", "SE.02.000", "SE.01.001"]  # jul, ago, set
    assert _numbers(manager, sort="versao", order="desc") == ["SE.02.000", "SE.01.001", "SE.00.500"]  # v3, v2, v1
    assert _numbers(manager, sort="criado_por", order="asc") == ["SE.01.001", "SE.00.500", "SE.02.000"]  # Alice, Bia, Carlos
    assert _numbers(manager, sort="atualizado", order="asc") == ["SE.02.000", "SE.01.001", "SE.00.500"]  # 01/09, 10/09, 20/09


def test_padrao_e_mais_recente_primeiro_e_parametro_invalido_e_422(lista):
    manager = _as(_MANAGER)
    assert _numbers(manager) == ["SE.00.500", "SE.01.001", "SE.02.000"]  # atualizado em 20/09, 10/09, 01/09
    assert manager.get("/reports", params={"sort": "senha"}).status_code == 422
    assert manager.get("/reports", params={"order": "sideways"}).status_code == 422


def test_quem_nao_e_gerente_ordena_so_dentro_do_que_enxerga(lista):
    assert _numbers(_as(_ALICE), sort="versao", order="asc") == ["SE.01.001"]


def test_ids_do_filtro_para_selecionar_todos(lista):
    manager = _as(_MANAGER)
    everything = manager.get("/reports/ids").json()
    assert everything["total"] == 3 and len(everything["ids"]) == 3 and everything["truncated"] is False
    filtered = manager.get("/reports/ids", params={"q": "abacate"}).json()
    assert filtered["ids"] == [_id(102)] and filtered["total"] == 1
