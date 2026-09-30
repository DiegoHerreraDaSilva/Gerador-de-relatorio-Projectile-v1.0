"""Dependências do FastAPI compartilhadas entre routers (main.py não
concentra mais as rotas).

Quem é gerente/coordenador/tradutor vive em `core/authz.py` — as funções de
lá leem os sets centrais na hora da chamada, então um monkeypatch em
`authz.MANAGEMENT_PANEL_LOGINS` (padrão dos testes) vale pra todos os
consumidores, sem a antiga pegadinha do `from import` congelar a cópia.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from ..auth import get_session
from ..core import authz

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
    if not authz.is_manager(_user):
        raise HTTPException(403, "Sem acesso ao painel de gerência.")
    return _user


def require_manager_or_coordinator(_user: dict = Depends(require_session)) -> dict:
    """Gerente ou coordenador — usado pelas rotas do Diagnóstico e da busca
    por cliente/projeto na importação. Os KPIs do Painel de Gerência
    (`/management/kpis`), a entrada manual mensal e o Analytics continuam em
    `require_manager`: coordenador não enxerga esses números nem pela API
    (o Diagnóstico usa `/management/send-status`, sem horas)."""
    if not (authz.is_manager(_user) or authz.is_coordinator(_user)):
        raise HTTPException(403, "Sem acesso a esta área.")
    return _user


def require_translate_access(_user: dict = Depends(require_session)) -> dict:
    """Barra com 403 quem não está na allowlist de tradução — cada clique no
    botão "EN" do preview chama a API da Anthropic, então isso existe pra
    limitar o gasto a quem realmente precisa (ver
    `TRANSLATE_ALLOWED_LOGINS` em core/authz.py)."""
    if not authz.is_translate_allowed(_user):
        raise HTTPException(403, "Sem acesso à tradução do relatório.")
    return _user


# re-exportadas pra quem só CONSULTA (não bloqueia): resposta de login,
# filtro de `/reports`, etc. — mesmo espírito de antes, agora delegando.
is_manager = authz.is_manager
is_coordinator = authz.is_coordinator
is_translate_allowed = authz.is_translate_allowed
