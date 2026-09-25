"""Cobertura de `chat_ops.apply_operations` — localização de alvo por `id`
estável, não por nome/
descrição. Não havia teste nenhum pra este módulo antes desta mudança."""
from __future__ import annotations

import pytest

from backend.app.chat_ops import OperationError, apply_operations


def _state(groups=None):
    return {
        "packages": [
            {
                "key": "pkg-1",
                "projectCode": "SE.01.002",
                "projectName": "Projeto Teste",
                "groups": groups if groups is not None else [],
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


def _group(group_id="g1", name="Grupo A", performance=100.0, activities=None):
    return {"id": group_id, "name": name, "performance": performance, "activities": activities or []}


def _activity(activity_id="a1", description="Atividade 1", hours=8.0):
    return {"id": activity_id, "description": description, "hours": hours}


def test_rename_group_por_id():
    state = _state([_group()])
    result = apply_operations(state, [{"op": "rename_group", "packageKey": "pkg-1", "groupId": "g1", "newName": "Novo Nome"}])
    assert result["packages"][0]["groups"][0]["name"] == "Novo Nome"


def test_rename_group_grupo_inexistente_levanta_operation_error():
    state = _state([_group()])
    with pytest.raises(OperationError, match="não encontrado"):
        apply_operations(state, [{"op": "rename_group", "packageKey": "pkg-1", "groupId": "id-que-nao-existe", "newName": "X"}])


def test_rename_group_para_nome_ja_existente_levanta_operation_error():
    state = _state([_group("g1", "Grupo A"), _group("g2", "Grupo B")])
    with pytest.raises(OperationError, match="Já existe"):
        apply_operations(state, [{"op": "rename_group", "packageKey": "pkg-1", "groupId": "g1", "newName": "Grupo B"}])


def test_dois_grupos_com_mesmo_nome_nao_sao_mais_ambiguos_porque_o_alvo_e_por_id():
    """Antes desta mudança, dois grupos com o mesmo nome eram um erro
    explícito (impossível saber qual a IA quis dizer, matching por nome). Com
    id estável, a ambiguidade simplesmente não existe mais."""
    state = _state([_group("g1", "Duplicado", performance=100.0), _group("g2", "Duplicado", performance=50.0)])
    result = apply_operations(state, [{"op": "set_group_performance", "packageKey": "pkg-1", "groupId": "g2", "performance": 200.0}])
    groups = {g["id"]: g["performance"] for g in result["packages"][0]["groups"]}
    assert groups == {"g1": 100.0, "g2": 200.0}


def test_add_group_gera_id_novo():
    state = _state([])
    result = apply_operations(state, [{"op": "add_group", "packageKey": "pkg-1", "name": "Grupo Novo", "performance": 90.0}])
    new_groups = result["packages"][0]["groups"]
    assert len(new_groups) == 1
    assert new_groups[0]["name"] == "Grupo Novo"
    assert new_groups[0]["id"]  # não vazio
    assert new_groups[0]["activities"] == []


def test_add_group_com_atividades_iniciais():
    state = _state([])
    result = apply_operations(state, [
        {
            "op": "add_group", "packageKey": "pkg-1", "name": "Grupo Novo", "performance": 100.0,
            "activities": [{"description": "Atividade X", "hours": 4.0}, {"description": "Atividade Y", "hours": None}],
        }
    ])
    activities = result["packages"][0]["groups"][0]["activities"]
    assert len(activities) == 2
    assert {a["id"] for a in activities} == {activities[0]["id"], activities[1]["id"]}
    assert len(set(a["id"] for a in activities)) == 2  # ids únicos entre si
    assert activities[0]["description"] == "Atividade X"
    assert activities[1]["hours"] is None


def test_add_group_com_nome_duplicado_levanta_operation_error():
    state = _state([_group("g1", "Existente")])
    with pytest.raises(OperationError, match="Já existe"):
        apply_operations(state, [{"op": "add_group", "packageKey": "pkg-1", "name": "Existente", "performance": 100.0}])


def test_remove_group_por_id():
    state = _state([_group("g1", "A"), _group("g2", "B")])
    result = apply_operations(state, [{"op": "remove_group", "packageKey": "pkg-1", "groupId": "g1"}])
    remaining = result["packages"][0]["groups"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == "g2"


def test_set_activity_hours_por_id():
    state = _state([_group("g1", activities=[_activity("a1", hours=8.0)])])
    result = apply_operations(state, [
        {"op": "set_activity_hours", "packageKey": "pkg-1", "groupId": "g1", "activityId": "a1", "hours": 5.5}
    ])
    assert result["packages"][0]["groups"][0]["activities"][0]["hours"] == 5.5


def test_set_activity_hours_aceita_null_para_atividade_extra():
    state = _state([_group("g1", activities=[_activity("a1", hours=8.0)])])
    result = apply_operations(state, [
        {"op": "set_activity_hours", "packageKey": "pkg-1", "groupId": "g1", "activityId": "a1", "hours": None}
    ])
    assert result["packages"][0]["groups"][0]["activities"][0]["hours"] is None


def test_set_activity_description_por_id():
    state = _state([_group("g1", activities=[_activity("a1", description="Original")])])
    result = apply_operations(state, [
        {"op": "set_activity_description", "packageKey": "pkg-1", "groupId": "g1", "activityId": "a1", "newDescription": "Corrigida"}
    ])
    assert result["packages"][0]["groups"][0]["activities"][0]["description"] == "Corrigida"


def test_activity_inexistente_levanta_operation_error():
    state = _state([_group("g1", activities=[_activity("a1")])])
    with pytest.raises(OperationError, match="não encontrada"):
        apply_operations(state, [
            {"op": "set_activity_hours", "packageKey": "pkg-1", "groupId": "g1", "activityId": "id-inexistente", "hours": 1.0}
        ])


def test_duas_atividades_com_mesma_descricao_nao_sao_mais_ambiguas():
    """Mesmo raciocínio do teste de grupos duplicados: descrição repetida
    (comum em relatórios reais) não impede mais localizar o alvo certo."""
    state = _state([_group("g1", activities=[
        _activity("a1", description="Reunião", hours=1.0),
        _activity("a2", description="Reunião", hours=2.0),
    ])])
    result = apply_operations(state, [
        {"op": "set_activity_hours", "packageKey": "pkg-1", "groupId": "g1", "activityId": "a2", "hours": 9.0}
    ])
    hours = {a["id"]: a["hours"] for a in result["packages"][0]["groups"][0]["activities"]}
    assert hours == {"a1": 1.0, "a2": 9.0}


def test_add_activity_gera_id_novo():
    state = _state([_group("g1", activities=[_activity("a1")])])
    result = apply_operations(state, [
        {"op": "add_activity", "packageKey": "pkg-1", "groupId": "g1", "description": "Nova atividade", "hours": 3.0}
    ])
    activities = result["packages"][0]["groups"][0]["activities"]
    assert len(activities) == 2
    new_activity = next(a for a in activities if a["description"] == "Nova atividade")
    assert new_activity["id"] and new_activity["id"] != "a1"


def test_remove_activity_por_id():
    state = _state([_group("g1", activities=[_activity("a1"), _activity("a2", description="Outra")])])
    result = apply_operations(state, [{"op": "remove_activity", "packageKey": "pkg-1", "groupId": "g1", "activityId": "a1"}])
    remaining = result["packages"][0]["groups"][0]["activities"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == "a2"


def test_sort_activities_alphabetically():
    state = _state([_group("g1", activities=[
        _activity("a1", description="Zebra"), _activity("a2", description="Abelha"),
    ])])
    result = apply_operations(state, [{"op": "sort_activities_alphabetically", "packageKey": "pkg-1", "groupId": "g1"}])
    descriptions = [a["description"] for a in result["packages"][0]["groups"][0]["activities"]]
    assert descriptions == ["Abelha", "Zebra"]


def test_set_package_field():
    state = _state([])
    result = apply_operations(state, [{"op": "set_package_field", "packageKey": "pkg-1", "field": "projectName", "value": "Novo Nome"}])
    assert result["packages"][0]["projectName"] == "Novo Nome"


def test_set_package_field_invalido_levanta_operation_error():
    state = _state([])
    with pytest.raises(OperationError, match="inválido"):
        apply_operations(state, [{"op": "set_package_field", "packageKey": "pkg-1", "field": "key", "value": "x"}])


def test_set_shared_field():
    state = _state([])
    result = apply_operations(state, [{"op": "set_shared_field", "field": "monthLabel", "value": "Agosto/2026"}])
    assert result["monthLabel"] == "Agosto/2026"


def test_pacote_inexistente_levanta_operation_error():
    state = _state([])
    with pytest.raises(OperationError, match="não encontrado"):
        apply_operations(state, [{"op": "rename_group", "packageKey": "pkg-inexistente", "groupId": "g1", "newName": "X"}])


def test_operacao_desconhecida_levanta_operation_error():
    state = _state([])
    with pytest.raises(OperationError, match="desconhecido"):
        apply_operations(state, [{"op": "operacao_que_nao_existe"}])


def test_operacao_malformada_levanta_operation_error_nao_key_error():
    state = _state([_group("g1")])
    with pytest.raises(OperationError, match="malformada"):
        apply_operations(state, [{"op": "rename_group", "packageKey": "pkg-1", "groupId": "g1"}])  # falta newName


def test_falha_no_meio_nao_aplica_nenhuma_operacao_tudo_ou_nada():
    state = _state([_group("g1", "A")])
    with pytest.raises(OperationError):
        apply_operations(state, [
            {"op": "rename_group", "packageKey": "pkg-1", "groupId": "g1", "newName": "Renomeado"},
            {"op": "rename_group", "packageKey": "pkg-1", "groupId": "id-invalido", "newName": "X"},
        ])
    # o estado ORIGINAL passado pra função nunca é mutado (apply_operations
    # trabalha sobre uma cópia) — continua com o nome original
    assert state["packages"][0]["groups"][0]["name"] == "A"


def test_apply_operations_nao_muta_o_estado_original():
    state = _state([_group("g1", "A")])
    apply_operations(state, [{"op": "rename_group", "packageKey": "pkg-1", "groupId": "g1", "newName": "B"}])
    assert state["packages"][0]["groups"][0]["name"] == "A"
