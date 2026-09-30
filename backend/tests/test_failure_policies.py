"""Registro da política de falha de cada store (ver `services/policy.py`).

Um store novo (módulo com persistência própria) que não estiver nem aqui nem
declarando `FAILURE_POLICY` faz este teste falhar: a decisão "pode falhar em
silêncio?" é obrigatória e explícita. O comportamento em si (fail-open de
`/generate`, 502 dos dados de gerência etc.) é coberto pelos testes de cada
módulo; aqui garantimos que a DECLARAÇÃO não ficou desatualizada."""

from __future__ import annotations

import pkgutil

import pytest

import backend.app.services as services_package
from backend.app.services import audit, auto_generation_store, management_store, report_admin, report_persistence
from backend.app.services.policy import FailurePolicy

# a decisão registrada — mudar aqui é mudar a política do projeto
_EXPECTED = {
    "report_persistence": FailurePolicy.FAIL_OPEN,
    "audit": FailurePolicy.FAIL_OPEN,
    "management_store": FailurePolicy.FAIL_CLOSED,
    "auto_generation_store": FailurePolicy.FAIL_CLOSED,
    "report_admin": FailurePolicy.FAIL_CLOSED,
}

_MODULES = {
    "report_persistence": report_persistence,
    "audit": audit,
    "management_store": management_store,
    "auto_generation_store": auto_generation_store,
    "report_admin": report_admin,
}


@pytest.mark.parametrize(("name", "expected"), _EXPECTED.items())
def test_store_declara_a_politica_registrada(name, expected):
    assert getattr(_MODULES[name], "FAILURE_POLICY", None) is expected


def test_store_novo_precisa_entrar_no_registro():
    """Varre o pacote `services`: qualquer módulo de store que não esteja no
    registro faz falhar (a lista de exceções são só os módulos que não são
    store: policy, snapshot, report_files, report_queries, system_health,
    management_store e auto_generation_store já cobertos)."""
    nao_stores = {
        "policy",
        "snapshot",
        "report_files",
        "report_queries",
        "system_health",
        "audit",
        "report_persistence",
        "management_store",
        "auto_generation_store",
        "report_admin",
    }
    encontrados = {m.name for m in pkgutil.iter_modules(services_package.__path__) if not m.name.startswith("_")}
    desconhecidos = encontrados - nao_stores

    assert desconhecidos == set(), (
        f"Módulo(s) novo(s) em services/ sem classificação de store: {sorted(desconhecidos)}. "
        "Se for um store, declare FAILURE_POLICY e adicione ao registro do teste; "
        "se não for, adicione à lista de exceções explicando o porquê."
    )
