"""Login usando as mesmas credenciais do Projectile — autentica direto contra
a tabela `auser` do MySQL (ver backend/app/projectile_db.py), sem duplicar
usuário/senha nesse app.

Esquema de hash confirmado manualmente (backend/app/auth.py não inventa isso):
`auser.rPassword` = sha256(senha + auser.rSalt), em hexadecimal.

Sessão e rate-limit de login vivem num store chave-valor com TTL:
- `SESSIONS_BACKEND=memory` (default, dev/testes): dicionário no processo —
  reinicia o backend, todos deslogam;
- `SESSIONS_BACKEND=redis` (`REDIS_URL` obrigatória, container de produção):
  session/rate-limit sobrevivem a restart e valem para vários processos
  (web + worker da topologia de containers).
O token nunca é o hash de senha nem contém dado do usuário — só uma chave
aleatória (`secrets.token_urlsafe`) que aponta pro registro no store.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import secrets
import time
from typing import Any, Protocol

from .core.config import get_settings
from .core.redis_client import get_redis_client
from .projectile_db import ProjectileDbError, open_connection

SESSION_TTL_SECONDS = 8 * 60 * 60  # uma jornada de trabalho

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


class LoginError(RuntimeError):
    """Login ou senha incorretos — mensagem genérica de propósito (não revela
    se o usuário existe ou não, pra não facilitar enumeração de contas)."""


class RateLimitError(RuntimeError):
    """Muitas tentativas de login seguidas de uma mesma origem — bloqueado
    temporariamente, independente de login/senha estarem certos ou não."""


class _Store(Protocol):
    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, value: dict, ttl_seconds: int) -> None: ...
    def delete(self, key: str) -> None: ...


class _MemoryStore:
    """Store do processo único: `ttl_seconds` por registro, checado na
    leitura (mesma semântica de expiração do Redis, só que local)."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[dict, float | None]] = {}

    def get(self, key: str) -> dict | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and expires_at <= time.time():
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self._data[key] = (value, time.time() + ttl_seconds if ttl_seconds else None)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class _RedisStore:
    """Valores JSON com TTL nativo do Redis — sobrevive a restart e vale
    entre processos."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self, key: str) -> dict | None:
        raw = self._client.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self._client.set(key, json.dumps(value), ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self._client.delete(key)


_store: _Store | None = None


def _build_store() -> _Store:
    settings = get_settings()
    backend = settings.sessions_backend.strip().lower()
    if backend == "redis":
        client = get_redis_client()
        if client is None:
            raise RuntimeError("SESSIONS_BACKEND=redis exige REDIS_URL configurada (ver .env.example) — não caímos em memória calados em produção.")
        return _RedisStore(client)
    if backend != "memory":
        raise RuntimeError(f"SESSIONS_BACKEND inválido: {backend!r} (use 'memory' ou 'redis').")
    return _MemoryStore()


def _get_store() -> _Store:
    global _store
    if _store is None:
        _store = _build_store()
    return _store


def reset_store_for_tests(store: _Store | None = None) -> None:
    """Só testes: injeta um store (ex.: fakeredis) ou volta ao padrão."""
    global _store
    _store = store


def check_rate_limit(client_key: str) -> None:
    entry = _get_store().get(f"login_fail:{client_key}")
    if not entry:
        return
    locked_until = entry.get("locked_until")
    if locked_until and locked_until > time.time():
        minutos = max(1, int((locked_until - time.time()) / 60) + 1)
        raise RateLimitError(f"Muitas tentativas de login. Tente de novo em ~{minutos} min.")
    if locked_until and locked_until <= time.time():
        # bloqueio expirou — reseta a contagem
        _get_store().delete(f"login_fail:{client_key}")


def register_login_failure(client_key: str) -> None:
    store = _get_store()
    key = f"login_fail:{client_key}"
    entry = store.get(key) or {"count": 0, "locked_until": None}
    entry["count"] += 1
    if entry["count"] >= MAX_LOGIN_ATTEMPTS:
        entry["locked_until"] = time.time() + LOCKOUT_SECONDS
    # o contador também expira (15 min de inatividade): antes, em memória,
    # ele vivia pra sempre até travar ou alguém acertar a senha
    store.set(key, entry, ttl_seconds=LOCKOUT_SECONDS)


def register_login_success(client_key: str) -> None:
    _get_store().delete(f"login_fail:{client_key}")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def verify_projectile_login(login: str, password: str) -> dict:
    """Consulta `auser` pelo login (+ `temployee` numa única query/conexão,
    via LEFT JOIN) e confere a senha com o mesmo esquema de hash do
    Projectile (sha256(senha+salt)). Levanta LoginError se não bater — nunca
    deixa vazar se foi "usuário não existe" ou "senha errada".

    `auser.rName` nem sempre é o nome usado nos relatórios (pode ser uma
    matrícula/apelido interno) — o nome de exibição de verdade, o mesmo que
    aparece em `tjob.capEmployee`, vem do cadastro de RH em `temployee`,
    ligado pelo login. Também traz `temployee.pEmployee` (a FK de verdade
    usada em `tjob.pEmployee`) pra guardar na sessão e usar depois em
    `fetch_employee_hours` sem precisar de outro lookup.

    Antes eram duas conexões seriais (uma pra `auser`, outra pra `temployee`)
    — nesse MySQL legado, abrir conexão nova já é lento por si só quando o
    servidor está sob carga, então unificar em uma só corta esse custo pela
    metade."""
    conn = open_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT au.rId, au.rName, au.rLogin, au.rEmail, au.rPassword, au.rSalt,
                       te.pEmployee AS employee_id, te.pFirstName, te.pName, te.pFiliale
                FROM auser au
                LEFT JOIN temployee te ON te.pLogin = au.rLogin
                WHERE au.rLogin = %s
                """,
                (login,),
            )
            row = cur.fetchone()
    except ProjectileDbError:
        raise
    except Exception as e:
        raise ProjectileDbError(f"Falha ao consultar usuário no Projectile: {e}") from e
    finally:
        # `open_connection()` empresta do pool — devolver aqui é
        # obrigatório, senão cada login consome uma conexão do pool pra
        # sempre até esgotá-lo.
        conn.close()

    if not row or not row.get("rPassword") or not row.get("rSalt"):
        # Calcula um hash "dummy" mesmo quando não há linha/senha/salt reais,
        # só pra gastar CPU equivalente ao caminho abaixo — reduz a diferença
        # de tempo entre "login não existe" e "login existe, senha errada"
        # (mitigação de timing attack teórico; não muda nenhum retorno).
        _hash_password(password, "dummy-salt-tempo-constante")
        hmac.compare_digest("0" * 64, "1" * 64)
        raise LoginError("Login ou senha incorretos.")

    expected = _hash_password(password, row["rSalt"])
    if not hmac.compare_digest(expected, (row["rPassword"] or "").strip().lower()):
        raise LoginError("Login ou senha incorretos.")

    first_name = html.unescape(row.get("pFirstName") or "").strip()
    last_name = html.unescape(row.get("pName") or "").strip()
    display_name = f"{first_name} {last_name}".strip() or row["rName"]
    return {
        "id": row["rId"],
        "name": display_name,
        "login": row["rLogin"],
        "email": row.get("rEmail") or "",
        "employee_id": row.get("employee_id"),
        # usada só pelo Dashboard de horas pessoal, pra decidir se o feriado
        # municipal de Santo André entra no cálculo de dias úteis dessa
        # pessoa (ver `generator.local_holidays_for_filiale`).
        "filiale": html.unescape(row.get("pFiliale") or "").strip() or None,
    }


def create_session(user: dict) -> str:
    token = secrets.token_urlsafe(32)
    _get_store().set(f"session:{token}", {**user, "expires_at": time.time() + SESSION_TTL_SECONDS}, ttl_seconds=SESSION_TTL_SECONDS)
    return token


def get_session(token: str | None) -> dict | None:
    if not token:
        return None
    session = _get_store().get(f"session:{token}")
    if not session:
        return None
    if session["expires_at"] < time.time():
        _get_store().delete(f"session:{token}")
        return None
    return session


def delete_session(token: str | None) -> None:
    if token:
        _get_store().delete(f"session:{token}")
