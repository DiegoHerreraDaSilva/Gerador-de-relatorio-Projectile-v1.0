"""Trava o cálculo de status "sent"/"partial"/"none" por (projeto, mês) em
`compute_monthly_kpis` — a mesma amostra de e-mail não pode mais marcar o
projeto inteiro como enviado quando cobre só 1 pacote de trabalho (ver
`management.py`, `project_send_status`, e a marca oculta em `generator.py`/
`email_ingest.py` que carrega o `pacote_scope` de cada amostra)."""
from __future__ import annotations

import json
from datetime import date

import pytest

from backend.app import management


def _write_samples(data_file, samples, closed_clients=None, closed_projects=None):
    data_file.write_text(
        json.dumps({
            "manual_entries": {},
            "project_kpi_samples": samples,
            "processed_message_ids": [],
            "skipped_messages": [],
            "closed_clients": closed_clients or [],
            "closed_projects": closed_projects or [],
        }),
        encoding="utf-8",
    )


def _sample(project_id, month, pacote_scope, billed_hours=1.0, msg_id="m1", source="email", sample_id=None, business_days=1):
    # aceita tanto uma string única (a maioria dos testes, mais legível) quanto
    # já uma lista/None — `pacote_scope` internamente é sempre list|None
    # (ver management._load_data, migração retroativa do formato antigo).
    scope = [pacote_scope] if isinstance(pacote_scope, str) else pacote_scope
    sample = {
        "email_message_id": msg_id,
        "received_at": "2026-09-01T00:00:00Z",
        "sender": "diego.herrera@schwaben.com.br",
        "report_project_text": f"Projeto {project_id}",
        "project_id": project_id,
        "project_name": f"Projeto {project_id}",
        "match_score": 1.0,
        "month": month,
        "billed_hours": billed_hours,
        "business_days": business_days,
        "pacote_scope": scope,
        "source": source,
    }
    if sample_id:
        sample["sample_id"] = sample_id
    return sample


def _row(project_id, pacote, hours, day=1, person=None):
    return {
        "data": date(2026, 8, day),
        "horas": hours,
        "pacote": pacote,
        "project_id": project_id,
        "cost_center": "CAD",
        "external": "1",
        "person": person,
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


def test_selected_months_recorta_available_mas_nao_os_buckets(monkeypatch, tmp_path):
    """`selected_months` (Competência no Painel de Gerência) só recorta as
    opções de filtro (available_projects/available_packages/project_codes)
    — os buckets de horas por mês (usados nos KPIs/gráfico) continuam com
    TODOS os meses, porque essa parte já é recortada depois, no frontend
    (ver `ManagementPanel.tsx` `displayRows`)."""
    data_file = tmp_path / "management_kpi.json"
    row_agosto = _row("P1", "Pacote A", 10.0, day=15)
    row_julho = {**_row("P2", "Pacote B", 5.0, day=15), "data": date(2026, 7, 15)}
    _patch_projectile(monkeypatch, [row_agosto, row_julho])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    result = management.compute_monthly_kpis(months=1, year=2026, selected_months=["2026-08"], force_refresh=True)

    assert result["available_packages"] == ["Pacote A"]
    assert result["available_projects"] == ["Projeto P1"]

    months_by_key = {m["month"]: m for m in result["months"]}
    assert months_by_key["2026-08"]["worked_hours"] == 10.0
    assert months_by_key["2026-07"]["worked_hours"] == 5.0


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


def test_one_sample_covering_multiple_pacotes_at_once_is_sent(monkeypatch, tmp_path):
    """Edição manual do Diagnóstico permite marcar VÁRIOS pacotes numa única
    amostra (ex: um relatório que na real cobriu 2 pacotes de trabalho) —
    não precisa de 2 amostras separadas pra fechar "enviado"."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0), _row("P1", "Pacote B", 5.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(
        data_file,
        [_sample("P1", "2026-08", pacote_scope=["Pacote A", "Pacote B"], billed_hours=15.0)],
    )

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "sent"
    assert row["missing_pacotes"] == []


def test_legacy_string_pacote_scope_migrates_to_list(tmp_path, monkeypatch):
    """Amostras gravadas antes da edição multi-pacote existir têm
    `pacote_scope` como texto único — `_load_data` precisa migrar isso pra
    lista de 1 item na primeira leitura, senão todo o resto do código (que
    já assume list|None) quebra com dado antigo."""
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope=None, msg_id="m1")])
    # sobrescreve pra simular o formato ANTIGO (string), sem passar por
    # `_sample`/`_write_samples` (que já produzem o formato novo).
    raw = json.loads(data_file.read_text(encoding="utf-8"))
    raw["project_kpi_samples"][0]["pacote_scope"] = "Pacote Antigo"
    data_file.write_text(json.dumps(raw), encoding="utf-8")

    samples = management.list_samples()["samples"]

    assert samples[0]["pacote_scope"] == ["Pacote Antigo"]


def test_update_project_kpi_sample_can_set_pacote_scope(tmp_path, monkeypatch):
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope=None, msg_id="m1")])
    sample_id = management.list_samples()["samples"][0]["sample_id"]

    ok = management.update_project_kpi_sample(sample_id, {"pacote_scope": ["Pacote A", "Pacote B"]})

    assert ok
    updated = management.list_samples()["samples"][0]
    assert updated["pacote_scope"] == ["Pacote A", "Pacote B"]


def test_list_pacotes_for_project_filters_by_project(monkeypatch):
    """O recorte por mês é feito pela query SQL (`fetch_engineering_hours(
    start, end)`), não em Python — aqui só se testa o filtro por projeto,
    já que o mock de `fetch_engineering_hours` (ver `_patch_projectile`)
    ignora o intervalo de datas recebido, igual ao resto dos testes deste
    arquivo."""
    _patch_projectile(monkeypatch, [
        _row("P1", "Pacote A", 10.0),
        _row("P1", "Pacote B", 5.0),
        _row("P2", "Pacote C", 3.0),
    ])

    pacotes = management.list_pacotes_for_project("P1", "2026-08", force_refresh=True)

    assert pacotes == ["Pacote A", "Pacote B"]


def test_list_pacotes_for_project_month_none_ignores_month_filter(monkeypatch):
    """Popup de "Fechados": fechar é permanente, o gerente precisa ver
    pacotes de QUALQUER mês, não só do que estiver selecionado no painel —
    `month=None` usa um intervalo bem amplo (_ALL_TIME_START) em vez do mês
    específico. Mock de fetch_engineering_hours já ignora o intervalo
    recebido (mesma ressalva do teste acima), então isso só prova que a
    chamada não quebra e ainda filtra por projeto certo."""
    _patch_projectile(monkeypatch, [
        _row("P1", "Pacote Antigo", 1.0, day=1),
        _row("P1", "Pacote Novo", 2.0, day=15),
        _row("P2", "Pacote Outro Projeto", 3.0),
    ])

    pacotes = management.list_pacotes_for_project("P1", None, force_refresh=True)

    assert pacotes == ["Pacote Antigo", "Pacote Novo"]


def test_closed_project_status_overrides_none(monkeypatch, tmp_path):
    """Projeto fechado nunca aparece como "Não enviado" — mesmo com horas
    reais e nenhuma amostra, o status vira "closed"."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [], closed_projects=["P1"])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "closed"
    assert row["missing_pacotes"] == []


def test_closed_client_cascades_to_all_its_projects(monkeypatch, tmp_path):
    """Fechar um CLIENTE fecha todos os projetos dele, sem precisar listar
    cada project_id em closed_projects."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0), _row("P2", "Pacote B", 5.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [], closed_clients=["Cliente Teste"])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)

    assert _find_status(result, "P1")["status"] == "closed"
    assert _find_status(result, "P2")["status"] == "closed"


def test_closed_client_matches_empty_client_via_sem_cliente_fallback(monkeypatch, tmp_path):
    """`fetch_project_details` pode devolver client="" (Projectile sem
    cliente cadastrado) — compute_monthly_kpis normaliza isso pra "Sem
    cliente" tanto no campo "client" da linha quanto na comparação contra
    closed_clients, então fechar "Sem cliente" fecha esses projetos."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0)])
    monkeypatch.setattr(management, "fetch_project_details", lambda ids, conn=None: {pid: {"name": f"Projeto {pid}", "client": ""} for pid in ids})
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [], closed_clients=["Sem cliente"])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["client"] == "Sem cliente"
    assert row["status"] == "closed"


def test_closed_overrides_even_a_genuinely_sent_month(monkeypatch, tmp_path):
    """Fechar sobrepõe QUALQUER resultado automático, inclusive um "sent"
    de verdade — decisão confirmada com o usuário (100% reversível, não
    mexe em nenhuma amostra)."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope=None, billed_hours=10.0)], closed_projects=["P1"])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "closed"


def test_manual_send_marker_created_and_detected(monkeypatch, tmp_path):
    """Amostra manual 0h/0dias (checkbox "Enviado" clicado numa linha
    "none"/"partial") é detectada como manual_send_marker_id, e como não há
    nenhuma outra evidência, é removível."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [
        _sample("P1", "2026-08", pacote_scope=None, billed_hours=0, business_days=0, msg_id="manual-1", source="manual", sample_id="marker-1"),
    ])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "sent"
    assert row["manual_send_marker_id"] == "marker-1"
    assert row["manual_send_marker_removable"] is True


def test_manual_send_marker_not_removable_when_real_evidence_covers_row(monkeypatch, tmp_path):
    """Se apagar o marcador AINDA deixaria a linha "sent" por evidência de
    e-mail real, ele não é removível (não faz sentido "desmarcar" algo que
    já está genuinamente enviado)."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [
        _sample("P1", "2026-08", pacote_scope=None, billed_hours=10.0, msg_id="m1", source="email"),
        _sample("P1", "2026-08", pacote_scope=None, billed_hours=0, business_days=0, msg_id="manual-1", source="manual", sample_id="marker-1"),
    ])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "sent"
    assert row["manual_send_marker_id"] == "marker-1"
    assert row["manual_send_marker_removable"] is False


def test_deleting_manual_send_marker_reverts_partial_status(monkeypatch, tmp_path):
    """Apagar o marcador manual (via delete_project_kpi_sample, mesmo
    endpoint que o botão "desmarcar" chama) reverte a linha pro status real
    calculado a partir das amostras que sobraram."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0), _row("P1", "Pacote B", 5.0)])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [
        _sample("P1", "2026-08", pacote_scope=["Pacote A"], billed_hours=10.0, msg_id="m1", source="email"),
        _sample("P1", "2026-08", pacote_scope=None, billed_hours=0, business_days=0, msg_id="manual-1", source="manual", sample_id="marker-1"),
    ])

    management.delete_project_kpi_sample("marker-1")
    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    row = _find_status(result, "P1")

    assert row["status"] == "partial"
    assert row["missing_pacotes"] == ["Pacote B"]
    assert row["manual_send_marker_id"] is None


def test_set_client_closed_and_reopen_round_trip(tmp_path, monkeypatch):
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    management.set_client_closed("Cliente A", True)
    assert management.get_closed_registry()["closed_clients"] == ["Cliente A"]

    management.set_client_closed("Cliente A", True)  # idempotente
    assert management.get_closed_registry()["closed_clients"] == ["Cliente A"]

    management.set_client_closed("Cliente A", False)
    assert management.get_closed_registry()["closed_clients"] == []


def test_set_project_closed_and_reopen_round_trip(tmp_path, monkeypatch):
    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    management.set_project_closed("P1", True)
    assert management.get_closed_registry()["closed_projects"] == ["P1"]

    management.set_project_closed("P1", False)
    assert management.get_closed_registry()["closed_projects"] == []


def test_load_data_migrates_closed_keys_for_old_json_files(tmp_path, monkeypatch):
    """Arquivo management_kpi.json de antes dessa funcionalidade existir não
    tem closed_clients/closed_projects — _load_data precisa preencher com
    listas vazias sem quebrar nada."""
    data_file = tmp_path / "management_kpi.json"
    data_file.write_text(
        json.dumps({
            "manual_entries": {},
            "project_kpi_samples": [],
            "processed_message_ids": [],
            "skipped_messages": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))

    assert management.get_closed_registry() == {"closed_clients": [], "closed_projects": []}


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


# ---------------------------------------------------------------------------
# persons — filtro por pessoa (só afeta worked_hours/nonbillable_hours, que
# vêm do Projectile; billed_hours/perf_hours/perf_kpi_pct/elaboration_days
# não têm dimensão de pessoa — ver docstring de _build_month_row).
# ---------------------------------------------------------------------------

def test_persons_filter_scopes_worked_hours(monkeypatch, tmp_path):
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [
        _row("P1", "Pacote A", 10.0, person="Ana"),
        _row("P1", "Pacote A", 4.0, person="Beto"),
    ])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    result = management.compute_monthly_kpis(months=1, year=2026, persons=["Ana"], force_refresh=True)

    months_by_key = {m["month"]: m for m in result["months"]}
    assert months_by_key["2026-08"]["worked_hours"] == 10.0


def test_persons_filter_nulls_billed_and_performance(monkeypatch, tmp_path):
    """Faturado/Performance vêm de e-mail/manual, por PROJETO — não têm como
    saber quanto disso é de UMA pessoa, então saem None em vez de comparar o
    trabalhado de uma pessoa com o faturado do time inteiro (decisão
    confirmada com o usuário)."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0, person="Ana")])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope=None, billed_hours=12.0)])

    without_filter = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)
    with_filter = management.compute_monthly_kpis(months=1, year=2026, persons=["Ana"], force_refresh=True)

    row_without = {m["month"]: m for m in without_filter["months"]}["2026-08"]
    row_with = {m["month"]: m for m in with_filter["months"]}["2026-08"]
    assert row_without["billed_hours"] == 12.0
    assert row_without["perf_hours"] is not None
    assert row_with["billed_hours"] is None
    assert row_with["perf_hours"] is None
    assert row_with["perf_kpi_pct"] is None
    # worked_hours continua calculado normalmente, só billed/perf somem
    assert row_with["worked_hours"] == 10.0


def test_persons_filter_does_not_affect_nonbillable(monkeypatch, tmp_path):
    """nonbillable_hours/nonbillable_kpi_pct são só de horas trabalhadas
    (tjob.pExternal='0') — não misturam com faturado, então continuam
    normalmente com o filtro de pessoa ativo."""
    data_file = tmp_path / "management_kpi.json"
    row = {**_row("P1", "Pacote A", 10.0, person="Ana"), "external": "0"}
    _patch_projectile(monkeypatch, [row])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    result = management.compute_monthly_kpis(months=1, year=2026, persons=["Ana"], force_refresh=True)

    row_result = {m["month"]: m for m in result["months"]}["2026-08"]
    assert row_result["nonbillable_hours"] == 10.0
    assert row_result["nonbillable_kpi_pct"] == 1.0


def test_available_persons_ignores_own_filter(monkeypatch, tmp_path):
    """`available_persons` reflete todo mundo que apontou no recorte de
    Centro de Custo/Cliente/Projeto/Pacote — não esvazia pras outras opções
    quando uma pessoa já está selecionada (mesmo padrão de available_packages)."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [
        _row("P1", "Pacote A", 10.0, person="Ana"),
        _row("P1", "Pacote A", 4.0, person="Beto"),
    ])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    result = management.compute_monthly_kpis(months=1, year=2026, persons=["Ana"], force_refresh=True)

    assert result["available_persons"] == ["Ana", "Beto"]


def test_no_persons_filter_behaves_exactly_like_before(monkeypatch, tmp_path):
    """Regressão: sem `persons` (None, o padrão), billed_hours/perf_hours
    continuam calculados normalmente — a feature não muda nada pra quem não
    usa o filtro."""
    data_file = tmp_path / "management_kpi.json"
    _patch_projectile(monkeypatch, [_row("P1", "Pacote A", 10.0, person="Ana")])
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [_sample("P1", "2026-08", pacote_scope=None, billed_hours=12.0)])

    result = management.compute_monthly_kpis(months=1, year=2026, force_refresh=True)

    row = {m["month"]: m for m in result["months"]}["2026-08"]
    assert row["billed_hours"] == 12.0
    assert row["perf_hours"] == pytest.approx(2.0)


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


# ---------------------------------------------------------------------------
# _load_management_panel_logins — normalização de caixa (ver main.py, que
# compara com .lower() do lado do login também; auser.rLogin no Projectile
# não tem capitalização padronizada, ex: "Lbrito" em vez de "lbrito")
# ---------------------------------------------------------------------------

def test_load_management_panel_logins_normalizes_to_lowercase(monkeypatch):
    monkeypatch.setenv("MANAGEMENT_PANEL_LOGINS", "Dherrera, LFranco, lvicente")

    logins = management._load_management_panel_logins()

    assert logins == {"dherrera", "lfranco", "lvicente"}


def test_load_management_panel_logins_strips_whitespace_and_drops_empty(monkeypatch):
    monkeypatch.setenv("MANAGEMENT_PANEL_LOGINS", " dherrera ,, lfranco,")

    logins = management._load_management_panel_logins()

    assert logins == {"dherrera", "lfranco"}


def test_load_management_panel_logins_falls_back_when_env_missing(monkeypatch):
    monkeypatch.delenv("MANAGEMENT_PANEL_LOGINS", raising=False)

    logins = management._load_management_panel_logins()

    assert logins == {"dherrera"}


def test_load_translate_allowed_logins_normalizes_to_lowercase(monkeypatch):
    monkeypatch.setenv("TRANSLATE_ALLOWED_LOGINS", "Dherrera, LFranco")

    logins = management._load_translate_allowed_logins()

    assert logins == {"dherrera", "lfranco"}


def test_load_translate_allowed_logins_falls_back_when_env_missing(monkeypatch):
    monkeypatch.delenv("TRANSLATE_ALLOWED_LOGINS", raising=False)

    logins = management._load_translate_allowed_logins()

    assert logins == {"dherrera"}


# ---------------------------------------------------------------------------
# Escrita concorrente em management_kpi.json — bug real relatado: um relatório
# manual adicionado pelo Diagnóstico "sumiu" depois de reiniciar o backend.
# Causa: _load_data()/_save_data() fazem leitura-modificação-escrita sem
# nenhum lock, e o loop de polling de e-mail (_poll_emails_loop, rodando em
# thread separada via asyncio.to_thread) chama funções que fazem o mesmo
# ciclo — se o polling carrega o arquivo, demora (chamada de rede real) e só
# depois salva, ele sobrescreve com um snapshot antigo qualquer escrita feita
# nesse meio-tempo (ex: o usuário adicionando uma amostra manual).
# ---------------------------------------------------------------------------

def test_concurrent_writes_do_not_lose_data(tmp_path, monkeypatch):
    """Duas escritas concorrentes — uma "lenta" (simulando o polling de
    e-mail, que carrega o arquivo, demora numa chamada de rede real e só
    depois salva) e uma "rápida" (simulando o usuário adicionando uma
    amostra manual pelo Diagnóstico) — não podem se perder uma à outra.

    Antes de `_DATA_LOCK` existir, isso reproduzia o bug relatado (um
    relatório manual "sumindo" depois de reiniciar o backend, porque o
    polling de e-mail salvava por cima com um snapshot carregado ANTES da
    escrita manual): a operação lenta ficava livre pra carregar um snapshot
    desatualizado enquanto a rápida escrevia por baixo dela, e ao salvar de
    volta apagava essa escrita. Com o lock, a rápida fica bloqueada até a
    lenta soltar o lock — mais lento, mas nunca perde dado."""
    import threading

    data_file = tmp_path / "management_kpi.json"
    monkeypatch.setattr(management, "_DATA_FILE", str(data_file))
    _write_samples(data_file, [])

    slow_holds_lock = threading.Event()
    fast_may_proceed = threading.Event()
    original_load_data = management._load_data

    def slow_first_load():
        data = original_load_data()
        # simula a demora real de uma chamada de rede (Graph) no meio do
        # ciclo de polling, com o lock já em mãos (ver set_manual_entry).
        slow_holds_lock.set()
        fast_may_proceed.wait(timeout=2)
        return data

    monkeypatch.setattr(management, "_load_data", slow_first_load)

    slow_thread = threading.Thread(target=lambda: management.set_manual_entry("2026-08", 100.0, 5.0))
    fast_thread = threading.Thread(
        target=lambda: management.append_project_kpi_sample(
            {
                "email_message_id": "manual-x", "received_at": "2026-09-10T12:00:00Z",
                "sender": "manual", "report_project_text": "Projeto X", "project_id": "P1",
                "project_name": "Projeto X", "match_score": 1.0, "month": "2026-08",
                "billed_hours": 10.0, "business_days": 1, "source": "manual",
                "edited": False, "pacote_scope": None, "sample_id": "s1",
            }
        )
    )

    slow_thread.start()
    assert slow_holds_lock.wait(timeout=2), "operação lenta não chegou a segurar o lock a tempo"
    fast_thread.start()  # fica bloqueada esperando o lock (comportamento esperado)
    fast_may_proceed.set()  # libera a lenta pra terminar e soltar o lock
    slow_thread.join(timeout=2)
    fast_thread.join(timeout=2)

    final = original_load_data()
    assert final["manual_entries"].get("2026-08") == {"billed_hours": 100.0, "elaboration_days": 5.0}
    assert len(final["project_kpi_samples"]) == 1
    assert final["project_kpi_samples"][0]["sample_id"] == "s1"
