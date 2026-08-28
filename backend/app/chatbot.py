"""Integração com a API da Anthropic para o chat de edição em massa dos dados do
relatório (grupos/atividades/cabeçalho) — o front-end manda o estado atual +
uma instrução em linguagem natural, o modelo devolve uma LISTA DE OPERAÇÕES
(ver chat_ops.py) descrevendo só o que mudou, em vez do relatório inteiro
reescrito — é a geração de tokens de saída que domina a latência da resposta,
então pedir menos texto pra IA gerar é o que realmente acelera a resposta
(streaming só melhora a PERCEPÇÃO de velocidade, não o tempo total).

Usa tool use forçado (`tool_choice`) em vez de pedir JSON solto em texto: o
schema da tool já é o formato esperado, então a resposta chega estruturada e
validável, sem parsing frágil de texto livre.
"""
from __future__ import annotations

import os

import truststore

# Faz o módulo `ssl` do Python usar o armazém de certificados do próprio Windows
# (o mesmo que o navegador/PowerShell usam) em vez do pacote `certifi` embutido.
# Necessário em redes corporativas com proxy de inspeção SSL: o Windows confia
# no certificado raiz da empresa (instalado via política de grupo), mas o
# `certifi` não — sem isso, toda chamada HTTPS feita pelo SDK da Anthropic
# falha com "Connection error" mesmo com a rede liberada (`Invoke-WebRequest`
# funciona porque usa o armazém do Windows nativamente).
truststore.inject_into_ssl()

from anthropic import Anthropic

from .chat_ops import TOOL_NAME, TOOL_SCHEMA, SYSTEM_PROMPT


class ChatConfigError(RuntimeError):
    """ANTHROPIC_API_KEY não configurada — erro do ambiente, não do usuário do chat."""


class ChatUpstreamError(RuntimeError):
    """A API da Anthropic falhou (rede, rate limit, etc.) ou devolveu algo que não
    bate com o schema esperado — em ambos os casos não há o que o usuário do chat
    fazer além de tentar de novo."""


_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ChatConfigError(
                "ANTHROPIC_API_KEY não configurada. Crie um arquivo .env na raiz do "
                "projeto (veja .env.example) com sua chave da API da Anthropic."
            )
        _client = Anthropic(api_key=api_key)
    return _client


def call_chat(message: str, state: dict) -> tuple[str, list[dict]]:
    """Manda a instrução + estado atual pra Claude, devolve (summary, operations).

    `operations` segue o catálogo de chat_ops.py — quem chama é responsável por
    aplicar (chat_ops.apply_operations) e validar o resultado (ChatState em
    app/main.py). Não valida aqui: o formato de cada operação só é checado no
    momento de aplicar, contra o estado real.
    """
    client = _get_client()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    try:
        response = client.messages.create(
            model=model,
            # bem menor que os 8192 do formato antigo (que ecoava o relatório
            # inteiro) — a resposta agora é só a lista de operações
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": f"Estado atual:\n{state}\n\nPedido do usuário: {message}",
                }
            ],
        )
    except Exception as e:
        raise ChatUpstreamError(f"Falha ao chamar a API da Anthropic: {e}") from e

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        raise ChatUpstreamError("A IA não devolveu uma edição estruturada. Tente reformular o pedido.")

    payload = dict(tool_use.input)
    summary = payload.get("summary", "Alterações aplicadas.")
    operations = payload.get("operations", [])
    return summary, operations
