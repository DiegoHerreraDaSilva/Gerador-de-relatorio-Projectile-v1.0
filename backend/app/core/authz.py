"""Autorização central: quem é gerente, coordenador e quem pode traduzir.

Antes cada módulo guardava a própria cópia das allowlists lidas de
`os.environ` no import (`management.MANAGEMENT_PANEL_LOGINS` etc.), o que
obrigava a convenção "referencie via atributo do módulo, nunca `from import`"
— um `from import` congelava a cópia e um monkeypatch no módulo definidor
não surtia efeito (bug real já encontrado em produção/testes). Aqui:

- as allowlists moram em UM lugar (`core.config.Settings`, que lê as mesmas
  variáveis `MANAGEMENT_PANEL_LOGINS`/`COORDINATOR_LOGINS`/
  `TRANSLATE_ALLOWED_LOGINS` do `.env`), normalizadas em minúsculas;
- os consumidores chamam as FUNÇÕES (`is_manager`, `roles_for`, ...), nunca
  importam os sets — então monkeypatch em `authz.MANAGEMENT_PANEL_LOGINS`
  (o padrão dos testes) vale pra todo mundo;
- mudança de allowlist continua exigindo reiniciar o backend (a leitura é no
  import do módulo), como já era documentado.
"""

from __future__ import annotations

from .config import get_settings


def parse_logins(raw: str, fallback: set[str]) -> set[str]:
    """CSV → conjunto de logins minúsculos, sem espaços/vazios. CSV vazio usa
    o fallback (cópia — nunca devolve o próprio objeto do chamador)."""
    parsed = {login.strip().lower() for login in raw.split(",") if login.strip()}
    return parsed or set(fallback)


_settings = get_settings()

# Fallbacks: gerente e tradução caem em {"dherrera"} com env ausente/vazia
# (nunca travar o app por falta de configuração); coordenador NÃO tem
# fallback — dar acesso a mais por falta de env seria o erro perigoso.
MANAGEMENT_PANEL_LOGINS: set[str] = parse_logins(_settings.management_panel_logins, {"dherrera"})
COORDINATOR_LOGINS: set[str] = parse_logins(_settings.coordinator_logins, set())
TRANSLATE_ALLOWED_LOGINS: set[str] = parse_logins(_settings.translate_allowed_logins, {"dherrera"})


def is_manager(user: dict) -> bool:
    return user["login"].lower() in MANAGEMENT_PANEL_LOGINS


def is_coordinator(user: dict) -> bool:
    return user["login"].lower() in COORDINATOR_LOGINS


def is_translate_allowed(user: dict) -> bool:
    return user["login"].lower() in TRANSLATE_ALLOWED_LOGINS


def roles_for(user: dict) -> dict:
    """Os três flags que `/auth/login` e `/auth/me` devolvem."""
    return {"is_manager": is_manager(user), "is_coordinator": is_coordinator(user), "is_translate_allowed": is_translate_allowed(user)}
