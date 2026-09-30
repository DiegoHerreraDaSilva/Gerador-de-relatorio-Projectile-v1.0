"""Configuração central, ainda pequena de propósito: só cobre o que o
`reports_db` (persistência de relatórios) introduz, mais o `sysClientId` do
Projectile que já existia hardcoded. As dezenas de outras variáveis de
ambiente do projeto (`ANTHROPIC_*`, `AZURE_*`, `PROJECTILE_DB_*`, etc.)
continuam lidas via `os.environ` direto no ponto de uso, como sempre foram —
migrá-las todas pra cá é trabalho de uma refatoração maior, não desta
mudança."""

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

    # Chat analítico (aba "Chat analítico", só gerente) — ver backend/app/analytics/.
    # Jev (TypeSafe AI) classifica a pergunta pela API oficial da TypeSafe
    # (TYPESAFE_API_KEY). Sem chave, o Claude classifica.
    typesafe_api_key: str = ""
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = 3.0
    # Confiança mínima do Jev, senão o Claude interpreta. Vale pra rota e pra
    # toda ESCOLHA feita (intent, período, cliente...); "nenhum" tem limiar
    # próprio, mais baixo. Calibrado em 2026-09-24 com 24 perguntas reais pelo
    # Jev (metade no meio de conversa): o Jev acerta 22/24, mas a
    # confiança dele é baixa mesmo quando acerta (métrica certa com 0,5–0,7).
    # 0,60/0,40 → 20 aceitas (1 com formato diferente, número certo), 4 pro
    # Claude; 0,80/0,60 → 0 erradas, mas 11 pro Claude.
    jev_min_confidence: float = 0.60
    jev_min_confidence_none: float = 0.40
    # Chave de emergência do agendador da geração automática (`AUTO_GENERATION_ENABLED=false`
    # desliga o loop sem reverter código). O liga/desliga do dia a dia é do gerente,
    # no "Padrão geral" (`schedule_enabled`); este só existe pra parar tudo por fora.
    auto_generation_enabled: bool = True
    # Modelo do chat analítico — separado de ANTHROPIC_MODEL (chat de edição
    # do relatório). Haiku: as tarefas são curtas e a latência importa mais.
    analytics_chat_model: str = "claude-haiku-4-5-20251001"
    analytics_chat_max_rows: int = 1000
    # janela do chat analítico = a do Painel de Gerência (12 meses) — mesmas
    # datas, mesmo cache de horas; decisão do usuário em 2026-09-24
    analytics_chat_max_months: int = 12
    # tamanho máximo (JSON) do resultado agregado mandado pro Claude
    analytics_chat_max_claude_payload_bytes: int = 20_000

    # Allowlists de acesso (ver core/authz.py). CSV de logins, normalizados
    # em minúsculas; fallback por papel aplicado no authz (gerente/tradução
    # têm fallback "dherrera", coordenador NÃO tem — vazio = nenhum).
    management_panel_logins: str = ""
    coordinator_logins: str = ""
    translate_allowed_logins: str = ""

    # Fase 3 (containers): sessões/rate limit (e a trava de envio) no Redis
    # quando `SESSIONS_BACKEND=redis` — default `memory` preserva dev/testes
    # sem exigir container. `REDIS_URL` é obrigatória nesse modo (falha
    # explícita, nunca cair em memória calado em produção).
    sessions_backend: str = "memory"
    redis_url: str = ""

    # Papel do processo na topologia de containers (docker-compose.prod.yml):
    # "all" = HTTP + background no mesmo processo (NSSM de sempre), "web" =
    # só HTTP, "worker" = só agendador + polling de e-mail (sem HTTP).
    process_role: str = "all"

    # Base dos links de notificação por e-mail (o app não sabe o próprio host).
    app_base_url: str = "http://localhost:8011"

    # Observabilidade (ver core/logging.py e README "Observabilidade"):
    # formato dos logs do processo ("text" legível ou "json" uma linha por
    # evento), limiar do aviso de requisição lenta em ms (0 = loga toda
    # requisição, pra depuração; negativo = desliga) e o DSN do
    # Sentry/GlitchTip self-hosted — vazio desliga o envio de erro pra fora.
    log_format: str = "text"
    slow_request_ms: int = 3000
    sentry_dsn: str = ""
    sentry_environment: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
