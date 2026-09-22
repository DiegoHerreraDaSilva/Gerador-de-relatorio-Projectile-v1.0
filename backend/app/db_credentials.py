"""Lê senhas de MySQL do Windows Credential Manager (via `keyring`) em vez de
guardá-las em texto puro no `.env` — a senha nunca fica num arquivo do
projeto, só no cofre criptografado do Windows, atrelado à conta do usuário
que está rodando o backend. Usado tanto pro Projectile quanto pro reports_db
(dois bancos, duas entradas de keyring, nomes de serviço diferentes).

Guardar a senha do Projectile uma vez (rode no terminal, não fica no
histórico do shell):
    python -c "import getpass, keyring; keyring.set_password('projectile_mysql', 'dashboards.board', getpass.getpass())"

Guardar a senha do reports_db (mesma senha usada em
REPORTS_MYSQL_APP_PASSWORD na primeira subida do container, ver
docker-compose.yml):
    python -c "import getpass, keyring; keyring.set_password('reports_mysql', 'reports_app', getpass.getpass())"
"""
from __future__ import annotations

import keyring

_PROJECTILE_SERVICE_NAME = "projectile_mysql"
_REPORTS_SERVICE_NAME = "reports_mysql"


class DbCredentialsError(RuntimeError):
    """Nenhuma senha guardada no Credential Manager pra esse usuário."""


def get_projectile_db_password(username: str) -> str:
    password = keyring.get_password(_PROJECTILE_SERVICE_NAME, username)
    if not password:
        raise DbCredentialsError(
            f'Nenhuma senha guardada pro usuário "{username}" no Windows Credential Manager. '
            "Rode: python -c \"import getpass, keyring; keyring.set_password('projectile_mysql', "
            f"'{username}', getpass.getpass())\""
        )
    return password


def get_reports_db_password(username: str) -> str:
    password = keyring.get_password(_REPORTS_SERVICE_NAME, username)
    if not password:
        raise DbCredentialsError(
            f'Nenhuma senha guardada pro usuário "{username}" no Windows Credential Manager. '
            "Rode: python -c \"import getpass, keyring; keyring.set_password('reports_mysql', "
            f"'{username}', getpass.getpass())\""
        )
    return password
