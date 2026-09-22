"""Engine SQLAlchemy pro `reports_db` — banco novo, local/dockerizado
(docker-compose.yml), sem o problema de latência de conexão que limita o
pool de `projectile_db.py` a poucas conexões (aquele MySQL legado pode levar
~20s pra conectar sob carga e não tem staging pra medir `max_connections`
real; este é local, novo e sob nosso controle). Por isso aqui o pool pode
ser maior/mais generoso, via `create_engine(pool_size=...)` em vez do
`DBUtils.PooledDB` usado lá.

`get_engine()` é preguiçoso (só conecta no primeiro uso real) — se o
container `reports-mysql` estiver fora do ar, isso NÃO afeta `/parse`,
`/auth/login`, `/my-hours` etc., só o caminho que efetivamente tenta
persistir (ver `services/report_persistence.py`, que é fail-open por
padrão)."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from ..core.config import get_settings
from ..db_credentials import DbCredentialsError, get_reports_db_password


class ReportsDbError(RuntimeError):
    """Falha ao conectar/persistir no reports_db — nunca erro do usuário;
    quem chama trata isso como fail-open (loga e segue sem histórico)."""


# connect_timeout curto de propósito: diferente do Projectile (onde vale a
# pena esperar porque a query em si é o que importa), aqui a persistência é
# só um acompanhamento da geração real do arquivo — não vale a pena travar a
# requisição por muito tempo tentando falar com um banco secundário.
_CONNECT_TIMEOUT_SECONDS = 3


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    try:
        password = get_reports_db_password(settings.reports_db_user)
    except DbCredentialsError as e:
        raise ReportsDbError(str(e)) from e
    url = (
        f"mysql+pymysql://{settings.reports_db_user}:{password}"
        f"@{settings.reports_db_host}:{settings.reports_db_port}/{settings.reports_db_name}"
        "?charset=utf8mb4"
    )
    return create_engine(
        url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
    )
