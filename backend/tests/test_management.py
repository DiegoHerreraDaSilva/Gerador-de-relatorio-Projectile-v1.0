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


# ---------------------------------------------------------------------------
# is_duplicate — mesmo relatório (projeto+mês+pacote) chegando de novo por
# e-mail (reenvio acidental ou duplicado) não pode contar billed_hours duas
# vezes em compute_monthly_kpis (ver management._recompute_duplicate_flags).
# ---------------------------------------------------------------------------

def _find_sample(samples, msg_id):
    for s in samples:
        if s["email_message_id"] == msg_id:
            return s
    raise AssertionError(f"nenhuma amostra com email_message_id={msg_id!r}")


def _month_billed_hours(result, month="2026-08"):
    for row in result["months"]:
        if row["month"] == month:
            return row["billed_hours"]
    raise AssertionError(f"nenhuma linha de months pra {month}")


def test_second_sample_same_identity_is_flagged_duplicate(tmp_path, monkeypatch):
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    first_is_dup = management.append_project_kpi_sample(_sample("P1", "2026-08", pacote_scope=None, msg_id="m1"))
    second_is_dup = management.append_project_kpi_sample(_sample("P1", "2026-08", pacote_scope=None, msg_id="m2"))

    assert first_is_dup is False
    assert second_is_dup is True
    samples = management.list_samples()["samples"]
    assert _find_sample(samples, "m1")["is_duplicate"] is False
    assert _find_sample(samples, "m2")["is_duplicate"] is True


def test_duplicate_even_with_different_hours(tmp_path, monkeypatch):
    """Decisão do usuário: ignora sempre que a identidade já existir, mesmo
    que o valor de horas do reenvio seja diferente do já registrado — não
    tenta adivinhar se é correção ou engano (correção de verdade usa o
    override manual do Painel de Gerência)."""
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    management.append_project_kpi_sample(
        _sample("P1", "2026-08", pacote_scope=None, billed_hours=10.0, msg_id="m1")
    )
    second_is_dup = management.append_project_kpi_sample(
        _sample("P1", "2026-08", pacote_scope=None, billed_hours=999.0, msg_id="m2")
    )

    assert second_is_dup is True


def test_manual_sample_never_marked_duplicate(tmp_path, monkeypatch):
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope=None, billed_hours=10.0, msg_id="m1")])

    management.create_manual_project_kpi_sample("P1", "Projeto P1", "2026-08", 10.0, 2.0)

    samples = management.list_samples()["samples"]
    manual_sample = next(s for s in samples if s["source"] == "manual")
    assert manual_sample["is_duplicate"] is False


def test_deleting_original_sample_promotes_next_to_non_duplicate(tmp_path, monkeypatch):
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])
    management.append_project_kpi_sample(_sample("P1", "2026-08", pacote_scope=None, msg_id="m1"))
    management.append_project_kpi_sample(_sample("P1", "2026-08", pacote_scope=None, msg_id="m2"))
    original_id = _find_sample(management.list_samples()["samples"], "m1")["sample_id"]

    management.delete_project_kpi_sample(original_id)

    remaining = management.list_samples()["samples"]
    assert len(remaining) == 1
    assert _find_sample(remaining, "m2")["is_duplicate"] is False


def test_duplicate_excluded_from_billed_hours_sum(monkeypatch, tmp_path):
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(
        data_file,
        [
            _sample("P1", "2026-08", pacote_scope=None, billed_hours=10.0, msg_id="m1"),
            _sample("P1", "2026-08", pacote_scope=None, billed_hours=10.0, msg_id="m2"),
        ],
    )

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)

    assert _month_billed_hours(result) == 10.0  # não 20.0 — m2 é duplicata de m1


def test_different_pacote_scope_is_not_duplicate(monkeypatch, tmp_path):
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

    assert _month_billed_hours(result) == 15.0  # pacotes diferentes — não é o mesmo relatório
