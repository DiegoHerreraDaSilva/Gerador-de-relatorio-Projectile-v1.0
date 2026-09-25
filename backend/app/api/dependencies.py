"""Dependências do FastAPI compartilhadas entre routers (main.py não
concentra mais as rotas).

`MANAGEMENT_PANEL_LOGINS`/`TRANSLATE_ALLOWED_LOGINS` são referenciadas via
`management.<nome>` (atributo do módulo, resolvido a cada chamada) em vez de
`from .management import <nome>` — um `from import` copiaria o `set` pro
namespace deste módulo NA HORA DO IMPORT; um teste que faz
`monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", ...)` (o padrão
usado nos testes deste projeto) não afetaria essa cópia. Mesma categoria de
bug encontrada e corrigida em `services/report_persistence.py` vs
`services/report_queries.py` (dois `get_engine` independentes) — aqui
evitado desde o início."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from .. import management
from ..auth import get_session

SESSION_COOKIE = "session_token"


def require_session(request: Request) -> dict:
    """Dependência do FastAPI que barra a rota com 401 se não houver sessão
    válida — sem isso, as rotas que tocam dado sensível (Projectile, geração
    de relatório, IA) ficariam acessíveis por qualquer um com acesso de rede
    ao backend, mesmo sem logar (a tela de login só bloqueia no navegador)."""
    session = get_session(request.cookies.get(SESSION_COOKIE))
    if not session:
        raise HTTPException(401, "Sessão expirada ou inválida. Faça login de novo.")
    return session


def require_manager(_user: dict = Depends(require_session)) -> dict:
    """Barra com 403 quem não é gerente — o painel de gerência mostra dados
    de TODOS os engenheiros, não só do usuário logado, então precisa de um
    controle de acesso além da sessão comum."""
    if _user["login"].lower() not in management.MANAGEMENT_PANEL_LOGINS:
        raise HTTPException(403, "Sem acesso ao painel de gerência.")
    return _user


def require_manager_or_coordinator(_user: dict = Depends(require_session)) -> dict:
    """Gerente ou coordenador — usado pelas rotas do Diagnóstico e da busca
    por cliente/projeto na importação. Os KPIs do Painel de Gerência
    (`/management/kpis`), a entrada manual mensal e o Analytics continuam em
    `require_manager`: coordenador não enxerga esses números nem pela API
    (o Diagnóstico usa `/management/send-status`, sem horas)."""
    if not (is_manager(_user) or is_coordinator(_user)):
        raise HTTPException(403, "Sem acesso a esta área.")
    return _user


def require_translate_access(_user: dict = Depends(require_session)) -> dict:
    """Barra com 403 quem não está na allowlist de tradução — cada clique no
    botão "EN" do preview chama a API da Anthropic, então isso existe pra
    limitar o gasto a quem realmente precisa (ver `TRANSLATE_ALLOWED_LOGINS`
    em management.py)."""
    if _user["login"].lower() not in management.TRANSLATE_ALLOWED_LOGINS:
        raise HTTPException(403, "Sem acesso à tradução do relatório.")
    return _user


def is_manager(user: dict) -> bool:
    """Mesmo teste usado por `require_manager`, exposto como função direta
    pros lugares que precisam só CONSULTAR (não bloquear) — ex.: computar
    `is_manager` na resposta de login, ou filtrar `/reports` sem 403."""
    return user["login"].lower() in management.MANAGEMENT_PANEL_LOGINS


def is_coordinator(user: dict) -> bool:
    return user["login"].lower() in management.COORDINATOR_LOGINS


def is_translate_allowed(user: dict) -> bool:
    return user["login"].lower() in management.TRANSLATE_ALLOWED_LOGINS
