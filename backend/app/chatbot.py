"""Integração com a API da Anthropic para o chat de edição em massa dos dados do
relatório (grupos/atividades/cabeçalho) — o front-end manda o estado atual +
uma instrução em linguagem natural, o modelo devolve o estado inteiro já editado.

Usa tool use forçado (`tool_choice`) em vez de pedir JSON solto em texto: o
schema da tool já é o formato do estado, então a resposta chega estruturada e
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


class ChatConfigError(RuntimeError):
    """ANTHROPIC_API_KEY não configurada — erro do ambiente, não do usuário do chat."""


class ChatUpstreamError(RuntimeError):
    """A API da Anthropic falhou (rede, rate limit, etc.) ou devolveu algo que não
    bate com o schema esperado — em ambos os casos não há o que o usuário do chat
    fazer além de tentar de novo."""


TOOL_NAME = "update_report_state"

SYSTEM_PROMPT = """Você edita os dados de um relatório de horas de projetos de engenharia.

Estrutura do estado (`state`):
- `packages`: lista de relatórios/projetos abertos. Cada um tem `key` (identificador,
  não mude), `projectCode`, `projectName`, e `groups` (lista de grupos de atividade).
- Cada grupo tem `name`, `performance` (multiplicador numérico, ex: 1.0, 1.1) e
  `activities` (lista de atividades).
- Cada atividade tem `description` e `hours` (número de horas apontadas, ou `null`
  quando é uma atividade extra ainda sem apontamento — nesse caso NUNCA invente um
  valor numérico, mantenha `null`).
- `activePackageIndex`: índice do pacote que o usuário está vendo agora — se o
  pedido não especificar "todos os relatórios/pacotes", aplique a mudança só nesse
  pacote.
- `locationDate`, `monthLabel`, `signer1Name`, `signer1Company`, `signer2Name`,
  `signer2Company`: campos do cabeçalho, compartilhados entre todos os pacotes.

Regra de ouro: SEMPRE devolva a tool `update_report_state` com o array `packages`
INTEIRO, na MESMA ORDEM e MESMO TAMANHO recebido — um item por pacote de entrada,
mesmo que ele não tenha mudado nada. Nunca remova, adicione ou reordene pacotes,
grupos ou atividades além do que foi explicitamente pedido. Tudo que não foi
mencionado no pedido do usuário deve voltar exatamente como veio.

Preserve o `summary`: um resumo curto (1-2 frases, em português, tom direto) do que
foi alterado, para mostrar ao usuário no chat. Se o pedido não fizer sentido dado o
estado atual (ex: menciona um grupo que não existe), não invente uma mudança —
devolva o estado inalterado e explique o motivo no `summary`.
"""

_ACTIVITY_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "hours": {"type": ["number", "null"]},
    },
    "required": ["description", "hours"],
}

_GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "performance": {"type": "number"},
        "activities": {"type": "array", "items": _ACTIVITY_SCHEMA},
    },
    "required": ["name", "performance", "activities"],
}

_PACKAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "projectCode": {"type": "string"},
        "projectName": {"type": "string"},
        "groups": {"type": "array", "items": _GROUP_SCHEMA},
    },
    "required": ["key", "projectCode", "projectName", "groups"],
}

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": "Devolve o estado completo do relatório após aplicar a edição pedida.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Resumo curto (1-2 frases) do que foi alterado, em português."},
            "packages": {"type": "array", "items": _PACKAGE_SCHEMA},
            "activePackageIndex": {"type": "integer"},
            "locationDate": {"type": "string"},
            "monthLabel": {"type": "string"},
            "signer1Name": {"type": "string"},
            "signer1Company": {"type": "string"},
            "signer2Name": {"type": "string"},
            "signer2Company": {"type": "string"},
        },
        "required": [
            "summary", "packages", "activePackageIndex", "locationDate", "monthLabel",
            "signer1Name", "signer1Company", "signer2Name", "signer2Company",
        ],
    },
}

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


def call_chat(message: str, state: dict) -> tuple[str, dict]:
    """Manda a instrução + estado atual pra Claude, devolve (summary, novo_state).

    `state` (entrada) e o `state` embutido no retorno seguem o mesmo shape —
    quem chama é responsável por validar/serializar via os modelos Pydantic
    ChatState/ChatResponse em app/main.py.
    """
    client = _get_client()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Estado atual:\n{state}\n\n"
                        f"Pedido do usuário: {message}"
                    ),
                }
            ],
        )
    except Exception as e:
        raise ChatUpstreamError(f"Falha ao chamar a API da Anthropic: {e}") from e

    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if tool_use is None:
        raise ChatUpstreamError("A IA não devolveu uma edição estruturada. Tente reformular o pedido.")

    payload = dict(tool_use.input)
    summary = payload.pop("summary", "Alterações aplicadas.")
    return summary, payload
