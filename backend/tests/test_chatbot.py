"""Trava o payload que `chatbot.call_chat`/`call_translate` monta pra API da
Anthropic — em especial que o histórico de conversa (`history`) vira turnos
de verdade na lista `messages`, na ordem certa, antes da mensagem atual (ver
CLAUDE.md "IA prompt" e o comentário em `call_chat`). Mocka o client da
Anthropic (`chatbot._get_client`) em vez de bater na API de verdade — aqui
importa só o formato do request montado e como a resposta é interpretada,
não o modelo em si.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import chatbot


def _tool_use_response(tool_name: str, input_payload: dict):
    block = SimpleNamespace(type="tool_use", name=tool_name, input=input_payload)
    return SimpleNamespace(content=[block])


@pytest.fixture
def fake_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(chatbot, "_get_client", lambda: client)
    return client


def test_call_chat_without_history_sends_single_message(fake_client):
    """Regressão: sem `history` (ou lista vazia), o comportamento é idêntico
    ao de antes desta feature — uma única mensagem `user`."""
    fake_client.messages.create.return_value = _tool_use_response(
        chatbot.TOOL_NAME, {"summary": "ok", "operations": []}
    )

    chatbot.call_chat("Renomeia o grupo Geral", {"packages": []}, history=None)

    kwargs = fake_client.messages.create.call_args.kwargs
    assert len(kwargs["messages"]) == 1
    assert kwargs["messages"][0]["role"] == "user"
    assert "Renomeia o grupo Geral" in kwargs["messages"][0]["content"]


def test_call_chat_with_history_prepends_turns_in_order(fake_client):
    """Os turnos de `history` viram mensagens `user`/`assistant` alternadas,
    ANTES da mensagem final (estado atual + pedido) — é isso que dá à IA
    memória do que já foi dito na conversa (sem isso, cada chamada era
    completamente sem contexto, ver comentário em call_chat)."""
    fake_client.messages.create.return_value = _tool_use_response(
        chatbot.TOOL_NAME, {"summary": "ok", "operations": []}
    )
    history = [
        {"role": "user", "text": "Renomeia o grupo Bumper pra Estrutura"},
        {"role": "assistant", "text": "Grupo renomeado."},
    ]

    chatbot.call_chat("Não, o OUTRO grupo", {"packages": []}, history=history)

    kwargs = fake_client.messages.create.call_args.kwargs
    messages = kwargs["messages"]
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "Renomeia o grupo Bumper pra Estrutura"}
    assert messages[1] == {"role": "assistant", "content": "Grupo renomeado."}
    assert messages[2]["role"] == "user"
    assert "Não, o OUTRO grupo" in messages[2]["content"]


def test_call_chat_returns_summary_and_operations(fake_client):
    fake_client.messages.create.return_value = _tool_use_response(
        chatbot.TOOL_NAME, {"summary": "Grupo renomeado.", "operations": [{"op": "rename_group"}]}
    )

    summary, operations = chatbot.call_chat("pedido", {"packages": []})

    assert summary == "Grupo renomeado."
    assert operations == [{"op": "rename_group"}]


def test_call_chat_raises_upstream_error_without_tool_use(fake_client):
    fake_client.messages.create.return_value = SimpleNamespace(content=[])

    with pytest.raises(chatbot.ChatUpstreamError):
        chatbot.call_chat("pedido", {"packages": []})


@pytest.mark.parametrize("target_language", ["en", "de"])
def test_call_translate_uses_target_language_in_system_prompt(fake_client, target_language):
    """O prompt de sistema muda com o idioma-alvo (EN/DE) — sem isso, o botão
    "DE" do preview traduziria pra inglês por engano."""
    fake_client.messages.create.return_value = _tool_use_response(
        chatbot.TRANSLATE_TOOL_NAME, {"translations": [{"id": "a", "text": "x"}]}
    )

    chatbot.call_translate([{"id": "a", "text": "Atividade"}], target_language)

    kwargs = fake_client.messages.create.call_args.kwargs
    system_text = kwargs["system"][0]["text"]
    expected_label = "alemão" if target_language == "de" else "inglês"
    assert expected_label in system_text


def test_call_translate_defaults_to_english(fake_client):
    fake_client.messages.create.return_value = _tool_use_response(
        chatbot.TRANSLATE_TOOL_NAME, {"translations": []}
    )

    chatbot.call_translate([{"id": "a", "text": "Atividade"}])

    kwargs = fake_client.messages.create.call_args.kwargs
    assert "inglês" in kwargs["system"][0]["text"]
