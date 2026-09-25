"""Catálogo de operações que o assistente de chat pode pedir, e o aplicador que
as executa em cima do estado atual do relatório.

Por que operações em vez de ecoar o relatório inteiro de volta (formato antigo):
a IA gera MUITO menos texto pra dizer "renomeia o grupo X pra Y" do que pra
reescrever cada grupo/atividade do zero, mesmo os que não mudaram — e é a
geração de tokens de saída que domina o tempo de resposta. O trade-off é que a
aplicação da mudança fica mais complexa: em vez de "substitui tudo", precisa
localizar cada alvo (pacote/grupo/atividade) e validar que ele existe.

Grupos e atividades são localizados por `id` estável (não por
nome/descrição). Antes desta mudança, a
IA precisava reproduzir nome/descrição CARACTERE POR CARACTERE pra localizar
o alvo, e nomes duplicados eram um erro explícito porque não dava pra saber
qual dos dois grupos era o pretendido — um `id` opaco elimina as duas
fragilidades: é um token curto fácil de copiar de volta sem erro, e nunca é
ambíguo mesmo com nomes repetidos."""
from __future__ import annotations

import copy
import uuid

TOOL_NAME = "apply_report_operations"

SYSTEM_PROMPT = """Você edita os dados de um relatório de horas de projetos de engenharia,
devolvendo uma LISTA DE OPERAÇÕES em vez de reescrever o relatório inteiro.

Estrutura do estado atual que você recebe (só leitura — é o ANTES, você não edita
esse JSON diretamente):
- `packages`: lista de relatórios/projetos abertos. Cada um tem `key` (identificador
  único do pacote — use em `packageKey`), `projectCode`, `projectName`, `groups`.
- Cada grupo tem `id` (identificador estável — use em `groupId`), `name`,
  `performance` (multiplicador numérico) e `activities`.
- Cada atividade tem `id` (identificador estável — use em `activityId`),
  `description` e `hours` (número, ou `null` = atividade extra ainda sem
  apontamento real).
- `activePackageIndex`: índice do pacote que o usuário está vendo — se o pedido
  não especificar "todos os relatórios/pacotes", aplique só nesse pacote (use
  `packages[activePackageIndex].key` como `packageKey`).

Catálogo de operações (campo `op`):
- `rename_group` {packageKey, groupId, newName} — renomeia um grupo existente.
- `set_group_performance` {packageKey, groupId, performance} — muda a performance de um grupo.
- `add_group` {packageKey, name, performance, activities?} — cria um grupo novo.
  `activities` é opcional: lista de `{description, hours}` pra já criar o grupo
  com atividades (prefira isso a criar vazio e adicionar depois, veja regra 1).
- `remove_group` {packageKey, groupId} — remove um grupo inteiro (e todas as atividades dele).
- `set_activity_hours` {packageKey, groupId, activityId, hours} — muda as horas de uma
  atividade (`hours` pode ser `null` pra virar atividade extra sem apontamento).
- `set_activity_description` {packageKey, groupId, activityId, newDescription} — renomeia a descrição de uma atividade.
- `add_activity` {packageKey, groupId, description, hours} — adiciona uma atividade nova a um grupo já existente.
- `remove_activity` {packageKey, groupId, activityId} — remove uma atividade.
- `sort_activities_alphabetically` {packageKey, groupId} — reordena as atividades
  desse grupo em ordem alfabética pela descrição (A-Z, sem diferenciar
  maiúscula/minúscula). Use pra qualquer pedido de "ordenar"/"organizar" as
  atividades de um grupo — não tente simular a ordenação reescrevendo cada
  atividade manualmente.
- `set_package_field` {packageKey, field, value} — `field` é `projectCode` ou `projectName`.
- `set_shared_field` {field, value} — campo compartilhado entre TODOS os pacotes:
  `locationDate`, `monthLabel`, `signer1Name`, `signer1Company`, `signer2Name`, `signer2Company`.

Regras:
1. `groupId`/`activityId` identificam o alvo pelo ID ESTÁVEL do "Estado atual" —
   copie o valor EXATAMENTE (é um token opaco: nunca invente, abrevie ou
   reconstrua um). Um grupo/atividade criado por `add_group`/`add_activity` só
   ganha id DEPOIS de aplicado — você não sabe esse id de antemão. Por isso: se
   o pedido pede pra criar algo e IMEDIATAMENTE editar esse mesmo algo (ex:
   "cria um grupo X com uma atividade Y de 5h"), já crie com os valores finais
   corretos numa única operação (`add_group` aceita `activities` inicial) em
   vez de criar e depois tentar referenciar o que acabou de criar.
2. Gere o MENOR número de operações que resolve o pedido — não descreva mudanças
   que não foram pedidas, e nunca emita uma operação pra algo que já está do jeito
   pedido.
3. Se o pedido mencionar um pacote/grupo/atividade que NÃO existe no estado atual,
   NÃO invente a operação — devolva `operations: []` e explique o motivo no `summary`.
4. `summary`: resumo curto (1-2 frases, português, tom direto) do que foi feito —
   ou do motivo de nada ter sido feito, se for o caso.
5. Em pedidos que afetam "todos/todas" (ex: "todos os grupos", "todas as
   atividades"), CONTE quantos itens existem no estado atual e gere UMA
   operação pra CADA UM deles — nunca pare antes do fim da lista. Antes de
   devolver a resposta, revise se o número de operações bate com o número de
   alvos existentes.
"""

_ACTIVITY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "hours": {"type": ["number", "null"]},
    },
    "required": ["description"],
}

_OPERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {
            "type": "string",
            "enum": [
                "rename_group", "set_group_performance", "add_group", "remove_group",
                "set_activity_hours", "set_activity_description", "add_activity", "remove_activity",
                "sort_activities_alphabetically",
                "set_package_field", "set_shared_field",
            ],
        },
        "packageKey": {"type": "string", "description": "Chave do pacote alvo (não usado em set_shared_field)."},
        "groupId": {"type": "string", "description": "ID estável do grupo alvo (do Estado atual)."},
        "activityId": {"type": "string", "description": "ID estável da atividade alvo (do Estado atual)."},
        "newName": {"type": "string", "description": "Usado em rename_group."},
        "newDescription": {"type": "string", "description": "Usado em set_activity_description."},
        "performance": {"type": "number", "description": "Usado em set_group_performance e add_group."},
        "hours": {"type": ["number", "null"], "description": "Usado em set_activity_hours e add_activity."},
        "description": {"type": "string", "description": "Usado em add_activity (descrição da atividade nova)."},
        "name": {"type": "string", "description": "Usado em add_group (nome do grupo novo)."},
        "activities": {
            "type": "array", "items": _ACTIVITY_INPUT_SCHEMA,
            "description": "Usado em add_group (atividades iniciais do grupo novo, opcional).",
        },
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


def _new_id() -> str:
    return str(uuid.uuid4())


def _find_package(state: dict, key: str) -> dict:
    for pkg in state["packages"]:
        if pkg["key"] == key:
            return pkg
    raise OperationError(f'Pacote "{key}" não encontrado.')


def _find_group(pkg: dict, group_id: str) -> dict:
    for g in pkg["groups"]:
        if g["id"] == group_id:
            return g
    raise OperationError(f'Grupo com id "{group_id}" não encontrado no pacote "{pkg["key"]}".')


def _find_activity(group: dict, activity_id: str) -> dict:
    for a in group["activities"]:
        if a["id"] == activity_id:
            return a
    raise OperationError(f'Atividade com id "{activity_id}" não encontrada no grupo "{group["name"]}".')


_PACKAGE_FIELDS = {"projectCode", "projectName"}
_SHARED_FIELDS = {
    "locationDate", "monthLabel",
    "signer1Name", "signer1Company", "signer2Name", "signer2Company",
}


def _find_target_group(state: dict, op: dict) -> dict:
    """Atalho para o par pacote+grupo usado por toda operação que só precisa do
    grupo (não do pacote em si) — repetido em várias operações abaixo."""
    return _find_group(_find_package(state, op["packageKey"]), op["groupId"])


def _apply_one(state: dict, op: dict) -> None:
    kind = op.get("op")
    if kind == "rename_group":
        group = _find_target_group(state, op)
        pkg = _find_package(state, op["packageKey"])
        new_name = op["newName"]
        if new_name != group["name"] and any(g["name"] == new_name for g in pkg["groups"]):
            raise OperationError(f'Já existe um grupo "{new_name}" no pacote "{pkg["key"]}".')
        group["name"] = new_name
    elif kind == "set_group_performance":
        group = _find_target_group(state, op)
        group["performance"] = float(op["performance"])
    elif kind == "add_group":
        pkg = _find_package(state, op["packageKey"])
        if any(g["name"] == op["name"] for g in pkg["groups"]):
            raise OperationError(f'Já existe um grupo "{op["name"]}" no pacote "{pkg["key"]}".')
        initial_activities = [
            {"id": _new_id(), "description": a["description"], "hours": a.get("hours")}
            for a in op.get("activities") or []
        ]
        pkg["groups"].append({
            "id": _new_id(),
            "name": op["name"],
            "performance": float(op.get("performance", 1)),
            "activities": initial_activities,
        })
    elif kind == "remove_group":
        pkg = _find_package(state, op["packageKey"])
        target = _find_group(pkg, op["groupId"])
        pkg["groups"] = [g for g in pkg["groups"] if g is not target]
    elif kind == "set_activity_hours":
        group = _find_target_group(state, op)
        activity = _find_activity(group, op["activityId"])
        activity["hours"] = op["hours"]
    elif kind == "set_activity_description":
        group = _find_target_group(state, op)
        activity = _find_activity(group, op["activityId"])
        activity["description"] = op["newDescription"]
    elif kind == "add_activity":
        group = _find_target_group(state, op)
        group["activities"].append({"id": _new_id(), "description": op["description"], "hours": op.get("hours")})
    elif kind == "remove_activity":
        group = _find_target_group(state, op)
        target = _find_activity(group, op["activityId"])
        group["activities"] = [a for a in group["activities"] if a is not target]
    elif kind == "sort_activities_alphabetically":
        group = _find_target_group(state, op)
        group["activities"].sort(key=lambda a: a["description"].strip().lower())
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
