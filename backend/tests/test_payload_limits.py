"""Tetos de entrada do payload de geração (`report_files`): barram payload
absurdo com 422 previsível sem recusar relatório real. Valem pra /generate,
/send-report e pra aprovação da geração automática (mesmos modelos)."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from backend.app.services import report_files as rf

PNG = base64.b64encode(bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"0" * 1000).decode()


def _header(**over):
    base = {"project_code": "SE.01.001", "project_name": "P", "location_date": "x", "month_label": "Agosto/2026", "signer1_name": "A", "signer2_name": "B"}
    return {**base, **over}


def _pkg(groups=None, **over):
    return {
        "header": _header(),
        "groups": groups if groups is not None else [{"name": "G", "performance": 1, "activities": [{"description": "a", "hours": 1}]}],
        **over,
    }


def test_real_sized_report_is_accepted():
    groups = [{"name": f"G{i}", "performance": 1, "activities": [{"description": "x" * 300, "hours": 1} for _ in range(200)]} for i in range(20)]
    rf.GeneratePayload(packages=[_pkg(groups, chart_image_bar=PNG, chart_image_pie=PNG)])


@pytest.mark.parametrize(
    "payload",
    [
        {"packages": [_pkg()] * (rf.MAX_PACKAGES + 1)},
        {"packages": [_pkg(groups=[{"name": "G", "performance": 1, "activities": []}] * (rf.MAX_GROUPS + 1))]},
        {"packages": [_pkg(groups=[{"name": "G", "performance": 1, "activities": [{"description": "a"}] * (rf.MAX_ACTIVITIES_PER_GROUP + 1)}])]},
        {"packages": [_pkg(groups=[{"name": "G", "performance": 1, "activities": [{"description": "x" * (rf.MAX_DESCRIPTION + 1)}]}])]},
        {"packages": [{**_pkg(), "header": _header(project_name="x" * (rf.MAX_HEADER_TEXT + 1))}]},
        {"packages": [_pkg(chart_image_bar="not base64!!")]},
        {"packages": [_pkg(chart_image_bar=base64.b64encode(b"GIF89a....").decode())]},
        {"packages": [_pkg(chart_image_bar="A" * (rf.MAX_CHART_B64 + 4))]},
    ],
)
def test_absurd_payload_is_rejected(payload):
    with pytest.raises(ValidationError):
        rf.GeneratePayload(**payload)


def test_total_activities_cap_spans_packages():
    groups = [{"name": "G", "performance": 1, "activities": [{"description": "a"}] * rf.MAX_ACTIVITIES_PER_GROUP}] * 5
    with pytest.raises(ValidationError):
        rf.GeneratePayload(packages=[_pkg(groups)] * 3)  # 3 × 5 × 2000 = 30 000 > 20 000
