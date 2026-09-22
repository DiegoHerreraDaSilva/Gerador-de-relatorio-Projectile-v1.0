"""Integração de POST /chat com o novo contrato de `id` estável em grupo/
atividade (Fase 8). Mocka `chatbot.call_chat` (mesmo padrão de
test_chatbot.py) — aqui importa o contrato do endpoint, não a chamada real
à Anthropic."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import main as main_module
from backend.app.main import app, require_session


def _fake_user() -> dict:
    return {"name": "Diego Herrera", "login": "dherrera", "email": "diego.herrera@schwaben.com.br"}


def _client(monkeypatch) -> TestClient:
    app.dependency_overrides[require_session] = _fake_user
    return TestClient(app)


def _chat_state_payload() -> dict:
    return {
        "packages": [
            {
                "key": "pkg-1",
                "projectCode": "SE.01.002",
                "projectName": "Projeto Teste",
                "groups": [
                    {
                        "id": "g1",
                        "name": "Grupo A",
                        "performance": 100.0,
                        "activities": [{"id": "a1", "description": "Atividade 1", "hours": 8.0}],
                    }
                ],
            }
        ],
        "activePackageIndex": 0,
        "locationDate": "São Paulo, 01/01/2026",
        "monthLabel": "Julho/2026",
        "signer1Name": "Fulano",
        "signer1Company": "Schwaben Engineering",
        "signer2Name": "Beltrano",
        "signer2Company": "Cliente Teste",
    }


def test_chat_endpoint_aplica_operacao_por_id_e_preserva_id(monkeypatch):
    monkeypatch.setattr(
        main_module, "call_chat",
        lambda message, state, history: ("Grupo renomeado.", [
            {"op": "rename_group", "packageKey": "pkg-1", "groupId": "g1", "newName": "Novo Nome"}
        ]),
    )
    client = _client(monkeypatch)
    with client:
        response = client.post("/chat", json={"message": "renomeia o grupo", "state": _chat_state_payload(), "history": []})
    app.dependency_overrides.pop(require_session, None)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Grupo renomeado."
    group = body["state"]["packages"][0]["groups"][0]
    assert group["id"] == "g1"
    assert group["name"] == "Novo Nome"
    assert group["activities"][0]["id"] == "a1"


def test_chat_endpoint_add_group_devolve_id_novo_gerado_pelo_backend(monkeypatch):
    monkeypatch.setattr(
        main_module, "call_chat",
        lambda message, state, history: ("Grupo criado.", [
            {"op": "add_group", "packageKey": "pkg-1", "name": "Grupo Novo", "performance": 90.0}
        ]),
    )
    client = _client(monkeypatch)
    with client:
        response = client.post("/chat", json={"message": "cria um grupo", "state": _chat_state_payload(), "history": []})
    app.dependency_overrides.pop(require_session, None)

    assert response.status_code == 200
    groups = response.json()["state"]["packages"][0]["groups"]
    assert len(groups) == 2
    new_group = next(g for g in groups if g["name"] == "Grupo Novo")
    assert new_group["id"] and new_group["id"] != "g1"


def test_chat_endpoint_operacao_invalida_vira_502(monkeypatch):
    monkeypatch.setattr(
        main_module, "call_chat",
        lambda message, state, history: ("...", [
            {"op": "rename_group", "packageKey": "pkg-1", "groupId": "id-que-nao-existe", "newName": "X"}
        ]),
    )
    client = _client(monkeypatch)
    with client:
        response = client.post("/chat", json={"message": "pedido", "state": _chat_state_payload(), "history": []})
    app.dependency_overrides.pop(require_session, None)

    assert response.status_code == 502
    assert "não encontrado" in response.json()["detail"]


def test_chat_endpoint_rejeita_grupo_sem_id_com_422():
    """Regressão: `id` em ChatGroup/ChatActivity é obrigatório desde a Fase 8
    — um payload do formato antigo (sem id) precisa falhar cedo, na
    validação do Pydantic, não silenciosamente."""
    app.dependency_overrides[require_session] = _fake_user
    payload = _chat_state_payload()
    del payload["packages"][0]["groups"][0]["id"]
    client = TestClient(app)
    with client:
        response = client.post("/chat", json={"message": "pedido", "state": payload, "history": []})
    app.dependency_overrides.pop(require_session, None)
    assert response.status_code == 422
