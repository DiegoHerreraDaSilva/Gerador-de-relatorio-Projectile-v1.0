"""Testes do núcleo de autorização (`core/authz.py`): parsing das allowlists
(normalização em minúsculas, fallback por papel) e as funções de papel que
todos os consumidores usam.

Antes isso vivia em `management.py`, com cada módulo importando a própria
cópia do set (o monkeypatch precisava acertar o módulo definidor). Agora o
patch é em `authz.<SET>` e vale pra todo consumidor — inclusive a dependência
do FastAPI, o que o último teste prova."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.api import dependencies
from backend.app.core import authz


def test_parse_logins_normaliza_caixa_e_remove_vazios():
    assert authz.parse_logins("Dherrera, LFranco,, lvicente ", set()) == {"dherrera", "lfranco", "lvicente"}


def test_parse_logins_vazio_usa_fallback_e_devolve_copia():
    fallback = {"dherrera"}

    parsed = authz.parse_logins("  ,, ", fallback)

    assert parsed == fallback
    assert parsed is not fallback  # nunca devolve o próprio set do chamador


def test_parse_logins_sem_fallback_para_coordenador():
    assert authz.parse_logins("", set()) == set()


def test_is_manager_ignora_caixa(monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"dherrera"})

    assert authz.is_manager({"login": "DHerrera"})
    assert not authz.is_manager({"login": "outro"})


def test_roles_for_devolve_os_tres_flags(monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})
    monkeypatch.setattr(authz, "COORDINATOR_LOGINS", {"coord"})
    monkeypatch.setattr(authz, "TRANSLATE_ALLOWED_LOGINS", {"trad"})

    assert authz.roles_for({"login": "Gerente"}) == {"is_manager": True, "is_coordinator": False, "is_translate_allowed": False}
    assert authz.roles_for({"login": "coord"}) == {"is_manager": False, "is_coordinator": True, "is_translate_allowed": False}
    assert authz.roles_for({"login": "trad"}) == {"is_manager": False, "is_coordinator": False, "is_translate_allowed": True}


def test_dependency_reage_ao_monkeypatch_do_authz(monkeypatch):
    """A prova de que a pegadinha do `from import` morreu: patchando SÓ o
    authz (nenhum módulo definidor), a dependência do FastAPI — que era o
    caso mais frágil — enxerga o novo valor."""
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})

    assert dependencies.require_manager({"login": "Gerente"}) == {"login": "Gerente"}


def test_dependency_nega_sem_papel(monkeypatch):
    monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", {"gerente"})

    with pytest.raises(HTTPException) as exc:
        dependencies.require_manager({"login": "outro"})
    assert exc.value.status_code == 403
