"""`canonical_json`/`compute_data_hash` (backend/app/services/snapshot.py) —
puramente funcionais, sem banco."""
from __future__ import annotations

from backend.app.services.snapshot import build_snapshot_data, canonical_json, compute_data_hash


def _pkg_data(hours=8.0, group_name="Grupo A"):
    return {
        "header": {
            "project_code": "SE.01.002",
            "project_name": "Projeto Teste",
            "location_date": "São Paulo, 01/01/2026",
            "month_label": "Julho/2026",
            "signer1_name": "Alberto Moura",
            "signer1_company": "Schwaben Engineering",
            "signer2_name": "Wagner Augusto Duarte",
            "signer2_company": "Mercedes-Benz do Brasil",
        },
        "groups": [
            {"name": group_name, "performance": 100.0, "activities": [{"description": "Atividade 1", "hours": hours}]}
        ],
        "pacote_scope": None,
        "language": "pt",
        "has_chart_bar": False,
        "has_chart_pie": False,
    }


def test_canonical_json_ignora_ordem_de_chaves():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b


def test_canonical_json_determinístico_em_espaçamento():
    assert canonical_json({"a": [1, 2, 3]}) == '{"a":[1,2,3]}'


def test_compute_data_hash_muda_se_horas_muda():
    snapshot_a = build_snapshot_data(_pkg_data(hours=8.0))
    snapshot_b = build_snapshot_data(_pkg_data(hours=8.5))
    assert compute_data_hash(snapshot_a) != compute_data_hash(snapshot_b)


def test_compute_data_hash_estavel_pro_mesmo_conteudo():
    snapshot_a = build_snapshot_data(_pkg_data())
    snapshot_b = build_snapshot_data(_pkg_data())
    assert compute_data_hash(snapshot_a) == compute_data_hash(snapshot_b)


def test_compute_data_hash_muda_se_ordem_dos_grupos_muda():
    """A ordem é dado real (vira `position` em report_groups/report_activities
    — ver report_persistence._insert_groups_and_activities), então trocar a
    ordem dos grupos PRECISA mudar o hash, mesmo com o mesmo conteúdo."""
    pkg = _pkg_data()
    pkg["groups"] = [
        {"name": "Grupo A", "performance": 100.0, "activities": [{"description": "X", "hours": 1.0}]},
        {"name": "Grupo B", "performance": 100.0, "activities": [{"description": "Y", "hours": 2.0}]},
    ]
    pkg_reordered = dict(pkg, groups=list(reversed(pkg["groups"])))

    hash_original = compute_data_hash(build_snapshot_data(pkg))
    hash_reordenado = compute_data_hash(build_snapshot_data(pkg_reordered))
    assert hash_original != hash_reordenado


def test_build_snapshot_data_exclui_bytes_de_grafico():
    """`chart_image_bar`/`chart_image_pie` nunca entram no snapshot — só as
    flags booleanas `has_chart_bar`/`has_chart_pie` (ver docstring do
    módulo)."""
    pkg = _pkg_data()
    pkg["chart_image_bar"] = "base64dataqueNUNCAdeveriaEntrarNoSnapshot..."
    snapshot = build_snapshot_data(pkg)
    assert "chart_image_bar" not in snapshot
    assert "base64data" not in canonical_json(snapshot)
