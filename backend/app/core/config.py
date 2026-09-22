"""Configuração central, ainda pequena de propósito: só cobre o que o
`reports_db` (persistência de relatórios) introduz, mais o `sysClientId` do
Projectile que já existia hardcoded. As dezenas de outras variáveis de
ambiente do projeto (`ANTHROPIC_*`, `AZURE_*`, `PROJECTILE_DB_*`, etc.)
continuam lidas via `os.environ` direto no ponto de uso, como sempre foram —
migrá-las todas pra cá é trabalho de uma refatoração maior, não desta
mudança (ver GUIA_EVOLUCAO_GERADOR_PROJECTILE.md, Fase 6)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": o .env real já tem várias outras variáveis
    # (ANTHROPIC_*, AZURE_*, ...) que este Settings não modela — sem isso,
    # pydantic-settings rejeitaria o arquivo inteiro por causa delas.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Projectile — sysClientId desta instalação on-premise (fixo, nunca muda
    # na prática; só existe como variável pra não ficar hardcoded no código,
    # ver projectile_db.py). Default idêntico ao valor hardcoded anterior.
    projectile_sys_client_id: str = "0"

    # Tamanho do pool de conexões pro MySQL do Projectile (ver
    # projectile_db.py) — pequeno de propósito: esse MySQL é legado,
    # on-premise, sem staging pra medir seu `max_connections` real, então o
    # padrão fica bem abaixo de qualquer default razoável (tipicamente 151+).
    projectile_db_pool_size: int = 5

    # reports_db — banco próprio de histórico de relatórios (container
    # Docker, ver docker-compose.yml). A senha NUNCA vem daqui — fica no
    # Windows Credential Manager via keyring (db_credentials.py), mesmo
    # padrão já usado pro Projectile.
    reports_db_host: str = "127.0.0.1"
    reports_db_port: int = 3307
    reports_db_name: str = "reports_db"
    reports_db_user: str = "reports_app"

    # Desligamento deliberado da persistência (não confundir com a falha
    # inesperada do reports_db, que já é fail-open por padrão) — útil pra
    # isolar "o deploy do código novo é seguro" de "a persistência funciona
    # em produção" em dois passos verificáveis, ou pra desligar rápido sem
    # precisar reverter/reduplicar deploy se o banco novo der problema.
    reports_db_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
