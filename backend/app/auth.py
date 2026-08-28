"""Login usando as mesmas credenciais do Projectile — autentica direto contra
a tabela `auser` do MySQL (ver backend/app/projectile_db.py), sem duplicar
usuário/senha nesse app.

Esquema de hash confirmado manualmente (backend/app/auth.py não inventa isso):
`auser.rPassword` = sha256(senha + auser.rSalt), em hexadecimal.

Sessão: token aleatório opaco guardado em memória do processo (não sobrevive
a reiniciar o backend, nem escala pra múltiplos processos — aceitável pro
tamanho desse app hoje; se um dia rodar atrás de load balancer, trocar por
sessão em banco/redis). O token nunca é o hash de senha nem contém dado do
usuário — só uma chave aleatória (`secrets.token_urlsafe`) que aponta pra um
dicionário em memória.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import secrets
import time

from .projectile_db import ProjectileDbError, _get_connection

SESSION_TTL_SECONDS = 8 * 60 * 60  # uma jornada de trabalho

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


class LoginError(RuntimeError):
    """Login ou senha incorretos — mensagem genérica de propósito (não revela
    se o usuário existe ou não, pra não facilitar enumeração de contas)."""


class RateLimitError(RuntimeError):
    """Muitas tentativas de login seguidas de uma mesma origem — bloqueado
    temporariamente, independente de login/senha estarem certos ou não."""


# rate limit por IP de origem (não por login) — trava tentativas mesmo que o
# atacante troque de usuário a cada tentativa. Em memória do processo, como a
# sessão: reseta se o backend reiniciar, aceitável pro tamanho desse app hoje.
_login_attempts: dict[str, dict] = {}


def check_rate_limit(client_key: str) -> None:
    entry = _login_attempts.get(client_key)
    if not entry:
        return
    locked_until = entry.get("locked_until")
    if locked_until and locked_until > time.time():
        minutos = max(1, int((locked_until - time.time()) / 60) + 1)
        raise RateLimitError(f"Muitas tentativas de login. Tente de novo em ~{minutos} min.")
    if locked_until and locked_until <= time.time():
        # bloqueio expirou — reseta a contagem
        _login_attempts.pop(client_key, None)


def register_login_failure(client_key: str) -> None:
    entry = _login_attempts.setdefault(client_key, {"count": 0, "locked_until": None})
    entry["count"] += 1
    if entry["count"] >= MAX_LOGIN_ATTEMPTS:
        entry["locked_until"] = time.time() + LOCKOUT_SECONDS


def register_login_success(client_key: str) -> None:
    _login_attempts.pop(client_key, None)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def verify_projectile_login(login: str, password: str) -> dict:
    """Consulta `auser` pelo login e confere a senha com o mesmo esquema de
    hash do Projectile (sha256(senha+salt)). Levanta LoginError se não bater
    — nunca deixa vazar se foi "usuário não existe" ou "senha errada"."""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rId, rName, rLogin, rEmail, rPassword, rSalt FROM auser WHERE rLogin = %s",
                (login,),
            )
            row = cur.fetchone()
    except ProjectileDbError:
        raise
    except Exception as e:
        raise ProjectileDbError(f"Falha ao consultar usuário no Projectile: {e}") from e
    finally:
        conn.close()

    if not row or not row.get("rPassword") or not row.get("rSalt"):
        raise LoginError("Login ou senha incorretos.")

    expected = _hash_password(password, row["rSalt"])
    if not hmac.compare_digest(expected, (row["rPassword"] or "").strip().lower()):
        raise LoginError("Login ou senha incorretos.")

    display_name = _employee_display_name(row["rLogin"]) or row["rName"]
    return {"id": row["rId"], "name": display_name, "login": row["rLogin"], "email": row.get("rEmail") or ""}


def _employee_display_name(login: str) -> str | None:
    """`auser.rName` nem sempre é o nome usado nos relatórios (pode ser uma
    matrícula/apelido interno) — o nome de exibição de verdade, o mesmo que
    aparece em `tjob.capEmployee` (usado pra buscar as horas), vem do cadastro
    de RH em `temployee`, ligado pelo login."""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pFirstName, pName FROM temployee WHERE pLogin = %s",
                (login,),
            )
            row = cur.fetchone()
    except Exception:
        return None
    finally:
        conn.close()

    if not row:
        return None
    first_name = html.unescape(row.get("pFirstName") or "").strip()
    last_name = html.unescape(row.get("pName") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    return full_name or None


_sessions: dict[str, dict] = {}


def create_session(user: dict) -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = {**user, "expires_at": time.time() + SESSION_TTL_SECONDS}
    return token


def get_session(token: str | None) -> dict | None:
    if not token:
        return None
    session = _sessions.get(token)
    if not session:
        return None
    if session["expires_at"] < time.time():
        _sessions.pop(token, None)
        return None
    return session


def delete_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)
