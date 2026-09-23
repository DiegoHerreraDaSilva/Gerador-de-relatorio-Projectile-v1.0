"""Persistência do Painel de Gerência/Diagnóstico em reports_db
(`services/management_store.py`) e a importação do antigo
management_kpi.json. Testes de REGRA (status de envio, duplicatas) ficam em
test_management.py; aqui fica o que depende do banco em si:

- `reports_db`: MySQL real (lock entre conexões, collation binária);
- os demais usam o SQLite da fixture `management_db`."""
from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import management
from backend.app.services import management_store
from backend.app.tools import import_management_json


def _email_sample(sample_id: str, msg_id: str, **overrides) -> dict:
    sample = {
        "email_message_id": msg_id, "received_at": "2026-09-10T12:00:00Z",
        "sender": "alberto@schwaben.com.br", "report_project_text": "Projeto X", "project_id": "P1",
        "project_name": "Projeto X", "match_score": 0.93, "month": "2026-08",
        "billed_hours": 10.25, "business_days": 3, "pacote_scope": None, "sample_id": sample_id,
    }
    sample.update(overrides)
    return sample


def _legacy_document(**overrides) -> dict:
    document = {
        "manual_entries": {"2026-07": {"billed_hours": 150.5, "elaboration_days": None}},
        "project_kpi_samples": [_email_sample("s1", "msg-1", pacote_scope="Pacote A", extra_field="x")],
        "processed_message_ids": ["msg-1", "msg-2"],
        "skipped_messages": [{"message_id": "msg-2", "received_at": "2026-09-11T08:00:00Z", "reason": "sem anexo"}],
        "closed_clients": ["Cliente Fechado"],
        "closed_projects": ["P9"],
        "nonbillable_packages": ["Treinamento"],
    }
    document.update(overrides)
    return document


# --- MySQL real -------------------------------------------------------------


@pytest.mark.reports_db
def test_escrita_concorrente_espera_o_lock_e_nao_perde_dado(reports_db_engine):
    """Substitui o antigo teste do `threading.RLock`: uma escrita "lenta"
    (o polling de e-mail, que segura a transação enquanto processa) e uma
    "rápida" (o gerente salvando pelo Diagnóstico) não podem se sobrescrever.
    A rápida espera no `SELECT ... FOR UPDATE` até a lenta commitar."""
    # a fixture trunca `mgmt_meta`; em produção a linha de lock vem da
    # migration 0006. Cria antes, pra este teste medir o lock em si.
    with management_store.write_session():
        pass
    slow_holds_lock = threading.Event()
    release_slow = threading.Event()
    finished = []

    def slow_writer():
        with management_store.write_session() as session:
            slow_holds_lock.set()
            release_slow.wait(timeout=5)
            session.upsert_manual_entry("2026-08", 100.0, 5.0)
        finished.append("slow")

    def fast_writer():
        management.append_project_kpi_sample(_email_sample("s1", "manual-x", source="manual"))
        finished.append("fast")

    slow = threading.Thread(target=slow_writer)
    slow.start()
    assert slow_holds_lock.wait(timeout=5)
    fast = threading.Thread(target=fast_writer)
    fast.start()
    time.sleep(0.5)
    assert finished == [], "a escrita rápida deveria estar bloqueada esperando o lock"
    release_slow.set()
    slow.join(timeout=10)
    fast.join(timeout=10)

    assert finished == ["slow", "fast"]
    document = management_store.load_document()
    assert document["manual_entries"]["2026-08"] == {"billed_hours": 100.0, "elaboration_days": 5.0}
    assert [s["sample_id"] for s in document["project_kpi_samples"]] == ["s1"]


@pytest.mark.reports_db
def test_ids_que_diferem_so_na_caixa_sao_distintos_no_mysql(reports_db_engine):
    """O collation padrão das tabelas ignora caixa; ids do Graph não —
    `_exact_string` precisa manter os dois como chaves diferentes."""
    management.append_skipped_message("AAMkAD-abc", "2026-09-10T12:00:00Z", "teste")

    assert management.is_message_processed("AAMkAD-abc") is True
    assert management.is_message_processed("AAMKAD-ABC") is False
    management.append_skipped_message("AAMKAD-ABC", "2026-09-10T12:00:00Z", "teste")
    assert len(management_store.load_document()["processed_message_ids"]) == 2


@pytest.mark.reports_db
def test_importacao_preserva_os_dados_no_mysql(reports_db_engine):
    result = management.import_legacy_document(_legacy_document(), source_path="/tmp/management_kpi.json")
    assert result["status"] == "imported"

    document = management_store.load_document()
    assert document["manual_entries"] == {"2026-07": {"billed_hours": 150.5, "elaboration_days": None}}
    sample = document["project_kpi_samples"][0]
    assert sample["billed_hours"] == 10.25
    assert sample["business_days"] == 3
    assert sample["match_score"] == 0.93
    assert sample["pacote_scope"] == ["Pacote A"]
    assert sample["extra_field"] == "x"
    assert sample["source"] == "email" and sample["edited"] is False and sample["is_duplicate"] is False
    assert sorted(document["processed_message_ids"]) == ["msg-1", "msg-2"]
    assert document["skipped_messages"] == [
        {"message_id": "msg-2", "received_at": "2026-09-11T08:00:00Z", "reason": "sem anexo"}
    ]
    assert document["closed_clients"] == ["Cliente Fechado"]
    assert document["closed_projects"] == ["P9"]

    with management_store.write_session() as session:
        meta = session.get_meta(management_store.LEGACY_IMPORT_KEY)
    assert meta["ignored_top_level_keys"] == {"nonbillable_packages": ["Treinamento"]}


# --- SQLite (sem Docker) ----------------------------------------------------


def test_segunda_importacao_nao_duplica(management_db):
    management.import_legacy_document(_legacy_document())
    again = management.import_legacy_document(_legacy_document())

    assert again == {"status": "already_imported"}
    assert len(management_store.load_document()["project_kpi_samples"]) == 1


def test_importacao_recusa_banco_que_ja_tem_dado(management_db):
    """Dado criado pela tela ANTES de qualquer importação — misturar um JSON
    por cima duplicaria amostras sem ninguém perceber."""
    management.set_manual_entry("2026-08", 10.0, 1.0)

    with pytest.raises(management_store.ManagementStoreError):
        management.import_legacy_document(_legacy_document())


def test_replace_existing_prefere_o_json_e_guarda_o_descartado(management_db):
    """Cenário real encontrado ao migrar o ambiente de dev: o backend novo
    subiu antes da importação e o polling recriou as amostras a partir dos
    e-mails — com o match automático original, não com a correção manual
    (`edited=True`) que só o JSON tinha. O JSON tem que prevalecer."""
    management.append_project_kpi_sample(_email_sample("do-polling", "msg-1", project_id="P-ERRADO"))
    corrected = _email_sample("corrigida", "msg-1", project_id="P-CERTO", edited=True)

    result = management.import_legacy_document(
        _legacy_document(project_kpi_samples=[corrected]), replace_existing=True,
    )

    assert result["replaced_samples"] == 1
    samples = management_store.load_document()["project_kpi_samples"]
    assert [(s["sample_id"], s["project_id"], s["edited"]) for s in samples] == [("corrigida", "P-CERTO", True)]
    with management_store.write_session() as session:
        meta = session.get_meta(management_store.LEGACY_IMPORT_KEY)
    assert meta["replaced_existing_data"]["project_kpi_samples"][0]["project_id"] == "P-ERRADO"


def test_ordem_de_insercao_desempata_duplicata_com_mesmo_received_at(management_db):
    """Mesma identidade e mesmo `received_at`: a primeira da lista do JSON é
    a original, as outras são duplicatas — igual a quando isso vivia no
    arquivo (sort estável por `received_at`)."""
    management.import_legacy_document(_legacy_document(project_kpi_samples=[
        _email_sample("primeira", "m1"), _email_sample("segunda", "m2"),
    ]))

    flags = {s["sample_id"]: s["is_duplicate"] for s in management_store.load_document()["project_kpi_samples"]}
    assert flags == {"primeira": False, "segunda": True}


def test_append_devolve_flag_de_duplicata_e_marca_processado(management_db):
    assert management.append_project_kpi_sample(_email_sample("s1", "m1")) is False
    assert management.append_project_kpi_sample(_email_sample("s2", "m2")) is True
    assert management.is_message_processed("m1") and management.is_message_processed("m2")


def test_ferramenta_importa_e_renomeia_o_json(management_db, tmp_path, capsys):
    path = tmp_path / "management_kpi.json"
    path.write_text(json.dumps(_legacy_document()), encoding="utf-8")

    assert import_management_json.main(["--path", str(path)]) == 0

    assert not path.exists()
    backups = list(tmp_path.glob("management_kpi.json.migrated-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == _legacy_document()
    assert "project_kpi_samples=1" in capsys.readouterr().out


def test_ferramenta_sem_arquivo_nao_faz_nada(management_db, tmp_path):
    assert import_management_json.main(["--path", str(tmp_path / "nao_existe.json")]) == 0
    assert management_store.load_document()["project_kpi_samples"] == []


def test_ferramenta_avisa_de_json_gravado_depois_da_importacao(management_db, tmp_path, capsys):
    """O backend antigo continua rodando até o restart e pode recriar o
    JSON depois da importação — o aviso é o que impede esse dado de sumir
    sem ninguém notar."""
    management.import_legacy_document(_legacy_document())
    path = tmp_path / "management_kpi.json"
    path.write_text(json.dumps(_legacy_document(project_kpi_samples=[_email_sample("tardia", "m9")])), encoding="utf-8")

    assert import_management_json.main(["--path", str(path)]) == 0

    assert "ATENÇÃO" in capsys.readouterr().out
    assert not path.exists()


def test_falha_do_banco_vira_502_com_mensagem_generica(management_db, monkeypatch):
    from backend.app.main import app, require_session

    monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", {"dherrera"})
    app.dependency_overrides[require_session] = lambda: {"name": "Diego", "login": "dherrera", "email": "d@x"}

    def _down():
        raise management_store.ManagementStoreError("connection refused 127.0.0.1:3307")

    monkeypatch.setattr(management_store, "load_document", _down)
    try:
        with TestClient(app) as client:
            response = client.get("/management/kpis/samples")
    finally:
        app.dependency_overrides.pop(require_session, None)

    assert response.status_code == 502
    assert "3307" not in response.text
    assert response.json()["detail"] == "Erro ao acessar os dados do painel de gerência. Tente de novo em instantes."
