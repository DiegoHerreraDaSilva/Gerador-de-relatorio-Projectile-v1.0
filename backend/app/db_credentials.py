"""Lê a senha do MySQL do Projectile do Windows Credential Manager (via
`keyring`) em vez de guardá-la em texto puro no `.env` — a senha nunca fica
num arquivo do projeto, só no cofre criptografado do Windows, atrelado à
conta do usuário que está rodando o backend.

Guardar a senha uma vez (rode no terminal, não fica no histórico do shell):
    python -c "import getpass, keyring; keyring.set_password('projectile_mysql', 'dashboards.board', getpass.getpass())"
"""
from __future__ import annotations

import keyring

_SERVICE_NAME = "projectile_mysql"


class DbCredentialsError(RuntimeError):
    """Nenhuma senha guardada no Credential Manager pra esse usuário."""


def get_projectile_db_password(username: str) -> str:
    password = keyring.get_password(_SERVICE_NAME, username)
    if not password:
        raise DbCredentialsError(
            f'Nenhuma senha guardada pro usuário "{username}" no Windows Credential Manager. '
            "Rode: python -c \"import getpass, keyring; keyring.set_password('projectile_mysql', "
            f"'{username}', getpass.getpass())\""
        )
    return password
