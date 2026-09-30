"""Isolamento do histórico entre usuários (SQLite, sem Docker).

O `report` é a identidade compartilhada (número + escopo + competência): dois
usuários que geram o mesmo relatório viram versões do MESMO registro. Quem não
é gerente só acessa o que ele mesmo gerou — versões, gerações, arquivos,
auditoria e lista —, inclusive no histórico antigo, sem backfill (a versão 1 já
guarda o `created_by`). Gerente continua vendo tudo."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from backend.app.api.dependencies import require_session
from backend.app.core import authz
from backend.app.db.reports_schema import audit_log, metadata, report_artifacts, report_generation, report_source_snapshots, report_versions, reports
from backend.app.main import app
from backend.app.services import report_queries

_ALICE = {"name": "Alice", "login": "alice", "email": "a@x", "employee_id": "1", "filiale": None}
_BOB = {"name": "Bob", "login": "Bob", "email": "b@x", "employee_id": "2", "filiale": None}
_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x", "employee_id": "3", "filiale": None}
_NOW = datetime(2026, 9, 10, 12, 0, 0)


def _id(n: int) -> str:
    return f"{n:026d}"


@pytest.fixture
def history(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    wanted = [t for t in metadata.sorted_tables if not t.name.startswith(("mgmt_", "auto_"))]
    metadata.create_all(engine, tables=wanted)
    monkeypatch.setattr(report_queries, "get_engine", lambda: engine)
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})

    alice_file = tmp_path / "alice.xlsx"
    alice_file.write_bytes(b"alice")
    bob_file = tmp_path / "bob.xlsx"
    bob_file.write_bytes(b"bob")

    def snapshot(n: int) -> dict:
        return {"id": _id(n), "source_system": "test", "data_json": {"n": n}, "data_hash": f"h{n}", "schema_version": 1, "captured_at": _NOW}

    with engine.begin() as conn:
        conn.execute(insert(report_source_snapshots), [snapshot(10), snapshot(11)])
        conn.execute(
            insert(reports),
            [
                {
                    "id": _id(1),
                    "identity_hash": "x" * 64,
                    "report_number": "SE.01.001",
                    "scope": None,
                    "competence_label": "Setembro/2026",
                    "competence_start": datetime(2026, 9, 1).date(),
                    "competence_end": datetime(2026, 9, 30).date(),
                    "project_name_snapshot": "Projeto X",
                    "created_by": "alice",
                    "created_by_name_snapshot": "Alice",
                    "current_version_id": _id(21),  # a última geração foi do Bob
                    "status": "generated",
                    "created_at": _NOW,
                    "updated_at": _NOW,
                }
            ],
        )
        conn.execute(
            insert(report_versions),
            [
                {
                    "id": _id(20),
                    "report_id": _id(1),
                    "version_number": 1,
                    "source_snapshot_id": _id(10),
                    "created_by": "alice",
                    "created_from": "generate_endpoint",
                    "created_at": _NOW,
                },
                {
                    "id": _id(21),
                    "report_id": _id(1),
                    "version_number": 2,
                    "source_snapshot_id": _id(11),
                    "created_by": "bob",
                    "created_from": "generate_endpoint",
                    "created_at": _NOW,
                },
            ],
        )
        conn.execute(
            insert(report_generation),
            [
                {
                    "id": _id(30),
                    "report_id": _id(1),
                    "report_version_id": _id(20),
                    "format": "xlsx",
                    "requested_by": "alice",
                    "started_at": _NOW,
                    "finished_at": _NOW,
                    "status": "success",
                },
                {
                    "id": _id(31),
                    "report_id": _id(1),
                    "report_version_id": _id(21),
                    "format": "xlsx",
                    "requested_by": "bob",
                    "started_at": _NOW,
                    "finished_at": _NOW,
                    "status": "success",
                },
            ],
        )
        conn.execute(
            insert(report_artifacts),
            [
                {
                    "id": _id(40),
                    "generation_id": _id(30),
                    "artifact_type": "xlsx",
                    "storage_path": str(alice_file),
                    "file_name": "alice.xlsx",
                    "mime_type": "x/y",
                    "file_size": 5,
                    "sha256": "a" * 64,
                    "created_at": _NOW,
                },
                {
                    "id": _id(41),
                    "generation_id": _id(31),
                    "artifact_type": "xlsx",
                    "storage_path": str(bob_file),
                    "file_name": "bob.xlsx",
                    "mime_type": "x/y",
                    "file_size": 3,
                    "sha256": "b" * 64,
                    "created_at": _NOW,
                },
            ],
        )
        conn.execute(
            insert(audit_log),
            [
                {
                    "id": _id(50),
                    "actor_id": "alice",
                    "actor_name_snapshot": "Alice",
                    "action": "report_generated",
                    "entity_type": "report_version",
                    "entity_id": _id(20),
                    "source": "generate_endpoint",
                    "created_at": _NOW,
                },
                {
                    "id": _id(51),
                    "actor_id": "bob",
                    "actor_name_snapshot": "Bob",
                    "action": "report_generated",
                    "entity_type": "report_version",
                    "entity_id": _id(21),
                    "source": "generate_endpoint",
                    "created_at": _NOW,
                },
            ],
        )
    yield engine
    app.dependency_overrides.pop(require_session, None)
    engine.dispose()


def _as(user: dict) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


def test_cada_usuario_ve_so_a_propria_versao_e_a_propria_atual(history):
    alice = _as(_ALICE).get(f"/reports/{_id(1)}")
    assert alice.status_code == 200
    assert alice.json()["current_version_number"] == 1

    bob = _as(_BOB).get(f"/reports/{_id(1)}")
    assert bob.status_code == 200  # antes: 403 (autorizava só pelo primeiro criador)
    assert bob.json()["current_version_number"] == 2

    versions_alice = _as(_ALICE).get(f"/reports/{_id(1)}/versions").json()
    versions_bob = _as(_BOB).get(f"/reports/{_id(1)}/versions").json()
    assert [v["version_number"] for v in versions_alice["items"]] == [1]
    assert [v["version_number"] for v in versions_bob["items"]] == [2]


def test_snapshot_de_outra_pessoa_nao_abre(history):
    assert _as(_ALICE).get(f"/reports/{_id(1)}/versions/{_id(20)}").status_code == 200
    assert _as(_ALICE).get(f"/reports/{_id(1)}/versions/{_id(21)}").status_code == 404
    assert _as(_BOB).get(f"/reports/{_id(1)}/versions/{_id(21)}").status_code == 200
    assert _as(_BOB).get(f"/reports/{_id(1)}/versions/{_id(20)}").status_code == 404


def test_geracoes_arquivos_e_auditoria_sao_so_do_dono(history):
    for user, own_gen, own_art in ((_ALICE, _id(30), _id(40)), (_BOB, _id(31), _id(41))):
        client = _as(user)
        assert [g["id"] for g in client.get(f"/reports/{_id(1)}/generations").json()["items"]] == [own_gen]
        assert [a["id"] for a in client.get(f"/reports/{_id(1)}/artifacts").json()["items"]] == [own_art]
        audit = client.get(f"/reports/{_id(1)}/audit").json()["items"]
        assert {e["actor_id"] for e in audit} == {user["login"].lower()}


def test_download_so_do_proprio_arquivo(history):
    assert _as(_ALICE).get(f"/artifacts/{_id(40)}/download").content == b"alice"
    assert _as(_ALICE).get(f"/artifacts/{_id(41)}/download").status_code == 403
    assert _as(_BOB).get(f"/artifacts/{_id(41)}/download").content == b"bob"
    assert _as(_BOB).get(f"/artifacts/{_id(40)}/download").status_code == 403


def test_lista_so_tem_relatorios_do_usuario_e_nao_expoe_o_primeiro_criador(history):
    alice = _as(_ALICE).get("/reports").json()
    assert alice["total"] == 1 and alice["items"][0]["created_by"] == "alice"

    bob = _as(_BOB).get("/reports").json()
    assert bob["total"] == 1  # antes: lista vazia
    assert bob["items"][0]["created_by"] == "Bob"
    assert bob["items"][0]["created_by_name_snapshot"] == "Bob"
    assert bob["items"][0]["current_version_number"] == 2


def test_usuario_sem_versao_no_relatorio_nao_acessa(history):
    carol = {"name": "Carol", "login": "carol", "email": "c@x", "employee_id": "9", "filiale": None}
    assert _as(carol).get("/reports").json()["total"] == 0
    assert _as(carol).get(f"/reports/{_id(1)}").status_code == 403
    assert _as(carol).get(f"/reports/{_id(1)}/versions").status_code == 403
    assert _as(carol).get(f"/artifacts/{_id(40)}/download").status_code == 403


def test_gerente_continua_vendo_tudo(history):
    client = _as(_MANAGER)
    assert client.get(f"/reports/{_id(1)}").json()["current_version_number"] == 2
    assert client.get(f"/reports/{_id(1)}/versions").json()["total"] == 2
    assert client.get(f"/reports/{_id(1)}/generations").json()["total"] == 2
    assert client.get(f"/reports/{_id(1)}/artifacts").json()["total"] == 2
    assert client.get(f"/reports/{_id(1)}/audit").json()["total"] == 2
    assert client.get(f"/artifacts/{_id(41)}/download").status_code == 200
    assert client.get("/reports").json()["items"][0]["created_by"] == "alice"
