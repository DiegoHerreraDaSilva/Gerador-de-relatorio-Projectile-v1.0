"""Papel de coordenador: acessa Gerar relatório (inclusive busca por
cliente/projeto), Dashboard de horas, o próprio Histórico e o Diagnóstico —
nunca o Painel de Gerência, o Analytics nem os KPIs (`/management/kpis`),
nem pela API."""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.app import auth
from backend.app.api.dependencies import require_manager, require_manager_or_coordinator, require_session, require_translate_access
from backend.app.api.routers import management as management_router
from backend.app.core import authz
from backend.app.main import app

_MANAGER = {"name": "Gerente", "login": "gerente", "email": "g@x"}
_COORDINATOR = {"name": "Coordenador", "login": "coord", "email": "c@x"}
_COLLABORATOR = {"name": "Colaborador", "login": "colab", "email": "o@x"}

_MANAGER_ONLY = {
    ("GET", "/health/details"),
    ("GET", "/reports/ids"),
    ("DELETE", "/reports"),
    ("POST", "/reports/restore"),
    ("DELETE", "/reports/trash"),
    ("GET", "/management/kpis"),
    ("GET", "/management/executive-summary"),
    ("POST", "/management/kpis/check-emails"),
    ("PUT", "/management/kpis/{month}"),
    ("GET", "/analytics/summary"),
    ("GET", "/analytics/health"),
    ("POST", "/analytics/chat"),
    ("POST", "/analytics/chat/export"),
    # geração automática — a aba inteira é só do gerente
    ("GET", "/auto-generation/config"),
    ("PUT", "/auto-generation/config"),
    ("PUT", "/auto-generation/rules/{family_key}"),
    ("DELETE", "/auto-generation/rules/{family_key}"),
    ("PUT", "/auto-generation/families/{project_id}"),
    ("GET", "/auto-generation/competences"),
    ("GET", "/auto-generation/competences/{competence}"),
    ("GET", "/auto-generation/competences/{competence}/preview"),
    ("POST", "/auto-generation/competences/{competence}/run"),
    ("GET", "/auto-generation/reports/{report_id}"),
    ("PUT", "/auto-generation/reports/{report_id}/draft"),
    ("PATCH", "/auto-generation/reports/{report_id}/numbers"),
    ("POST", "/auto-generation/reports/{report_id}/approve"),
    ("POST", "/auto-generation/reports/{report_id}/skip"),
    ("POST", "/auto-generation/reports/{report_id}/reopen"),
    ("POST", "/auto-generation/reports/{report_id}/regenerate"),
    ("GET", "/auto-generation/reports/{report_id}/files"),
    ("GET", "/auto-generation/reviewers"),
    ("PUT", "/auto-generation/reports/{report_id}/reviewer"),
    ("POST", "/auto-generation/reports/{report_id}/return"),
    ("GET", "/auto-generation/reports/{report_id}/send"),
    ("POST", "/auto-generation/reports/{report_id}/send"),
    ("POST", "/auto-generation/reports/{report_id}/send/resolve"),
    ("GET", "/auto-generation/files"),
    ("POST", "/auto-generation/send"),
    ("PUT", "/auto-generation/competences/{competence}/numbers/{project_id}"),
    ("GET", "/auto-generation/custom"),
    ("POST", "/auto-generation/custom/preview"),
    ("POST", "/auto-generation/custom"),
    ("DELETE", "/auto-generation/custom/{report_id}"),
    ("DELETE", "/auto-generation/custom/requests/{request_id}"),
    ("PUT", "/auto-generation/custom/requests/{request_id}/config"),
    ("PUT", "/auto-generation/custom/{report_id}/config"),
}


@pytest.fixture(autouse=True)
def _roles(monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    monkeypatch.setattr(authz, "COORDINATOR_LOGINS", {"coord"})
    yield
    app.dependency_overrides.pop(require_session, None)


def _client_as(user: dict) -> TestClient:
    app.dependency_overrides[require_session] = lambda: user
    return TestClient(app)


_ACCESS_CLASSES = {
    require_session: "session",
    require_manager: "manager",
    require_manager_or_coordinator: "manager_or_coordinator",
    require_translate_access: "translate",
}

# rotas sem NENHUMA dependência de acesso: login; me/logout tratam a sessão
# por dentro; /health é do monitor externo (sem login de propósito)
_PUBLIC = {("POST", "/auth/login"), ("GET", "/auth/me"), ("POST", "/auth/logout"), ("GET", "/health")}

# allowlist que gasta Anthropic por clique (não é papel, é permissão à parte)
_TRANSLATE = {("POST", "/translate-activities")}


def _access_class(route) -> str:
    calls = {dep.call for dep in route.dependant.dependencies}
    for candidate, label in _ACCESS_CLASSES.items():
        if candidate in calls:
            return label
    return "public"


def _expected_class(method: str, path: str) -> str:
    if (method, path) in _MANAGER_ONLY:
        return "manager"
    if (method, path) in _PUBLIC:
        return "public"
    if (method, path) in _TRANSLATE:
        return "translate"
    if path.startswith("/management/") or path in ("/parse-db-client", "/my-hours/employees", "/my-hours/team"):
        return "manager_or_coordinator"
    return "session"


def _all_api_routes() -> list[APIRoute]:
    """FastAPI 0.141 guarda cada `include_router` num wrapper
    `_IncludedRouter` (sem `.routes`); as rotas de verdade ficam em
    `original_router`. Achata os dois formatos numa lista só."""
    routes: list[APIRoute] = []
    for route in app.routes:
        original = getattr(route, "original_router", None)
        for candidate in original.routes if original is not None else [route]:
            if isinstance(candidate, APIRoute):
                routes.append(candidate)
    return routes


def test_matriz_de_autorizacao_de_toda_rota():
    """TODA rota do app tem que bater com a classificação declarada:
    `session` (padrão), `manager` (lista `_MANAGER_ONLY`), ou as exceções
    explícitas `manager_or_coordinator`, `translate` e `public`. Rota nova de
    gerência/coordenação/tradução/pública sem a classificação certa falha com
    o nome; rota `session` nova passa (é o padrão) — mas qualquer dependência
    de acesso diferente vira erro, nunca silêncio."""
    routes = _all_api_routes()
    assert routes
    for route in routes:
        for method in route.methods:
            expected = _expected_class(method, route.path)
            actual = _access_class(route)
            assert actual == expected, f"{method} {route.path}: esperado {expected}, veio {actual}"


@pytest.mark.parametrize("path", ["/management/kpis", "/analytics/summary"])
def test_coordenador_nao_ve_kpis_nem_analytics(path):
    response = _client_as(_COORDINATOR).get(path)
    assert response.status_code == 403


def test_colaborador_nao_acessa_o_diagnostico():
    response = _client_as(_COLLABORATOR).get("/management/send-status")
    assert response.status_code == 403


def test_send_status_nao_devolve_numero_de_kpi(monkeypatch):
    """O Diagnóstico do coordenador usa esta rota em vez de /management/kpis
    — nada de horas, faturamento ou performance pode sair por ela."""
    full_result = {
        "months": [{"month": "2026-08", "worked_hours": 100.0, "billed_hours": 90.0, "perf_kpi_pct": -0.1, "nonbillable_hours": 5.0, "elaboration_days": 3.0}],
        "nonbillable_breakdown": [{"month": "2026-08", "package": "Treinamento", "hours": 5.0}],
        "cost_centers": ["CAD", "CAE"],
        "project_send_status": [{"month": "2026-08", "project_id": "P1", "status": "sent"}],
        "available_projects": ["Projeto 1"],
        "available_clients": ["Cliente"],
        "available_packages": ["Pacote"],
        "available_persons": ["Fulano"],
        "project_codes": {"Projeto 1": "1564"},
        "project_clients": {"Projeto 1": "Cliente"},
    }
    monkeypatch.setattr(management_router, "compute_monthly_kpis", lambda *a, **k: full_result)

    response = _client_as(_COORDINATOR).get("/management/send-status")

    assert response.status_code == 200
    body = response.json()
    assert body["months"] == [{"month": "2026-08"}]
    assert "nonbillable_breakdown" not in body
    assert "cost_centers" not in body
    assert body["project_send_status"] == full_result["project_send_status"]
    assert body["available_persons"] == ["Fulano"]


def test_gerente_continua_com_acesso_aos_kpis(monkeypatch):
    monkeypatch.setattr(management_router, "compute_monthly_kpis", lambda *a, **k: {"months": []})
    assert _client_as(_MANAGER).get("/management/kpis").status_code == 200


@pytest.mark.parametrize(("user", "expected"), [(_MANAGER, (True, False)), (_COORDINATOR, (False, True)), (_COLLABORATOR, (False, False))])
def test_auth_me_informa_o_papel(user, expected):
    token = auth.create_session(user)
    try:
        response = TestClient(app).get("/auth/me", cookies={"session_token": token})
    finally:
        auth.delete_session(token)
    assert response.status_code == 200
    assert (response.json()["is_manager"], response.json()["is_coordinator"]) == expected


def test_coordinator_logins_sem_fallback(monkeypatch):
    """Ao contrário das outras allowlists, não há fallback: env vazia não
    pode dar acesso a ninguém por engano (o authz chama `parse_logins` com
    fallback vazio pro coordenador)."""
    assert authz.parse_logins("", set()) == set()
    assert authz.parse_logins(" Coord , outro ,", set()) == {"coord", "outro"}


def _fake_kpis(monkeypatch):
    calls = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return {"months": [], **{key: [] for key in management_router._SEND_STATUS_KEYS}}

    monkeypatch.setattr(management_router, "compute_monthly_kpis", fake)
    return calls


def test_coordenador_ve_os_ultimos_12_meses_e_o_ano_atual(monkeypatch):
    from datetime import date

    calls = _fake_kpis(monkeypatch)
    client = _client_as(_COORDINATOR)
    assert client.get("/management/send-status").status_code == 200
    assert client.get("/management/send-status", params={"year": date.today().year}).status_code == 200
    assert len(calls) == 2


@pytest.mark.parametrize(
    "params",
    [
        {"year": 2019},
        {"year": "LAST"},  # o ano passado saiu (decisão de 2026-09-28)
        {"months": 36},
    ],
)
def test_coordenador_nao_ve_outros_periodos(monkeypatch, params):
    from datetime import date

    if params.get("year") == "LAST":
        params = {"year": date.today().year - 1}
    calls = _fake_kpis(monkeypatch)
    response = _client_as(_COORDINATOR).get("/management/send-status", params=params)
    assert response.status_code == 403
    assert calls == []


def test_gerente_ve_qualquer_periodo_no_diagnostico(monkeypatch):
    calls = _fake_kpis(monkeypatch)
    client = _client_as(_MANAGER)
    assert client.get("/management/send-status", params={"year": 2019}).status_code == 200
    assert client.get("/management/send-status", params={"months": 36}).status_code == 200
    assert len(calls) == 2


def test_amostras_do_coordenador_ficam_na_janela_permitida(monkeypatch):
    from datetime import date

    from backend.app.api import period_access

    today = date.today()
    recent = today.strftime("%Y-%m")
    edge = period_access.allowed_months()[0]  # 11 meses atrás: ainda vale
    before = f"{int(edge[:4]) - (edge[5:] == '01')}-{12 if edge[5:] == '01' else int(edge[5:]) - 1:02d}"
    old = f"{today.year - 3}-05"
    document = {
        "samples": [{"month": m, "sample_id": m} for m in (recent, edge, before, old)],
        "skipped_messages": [{"received_at": f"{m}-10T09:00:00"} for m in (recent, old)],
    }
    monkeypatch.setattr(management_router, "list_samples", lambda month=None: document)

    body = _client_as(_COORDINATOR).get("/management/kpis/samples").json()
    assert [s["month"] for s in body["samples"]] == [recent, edge]
    assert [s["received_at"][:7] for s in body["skipped_messages"]] == [recent]

    body = _client_as(_MANAGER).get("/management/kpis/samples").json()
    assert len(body["samples"]) == 4
    assert len(body["skipped_messages"]) == 2
