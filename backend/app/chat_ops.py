"""Catálogo de operações que o assistente de chat pode pedir, e o aplicador que
as executa em cima do estado atual do relatório.

Por que operações em vez de ecoar o relatório inteiro de volta (formato antigo):
a IA gera MUITO menos texto pra dizer "renomeia o grupo X pra Y" do que pra
reescrever cada grupo/atividade do zero, mesmo os que não mudaram — e é a
geração de tokens de saída que domina o tempo de resposta. O trade-off é que a
aplicação da mudança fica mais complexa: em vez de "substitui tudo", precisa
localizar cada alvo (pacote/grupo/atividade) e validar que ele existe.
"""
from __future__ import annotations

import copy

TOOL_NAME = "apply_report_operations"

SYSTEM_PROMPT = """Você edita os dados de um relatório de horas de projetos de engenharia,
devolvendo uma LISTA DE OPERAÇÕES em vez de reescrever o relatório inteiro.

Estrutura do estado atual que você recebe (só leitura — é o ANTES, você não edita
esse JSON diretamente):
- `packages`: lista de relatórios/projetos abertos. Cada um tem `key` (identificador
  único do pacote — use em `packageKey`), `projectCode`, `projectName`, `groups`.
- Cada grupo tem `name`, `performance` (multiplicador numérico) e `activities`.
- Cada atividade tem `description` e `hours` (número, ou `null` = atividade extra
  ainda sem apontamento real).
- `activePackageIndex`: índice do pacote que o usuário está vendo — se o pedido
  não especificar "todos os relatórios/pacotes", aplique só nesse pacote (use
  `packages[activePackageIndex].key` como `packageKey`).

Catálogo de operações (campo `op`):
- `rename_group` {packageKey, group, newName} — renomeia um grupo existente.
- `set_group_performance` {packageKey, group, performance} — muda a performance de um grupo.
- `add_group` {packageKey, name, performance} — cria um grupo novo (vazio).
- `remove_group` {packageKey, group} — remove um grupo inteiro (e todas as atividades dele).
- `set_activity_hours` {packageKey, group, activity, hours} — muda as horas de uma
  atividade (`hours` pode ser `null` pra virar atividade extra sem apontamento).
- `set_activity_description` {packageKey, group, activity, newDescription} — renomeia a descrição de uma atividade.
- `add_activity` {packageKey, group, description, hours} — adiciona uma atividade nova a um grupo.
- `remove_activity` {packageKey, group, activity} — remove uma atividade.
- `set_package_field` {packageKey, field, value} — `field` é `projectCode` ou `projectName`.
- `set_shared_field` {field, value} — campo compartilhado entre TODOS os pacotes:
  `locationDate`, `monthLabel`, `signer1Name`, `signer1Company`, `signer2Name`, `signer2Company`.

Regras:
1. `group` e `activity` identificam o alvo pelo nome/descrição ATUAL dele NO MOMENTO
   em que cada operação é aplicada — as operações são executadas em ORDEM, uma de
   cada vez, cada uma vendo o resultado das anteriores. Se você renomear um grupo
   e depois quiser mudar a performance DESSE MESMO grupo na mesma resposta, use o
   NOME NOVO na operação seguinte (a renomeação já aconteceu quando ela rodar).
2. Gere o MENOR número de operações que resolve o pedido — não descreva mudanças
   que não foram pedidas, e nunca emita uma operação pra algo que já está do jeito
   pedido.
3. Se o pedido mencionar um pacote/grupo/atividade que NÃO existe no estado atual,
   NÃO invente a operação — devolva `operations: []` e explique o motivo no `summary`.
4. `summary`: resumo curto (1-2 frases, português, tom direto) do que foi feito —
   ou do motivo de nada ter sido feito, se for o caso.
5. Se houver mensagens anteriores nesta conversa, use-as só para entender
   referências ambíguas do pedido atual (ex: "esse grupo", "ele", "de novo") —
   as operações devem sempre ser aplicadas sobre o `Estado atual` desta
   mensagem, nunca sobre um estado de uma mensagem anterior.
"""

_OPERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {
            "type": "string",
            "enum": [
                "rename_group", "set_group_performance", "add_group", "remove_group",
                "set_activity_hours", "set_activity_description", "add_activity", "remove_activity",
                "set_package_field", "set_shared_field",
            ],
        },
        "packageKey": {"type": "string", "description": "Chave do pacote alvo (não usado em set_shared_field)."},
        "group": {"type": "string", "description": "Nome ATUAL do grupo alvo."},
        "activity": {"type": "string", "description": "Descrição ATUAL da atividade alvo."},
        "newName": {"type": "string", "description": "Usado em rename_group."},
        "newDescription": {"type": "string", "description": "Usado em set_activity_description."},
        "performance": {"type": "number", "description": "Usado em set_group_performance e add_group."},
        "hours": {"type": ["number", "null"], "description": "Usado em set_activity_hours e add_activity."},
        "description": {"type": "string", "description": "Usado em add_activity (descrição da atividade nova)."},
        "name": {"type": "string", "description": "Usado em add_group (nome do grupo novo)."},
        "field": {"type": "string", "description": "Usado em set_package_field/set_shared_field."},
        "value": {"type": "string", "description": "Usado em set_package_field/set_shared_field."},
    },
    "required": ["op"],
}

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": "Aplica uma lista de operações pontuais no relatório, em vez de reescrevê-lo inteiro.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Resumo curto (1-2 frases) do que foi feito, em português."},
            "operations": {"type": "array", "items": _OPERATION_SCHEMA},
        },
        "required": ["summary", "operations"],
    },
}


class OperationError(ValueError):
    """Uma operação referenciou um pacote/grupo/atividade que não existe, um campo
    inválido, ou veio com formato errado — sinal de que a IA alucinou uma
    referência ou o pedido do usuário era ambíguo. Sempre vira um 502 pro cliente,
    nunca aplica parte das operações."""


def _find_package(state: dict, key: str) -> dict:
    for pkg in state["packages"]:
        if pkg["key"] == key:
            return pkg
    raise OperationError(f'Pacote "{key}" não encontrado.')


def _find_group(pkg: dict, name: str) -> dict:
    for g in pkg["groups"]:
        if g["name"] == name:
            return g
    raise OperationError(f'Grupo "{name}" não encontrado no pacote "{pkg["key"]}".')


def _find_activity(group: dict, description: str) -> dict:
    for a in group["activities"]:
        if a["description"] == description:
            return a
    raise OperationError(f'Atividade "{description}" não encontrada no grupo "{group["name"]}".')


_PACKAGE_FIELDS = {"projectCode", "projectName"}
_SHARED_FIELDS = {
    "locationDate", "monthLabel",
    "signer1Name", "signer1Company", "signer2Name", "signer2Company",
}


def _apply_one(state: dict, op: dict) -> None:
    kind = op.get("op")
    if kind == "rename_group":
        group = _find_group(_find_package(state, op["packageKey"]), op["group"])
        group["name"] = op["newName"]
    elif kind == "set_group_performance":
        group = _find_group(_find_package(state, op["packageKey"]), op["group"])
        group["performance"] = float(op["performance"])
    elif kind == "add_group":
        pkg = _find_package(state, op["packageKey"])
        if any(g["name"] == op["name"] for g in pkg["groups"]):
            raise OperationError(f'Já existe um grupo "{op["name"]}" no pacote "{pkg["key"]}".')
        pkg["groups"].append({"name": op["name"], "performance": float(op.get("performance", 1)), "activities": []})
    elif kind == "remove_group":
        pkg = _find_package(state, op["packageKey"])
        target = _find_group(pkg, op["group"])
        pkg["groups"] = [g for g in pkg["groups"] if g is not target]
    elif kind == "set_activity_hours":
        group = _find_group(_find_package(state, op["packageKey"]), op["group"])
        activity = _find_activity(group, op["activity"])
        activity["hours"] = op["hours"]
    elif kind == "set_activity_description":
        group = _find_group(_find_package(state, op["packageKey"]), op["group"])
        activity = _find_activity(group, op["activity"])
        activity["description"] = op["newDescription"]
    elif kind == "add_activity":
        group = _find_group(_find_package(state, op["packageKey"]), op["group"])
        group["activities"].append({"description": op["description"], "hours": op.get("hours")})
    elif kind == "remove_activity":
        group = _find_group(_find_package(state, op["packageKey"]), op["group"])
        target = _find_activity(group, op["activity"])
        group["activities"] = [a for a in group["activities"] if a is not target]
    elif kind == "set_package_field":
        pkg = _find_package(state, op["packageKey"])
        field = op.get("field")
        if field not in _PACKAGE_FIELDS:
            raise OperationError(f'Campo de pacote inválido: "{field}".')
        pkg[field] = op["value"]
    elif kind == "set_shared_field":
        field = op.get("field")
        if field not in _SHARED_FIELDS:
            raise OperationError(f'Campo compartilhado inválido: "{field}".')
        state[field] = op["value"]
    else:
        raise OperationError(f'Tipo de operação desconhecido: "{kind}".')


def apply_operations(state: dict, operations: list[dict]) -> dict:
    """Aplica as operações em SEQUÊNCIA sobre uma cópia do estado (nunca muta o
    original) e devolve o novo estado. Levanta OperationError na primeira
    operação inválida — tudo ou nada, nunca aplica só uma parte da lista."""
    new_state = copy.deepcopy(state)
    for index, op in enumerate(operations):
        try:
            _apply_one(new_state, op)
        except OperationError:
            raise
        except (KeyError, TypeError) as e:
            raise OperationError(f"Operação {index + 1} ({op.get('op')}) malformada: campo {e} ausente ou inválido.") from e
    return new_state
