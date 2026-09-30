"""Senhas de MySQL: variável de ambiente (containers/Linux) ou Windows
Credential Manager (via `keyring`) — a senha nunca fica em texto puro num
arquivo do projeto no caminho do Windows, só no cofre criptografado da
conta que roda o backend. Usado tanto pro Projectile quanto pro reports_db
(dois bancos, duas entradas de keyring, nomes de serviço diferentes).

A ORDEM importa: `PROJECTILE_DB_PASSWORD`/`REPORTS_DB_PASSWORD` no ambiente
vêm primeiro (é o caminho dos containers do `docker-compose.prod.yml`, onde
não existe Credential Manager do Windows); sem elas, cai no keyring.

Guardar a senha do Projectile uma vez (rode no terminal, não fica no
histórico do shell):
    python -c "import getpass, keyring; keyring.set_password('projectile_mysql', 'dashboards.board', getpass.getpass())"

Guardar a senha do reports_db (mesma senha usada em
REPORTS_MYSQL_APP_PASSWORD na primeira subida do container, ver
docker-compose.yml):
    python -c "import getpass, keyring; keyring.set_password('reports_mysql', 'reports_app', getpass.getpass())"
"""

from __future__ import annotations

import os

import keyring

_PROJECTILE_SERVICE_NAME = "projectile_mysql"
_REPORTS_SERVICE_NAME = "reports_mysql"


class DbCredentialsError(RuntimeError):
    """Nenhuma senha no ambiente nem guardada no Credential Manager pra esse usuário."""


def _resolve_password(env_var: str, service_name: str, username: str) -> str:
    password = os.environ.get(env_var)
    if password:
        return password
    try:
        password = keyring.get_password(service_name, username)
    except Exception as e:  # NoKeyringError em Linux sem backend, cofre bloqueado etc.
        raise DbCredentialsError(f"Não consegui ler a senha no Credential Manager ({type(e).__name__}). Em container, defina {env_var} no ambiente.") from e
    if not password:
        raise DbCredentialsError(
            f'Nenhuma senha guardada pro usuário "{username}" no Windows Credential Manager '
            f"(ou {env_var} vazia no ambiente). "
            "Rode: python -c \"import getpass, keyring; keyring.set_password('"
            f"{service_name}', '{username}', getpass.getpass())\""
        )
    return password


def get_projectile_db_password(username: str) -> str:
    return _resolve_password("PROJECTILE_DB_PASSWORD", _PROJECTILE_SERVICE_NAME, username)


def get_reports_db_password(username: str) -> str:
    return _resolve_password("REPORTS_DB_PASSWORD", _REPORTS_SERVICE_NAME, username)
