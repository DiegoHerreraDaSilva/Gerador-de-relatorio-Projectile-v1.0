"""Apagar relatórios do histórico (só gerente) e ordenar as colunas da lista. SQLite, sem Docker."""

from __future__ import annotations

import os
from datetime import datetime

import pytest
from sqlalchemy import func, insert, select

from backend.app.db.reports_schema import audit_log, report_artifacts, report_generation, report_source_snapshots, report_versions, reports
from backend.app.services import report_persistence

from .test_history_isolation import _ALICE, _MANAGER, _NOW, _as, _id, history  # noqa: F401 — fixture reaproveitada


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


def _delete(client, ids):
    return client.request("DELETE", "/reports", json={"ids": ids})


def test_gerente_apaga_relatorio_com_tudo_dentro_e_os_arquivos(history, artifacts_dir):
    response = _delete(_as(_MANAGER), [_id(1)])
    assert response.status_code == 200
    body = response.json()
    assert [d["report_number"] for d in body["deleted"]] == ["SE.01.001"] and body["deleted"][0]["versions"] == 2
    assert body["not_found"] == [] and body["files_removed"] == 2

    for table in (reports, report_versions, report_generation, report_artifacts, report_source_snapshots):
        assert _count(history, table) == 0, table.name
    assert not any(os.path.exists(p) for p in artifacts_dir)
    assert _as(_MANAGER).get(f"/reports/{_id(1)}").status_code == 404


def test_a_auditoria_fica_e_ganha_o_evento_de_exclusao(history, artifacts_dir):
    _delete(_as(_MANAGER), [_id(1)])
    with history.connect() as conn:
        actions = [r.action for r in conn.execute(select(audit_log.c.action))]
    assert actions.count("report_generated") == 2  # a trilha antiga continua
    assert "report_deleted" in actions


def test_so_gerente_apaga_ou_lista_ids(history):
    assert _delete(_as(_ALICE), [_id(1)]).status_code == 403
    assert _as(_ALICE).get("/reports/ids").status_code == 403
    assert _count(history, reports) == 1


def test_id_inexistente_repetido_e_limite(history, artifacts_dir):
    manager = _as(_MANAGER)
    result = _delete(manager, [_id(1), _id(1), _id(99)]).json()
    assert len(result["deleted"]) == 1 and result["not_found"] == [_id(99)]
    assert _delete(manager, []).status_code == 422
    assert _delete(manager, [f"{i:026d}" for i in range(201)]).status_code == 422


def test_arquivo_fora_do_diretorio_de_artefatos_nunca_e_apagado(history, tmp_path, monkeypatch):
    base = tmp_path / "artifacts"
    base.mkdir()
    monkeypatch.setattr(report_persistence, "ARTIFACTS_DIR", str(base))
    outside = tmp_path / "importante.txt"
    outside.write_text("fica")
    with history.begin() as conn:
        conn.execute(report_artifacts.update().where(report_artifacts.c.id == _id(40)).values(storage_path=str(outside)))
    _delete(_as(_MANAGER), [_id(1)])
    assert outside.exists()


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
