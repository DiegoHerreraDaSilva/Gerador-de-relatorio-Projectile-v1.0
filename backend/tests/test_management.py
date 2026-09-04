"""Trava o cálculo de status "sent"/"partial"/"none" por (projeto, mês) em
`compute_monthly_kpis` — a mesma amostra de e-mail não pode mais marcar o
projeto inteiro como enviado quando cobre só 1 pacote de trabalho (ver
`management.py`, `project_send_status`, e a marca oculta em `generator.py`/
`email_ingest.py` que carrega o `pacote_scope` de cada amostra)."""
from __future__ import annotations

import json
from datetime import date

from backend.app import management


def _write_samples(data_file, samples):
    data_file.write_text(
        json.dumps({
            "manual_entries": {},
            "project_kpi_samples": samples,
            "processed_message_ids": [],
            "skipped_messages": [],
        }),
        encoding="utf-8",
    )


def _sample(project_id, month, pacote_scope, billed_hours=1.0, msg_id="m1"):
    return {
        "email_message_id": msg_id,
        "received_at": "2026-09-01T00:00:00Z",
        "sender": "diego.herrera@schwaben.com.br",
        "report_project_text": f"Projeto {project_id}",
        "project_id": project_id,
        "project_name": f"Projeto {project_id}",
        "match_score": 1.0,
        "month": month,
        "billed_hours": billed_hours,
        "business_days": 1,
        "pacote_scope": pacote_scope,
    }


def _row(project_id, pacote, hours, day=1):
    return {
        "data": date(2026, 8, day),
        "horas": hours,
        "pacote": pacote,
        "project_id": project_id,
        "cost_center": "CAD",
        "external": "1",
    }


def _patch_projectile(monkeypatch, rows):
    """`compute_monthly_kpis` só toca o banco de verdade através dessas
    funções (importadas em `management.py`) — substitui todas por dados
    fixos, sem precisar de uma conexão MySQL real pro teste."""
    monkeypatch.setattr(management, "open_connection", lambda: None)
    monkeypatch.setattr(management, "fetch_engineering_hours", lambda *a, **k: rows)
    monkeypatch.setattr(management, "fetch_clients_for_projects", lambda ids, conn=None: ["Cliente Teste"])
    monkeypatch.setattr(
        management,
        "fetch_project_details",
        lambda ids, conn=None: {pid: {"name": f"Projeto {pid}", "client": "Cliente Teste"} for pid in ids},
    )
    monkeypatch.setattr(
        management, "fetch_project_names_for_ids", lambda ids, conn=None: [f"Projeto {pid}" for pid in ids]
    )


def _find_status(result, project_id, month="2026-08"):
    for row in result["project_send_status"]:
        if row["project_id"] == project_id and row["month"] == month:
            return row
    raise AssertionError(f"nenhuma linha de project_send_status pra {project_id}/{month}")


def test_one_of_two_pacotes_sent_is_partial(monkeypatch, tmp_path):
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0), _row("P1", "Pacote B", 5.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope="Pacote A", billed_hours=10.0)])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "partial"
    assert row["missing_pacotes"] == ["Pacote B"]


def test_all_pacotes_sent_is_sent(monkeypatch, tmp_path):
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0), _row("P1", "Pacote B", 5.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(
        data_file,
        [
            _sample("P1", "2026-08", pacote_scope="Pacote A", billed_hours=10.0, msg_id="m1"),
            _sample("P1", "2026-08", pacote_scope="Pacote B", billed_hours=5.0, msg_id="m2"),
        ],
    )

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "sent"
    assert row["missing_pacotes"] == []


def test_null_pacote_scope_covers_whole_project(monkeypatch, tmp_path):
    """Amostra sem pacote_scope (None) — relatório "por projeto" ou dado
    antigo (de antes dessa funcionalidade existir) — cobre tudo de uma vez,
    mesmo comportamento de antes desta mudança."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0), _row("P1", "Pacote B", 5.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope=None, billed_hours=15.0)])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "sent"
    assert row["missing_pacotes"] == []


def test_no_samples_is_none(monkeypatch, tmp_path):
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "none"
    assert row["missing_pacotes"] == []
