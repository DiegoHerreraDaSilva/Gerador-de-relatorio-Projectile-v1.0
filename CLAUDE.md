# Project Instructions — Automação de Relatório de Horas

Este arquivo descreve o estado implementado do repositório e as regras para agentes que forem alterá-lo. O `GUIA_EVOLUCAO_GERADOR_PROJECTILE.md` é um plano de evolução futura; não trate suas propostas como funcionalidades já existentes.

## Visão geral

Aplicação interna full stack para:

1. autenticar usuários no Projectile;
2. importar horas por XLSX ou MySQL;
3. revisar e editar relatórios;
4. gerar/enviar XLSX e PDF;
5. acompanhar horas pessoais;
6. acompanhar e diagnosticar KPIs gerenciais;
7. automatizar ingestão de relatórios por Microsoft Graph;
8. editar/traduzir conteúdo com Anthropic.

O MySQL do Projectile é somente lido. Desde a Fundação/Slice 1 do
`GUIA_EVOLUCAO_GERADOR_PROJECTILE.md`, existe um SEGUNDO banco próprio,
`reports_db` (MySQL em container Docker, acessado via SQLAlchemy Core +
Alembic), que persiste histórico/versionamento de cada geração de relatório
— ver seção "Persistência de relatórios (reports_db)". A persistência
gerencial local continua em `backend/data/management_kpi.json` e as guias
do frontend em `localStorage`; nenhum dos dois foi migrado pro banco novo
ainda.

## Stack atual

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI 0.141.1, Uvicorn 0.49 |
| XLSX/PDF | openpyxl para leitura, ZIP/XML para escrita, ReportLab, pypdf |
| Banco Projectile | MySQL/PyMySQL (só leitura); senha via Windows Credential Manager/keyring |
| Banco reports_db | MySQL em Docker; SQLAlchemy Core + Alembic; senha via keyring |
| Frontend | React 18, TypeScript 5.6, Vite 7.3.6, Zustand 4, immer 10 |
| IA | Anthropic SDK + truststore |
| E-mail | Microsoft Graph via MSAL |
| Testes | pytest + Vitest |

## Regras que não podem ser quebradas

### Geração XLSX

- **Nunca use `openpyxl.save()` no caminho de geração.** Ele pode remover `xl/drawings` e `xl/media` do template.
- `backend/app/generator.py` copia o template e altera ZIP/XML diretamente.
- `backend/templates/relatorio_final_template.xlsx` é a fonte da verdade e não deve ser recriado por código.
- Mantenha os cálculos equivalentes entre `frontend/src/utils/calc.ts`, `generator.py` e `pdf_generator.py`.
- Preserve os metadados/markers de identidade, total e `pacote_scope`; `email_ingest.py` depende deles.

### Identidade e autorização

- `/parse-db` e `/my-hours` sempre usam a identidade da sessão; nunca aceite `employee_id`/nome vindo do cliente para consultar outra pessoa.
- `/parse-db-client` e todas as rotas `/management/*` exigem `require_manager`.
- `/translate-activities` exige `require_translate_access`.
- Não exponha distinção entre usuário inexistente e senha incorreta.
- Não habilite Swagger/ReDoc/OpenAPI sem uma decisão explícita de segurança.

### Estado do frontend

- `useReportStore.ts` é a fonte de verdade da guia ativa.
- Pacotes, grupos e atividades são identificados por `id`, nunca por índice persistente.
- **Chat de IA usa `id` estável de grupo/atividade** (Fase 8) — `ChatGroup`/`ChatActivity` (`api/routers/chat.py`) exigem `id`; `chat_ops.py` localiza o alvo das operações por `groupId`/`activityId`, nunca por nome/descrição. `add_group`/`add_activity` geram `id` novo no backend (`uuid4()`), que o frontend só precisa aceitar (`applyChatState` casa por `id`, não mais por nome+índice).
- `enableMapSet()` é obrigatório porque o estado contém `Set`.
- A pilha de undo é global à guia durante a sessão, mas não vai para o `localStorage`.
- `useReportTabsStore.ts` serializa cada guia, faz autosave com debounce e restaura no boot.
- Ao trocar ou fechar guias, salve o bundle atual antes de carregar o próximo.
- `resetForNewImport()`/`resetParsedState()` devem limpar o preview e o estado transitório sem deixar dados da importação anterior.

### Preview

- O preview representa uma folha impressa e permanece branco nos temas claro e escuro.
- Inputs `.pv-input` são transparentes; preserve chaves React estáveis para não perder foco.
- Nunca substitua conteúdo editável via `innerHTML`. React já escapa texto; updates pontuais devem usar estado ou `textContent` seguro.
- Drag-and-drop, seleção múltipla, split view e fullscreen são comportamentos existentes; não os remova em refactors visuais.

### Persistência de relatórios (reports_db)

- **Fail-open por padrão, decisão deliberada**: se `reports_db` estiver fora
  do ar ou qualquer chamada de persistência falhar, `services/report_persistence.py`
  loga e devolve `None`/não faz nada — `/generate` e `/send-report` NUNCA
  ficam bloqueados por causa dessa infraestrutura secundária. Não troque
  isso por fail-closed sem uma decisão explícita do usuário (foi avaliado e
  descartado — ver plano de implementação no histórico do projeto).
- `REPORTS_DB_ENABLED=false` desliga a persistência deliberadamente
  (diferente do fail-open, que cobre falha inesperada) — reproduz o `.xlsx`/`.pdf`
  byte a byte em relação a `true` (verificado). Use pra isolar "o deploy é
  seguro" de "a persistência funciona em produção", ou pra desligar rápido
  sem reverter código.
- O snapshot salvo é **o payload exato recebido por `/generate`**, não uma
  reconsulta ao Projectile — o backend não vê mais os dados brutos nesse
  ponto (o payload já passou por edição/chat/merge no frontend desde o
  `/parse-db`). Não tente "melhorar" isso reconsultando o Projectile dentro
  de `report_persistence.py`.
- Identidade de um `report` = hash de `(report_number, scope,
  competence_label)`, sem o usuário que gerou — `/parse-db-client` (gerente)
  pode gerar o mesmo relatório de projeto em dias diferentes; incluir o
  usuário fragmentaria isso incorretamente em relatórios novos. Risco
  residual aceito: dois relatórios pessoais com o mesmo texto de código por
  coincidência colidem como versões do mesmo `report`.
- `reports.current_version_id` não tem FK (dependência circular com
  `report_versions`) — integridade garantida pela aplicação, sempre escrita
  na mesma transação que cria a versão.
- Versionamento seguro sob concorrência: lock de `reports.id` (`SELECT ...
  FOR UPDATE` ou o próprio `INSERT` até commit) serializa duas requisições
  concorrentes pro mesmo `identity_hash`; `UNIQUE(report_id, version_number)`
  é a segunda barreira. Não calcule `version_number` fora dessa transação.
- Artifacts ficam em `backend/data/report_artifacts/<report_id>/<generation_id>.<fmt>`
  (cópia própria, fora de `tempfile.gettempdir()` — o caminho original é
  apagado segundos após o download).

## Arquitetura do frontend

`App.tsx` controla cinco views sem React Router:

```ts
type AppView = "report" | "dashboard" | "management" | "diagnostics" | "history";
```

- `Sidebar.tsx`: logo, navegação, guias abertas, tema, usuário e logout. É recolhível no desktop e drawer no mobile.
- `PageHeader.tsx`: cabeçalhos internos reutilizáveis.
- `FileUpload.tsx`: fluxo de fonte, escopo, organização, período e seleção de cliente/projetos.
- `RadioCard.tsx` e `StepCard.tsx`: controles visuais do fluxo de importação.
- `Preview/`: revisão do relatório.
- `GenerateFooter.tsx`: formatos, nome, performance, download e abertura do modal de envio.
- `MyHoursDashboard.tsx`: dashboard pessoal.
- `ManagementPanel.tsx`: KPIs e gráficos gerenciais.
- `DiagnosticsPanel.tsx`: amostras, duplicidades e mensagens ignoradas.
- `HistoryPanel.tsx`: histórico de relatórios (`reports_db`) — lista, versões, gerações, artifacts e auditoria. Visível pra todo mundo (não só gerente); backend filtra pra só os próprios relatórios de quem não é gerente.

Não reintroduza o antigo `Header.tsx` nem o stepper vertical; ambos foram substituídos pela sidebar e pelos blocos horizontais.

### Fluxo de importação

- `importSource = "db"`: buscar no Projectile.
- `importSource = "file"`: arquivo local.
- Busca do próprio usuário suporta `single` (consolidado) e `multi` (por pacote).
- Busca por cliente aparece somente para gerente e suporta `projeto` ou `pacote`, com múltiplos projetos.
- Período pode ser mês único ou intervalo. A UI atual mantém o mesmo ano nos dois extremos; o backend também aceita labels que cruzam ano.
- As opções de ano vêm de `getReportYearOptions()` e cobrem de 2008 ao ano corrente, em ordem decrescente.
- Use `frontend/src/utils/period.ts` para montar/interpretar labels. O backend usa `parse_month_label`/`parse_period_label`.
- Ao alterar fonte, modo, cliente, projeto ou período, invalide apenas os dados dependentes necessários.

### Tema e layout

- Tokens globais ficam em `frontend/src/styles/index.css`.
- Tema escuro usa azul-noite (`--bg`, `--surface`, `--surface-2`); não volte às superfícies cinza neutro.
- Tema claro fica em `:root[data-theme="light"]`.
- Sidebar usa `position: sticky` e altura de viewport. A reserva do footer fixo pertence a `.app-main`, não ao `body`; mover essa reserva para fora do `.app-shell` faz a sidebar subir no fim da página.
- `ManagementFilters` é compartilhado entre Gerência e Diagnóstico.
- Os três KPIs principais usam grade de três colunas, mesma altura e tabelas sem scrollbar horizontal. Preserve breakpoints de duas/uma coluna.
- O gráfico de evolução deve manter os meses em ordem cronológica da esquerda para a direita.

## Stores

| Store | Responsabilidade |
|---|---|
| `useAuthStore.ts` | sessão, login/logout, gerente e tradução |
| `useReportStore.ts` | relatório ativo, header, importação, edição, undo, drag e split |
| `useReportTabsStore.ts` | múltiplas guias e persistência local |
| `useMyHoursStore.ts` | dashboard pessoal e filtros |
| `useManagementStore.ts` | KPIs, filtros, fechados e status de envio |
| `useDiagnosticsStore.ts` | amostras e projetos do diagnóstico |
| `useHistoryStore.ts` | lista/paginação/filtros de `GET /reports`, detalhe do relatório selecionado (versões, gerações, artifacts, auditoria) e detalhe de uma versão |

## Backend

### Módulos

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | monta o `FastAPI`, middlewares, `include_router` de cada domínio e static mount — **não tem endpoint nenhum desde a Fase 5**, ver "API — routers" abaixo |
| `auth.py` | login Projectile, rate limit e sessões em memória |
| `db_credentials.py` | leitura da senha no Windows Credential Manager/keyring |
| `projectile_db.py` | pool de conexões (`DBUtils.PooledDB`), queries e agrupamento |
| `parser.py` | parser do export XLSX e `RowIssue` |
| `generator.py` | geração XLSX, feriados e dias úteis |
| `pdf_generator.py` | PDF A4 e metadados |
| `hours_analytics.py` | contrato, baseline, lacunas, outliers e séries |
| `management.py` | KPIs, cache, amostras, fechados e JSON local |
| `email_ingest.py` | Graph, anexos, matching, leitura e envio de e-mail |
| `chatbot.py` | chamadas Anthropic |
| `chat_ops.py` | schema/aplicação das operações do chat |
| `translate_ops.py` | contrato de tradução |
| `core/config.py` | `Settings` (pydantic-settings) — só `reports_db_*`/`projectile_sys_client_id`/`projectile_db_pool_size` por ora, não todas as env vars |
| `db/reports_db.py` | engine SQLAlchemy do `reports_db` (pool de verdade, `connect_timeout` curto) |
| `db/reports_schema.py` | `Table`/`MetaData` das 7 tabelas do histórico (SQLAlchemy Core, não ORM); alvo do `alembic revision --autogenerate` |
| `services/snapshot.py` | funções puras: canonical JSON, hash de dado/identidade, parse de competência |
| `services/report_persistence.py` | `begin_generation`/`finish_generation_success`/`finish_generation_failure`/`reconcile_orphaned_generations`, `GenerationGuard` — sempre fail-open |
| `services/audit.py` | `record_event()` — trilha de auditoria em `audit_log`, sempre fail-open |
| `services/report_queries.py` | leituras pro histórico (`GET /reports/*`) — **não** é fail-open: falha vira 502 (a única função do endpoint é ler) |

### API — routers (Fase 5)

`main.py` só monta o app; toda rota vive em `api/routers/*.py`, uma por domínio:

| Router | Rotas | Modelos Pydantic |
|---|---|---|
| `api/routers/auth.py` | `/auth/login`, `/auth/me`, `/auth/logout` | `LoginRequest` |
| `api/routers/parsing.py` | `/parse`, `/parse-db`, `/parse-db-client` | `ParseDbRequest`, `ParseDbClientRequest`; hardening de upload (`_stream_upload_to_tempfile`, `_reject_if_oversized_uncompressed`) |
| `api/routers/my_hours.py` | `/my-hours` | — |
| `api/routers/management.py` | `/management/*` (15 rotas) | `ManualSampleCreatePayload`, `SampleUpdatePayload`, `ManualEntryPayload`. **Nome igual ao módulo `backend/app/management.py`** (regra de negócio) de propósito — são caminhos de import diferentes (`api.routers.management` vs `management`), sempre importe com alias quando os dois aparecem juntos (`main.py` faz `from .api.routers import management as management_router`) |
| `api/routers/generation.py` | `/generate`, `/send-report` | `HeaderPayload`, `GroupPayload`, `ActivityPayload`, `ReportPackagePayload`, `GeneratePayload`, `SendReportPayload` — `OUTPUT_DIR` também vive aqui |
| `api/routers/history.py` | `/reports/*`, `/artifacts/{id}/download` | — |
| `api/routers/chat.py` | `/chat`, `/translate-activities` | `ChatState`, `ChatGroup`, `ChatActivity`, `ChatPackage`, `ChatRequest`, `ChatResponse`, `TranslatePayload` |

Compartilhado entre routers: `api/dependencies.py` (`require_session`/`require_manager`/`require_translate_access`/`SESSION_COOKIE`), `api/errors.py` (`log_and_generic_error`/`GENERIC_*_ERROR`), `api/shared.py` (`resolve_month_range`, `build_parse_response`).

**Gotcha de teste**: `require_manager`/`require_translate_access` (em `api/dependencies.py`) e `_require_report_access` (em `api/routers/history.py`) leem `management.MANAGEMENT_PANEL_LOGINS`/`management.TRANSLATE_ALLOWED_LOGINS` como **atributo do módulo** (`from .. import management` + `management.MANAGEMENT_PANEL_LOGINS`), nunca `from ..management import MANAGEMENT_PANEL_LOGINS` — um `from import` copiaria o `set` pro namespace local NA HORA DO IMPORT, e `monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", ...)` (o padrão usado nos testes) não afetaria essa cópia. Mesma categoria de bug já encontrada uma vez com `get_engine` em `report_persistence.py`/`report_queries.py`/`audit.py` (três bindings independentes da mesma função) — ao adicionar um novo consumidor de estado "testável por monkeypatch", sempre referencie via atributo do módulo definidor, nunca via `from import`.

**Adicionar uma rota nova**: crie/edite o router do domínio certo em `api/routers/`, nunca em `main.py` diretamente. Se o domínio for novo, crie o arquivo, defina `router = APIRouter()`, e adicione `app.include_router(seu_router.router)` em `main.py`.

### Banco do Projectile

- Importe o backend como `backend.app.*`; use imports relativos dentro do pacote.
- `projectile_db._get_connection()` empresta uma conexão de um pool de verdade (`DBUtils.PooledDB`, `autocommit=True`, `ping=1` reconecta sozinho ao pegar do cache); tamanho fixo em `Settings.projectile_db_pool_size` (padrão 5 — pequeno de propósito, sem staging pra medir `max_connections` real do MySQL legado).
- Toda função `fetch_*` usa `_borrowed_connection(conn)`: se `conn` foi passada pelo chamador (reaproveitar em várias queries do mesmo request), NÃO devolve ao pool — quem abriu é dono. Se `conn` é `None`, empresta e devolve sozinha ao final (`finally: borrowed.close()`).
- `open_connection()` (usada por `auth.verify_projectile_login` e `management.compute_monthly_kpis` pra reaproveitar uma conexão em várias queries) empresta do pool sem devolver — o CHAMADOR é responsável por `conn.close()` num `try/finally` (devolve ao pool, não fecha de verdade).
- Queries relevantes devem filtrar `sysClientId` para usar os índices compostos do banco legado.
- Não mantenha transação de leitura aberta numa conexão emprestada além do necessário — outra chamada pode estar esperando na fila (`blocking=True`) por uma conexão do pool.
- Preserve decoding duplo de entidades HTML onde já aplicado; existem textos `&amp;#...` no banco.
- Horas `<= 0` não entram nos agrupamentos.
- Observação sem separador vai para o grupo geral no fluxo do banco e gera `RowIssue` quando há dado real incompleto.

### Parser XLSX

- Cabeçalho: `Dados`, `Horário`, `Hs`.
- Observação: primeiro `-` ou `_` separa grupo/atividade.
- `_extract_package_key()` só divide hífen com espaço em pelo menos um lado; não quebre nomes como `Para-barro`.
- Linhas em branco, subtotais e assinaturas devem continuar silenciosas.
- Upload: máximo 25 MB e 200 MB descomprimidos.

### Analytics e calendário

- Geração de relatório usa feriados nacionais e dias úteis do período do relatório.
- Dashboard pessoal acrescenta feriado estadual de SP, municipal de Santo André conforme filial e pontes.
- Somente contrato explícito autoriza percentual de aderência; histórico empírico é referência informativa.
- Não misture a regra do dashboard pessoal com a geração de relatório sem uma decisão explícita.

### Persistência gerencial

- Arquivo: `backend/data/management_kpi.json` (ignorado pelo Git).
- Escritas são protegidas por `RLock`; preserve escrita atômica/consistência.
- Cache de horas gerenciais: 15 minutos por intervalo.
- `pacote_scope = None` significa projeto inteiro; lista significa pacotes específicos.
- Amostras automáticas duplicadas não entram duas vezes no faturado; amostras manuais têm regras próprias.
- Fechamento de cliente/projeto é permanente e prevalece sobre status calculado.

### E-mail

- O polling inicia no startup e só trabalha quando `AZURE_CLIENT_ID` está configurado.
- Idempotência é por `message_id`.
- Anexos aceitos: `.xlsx` e `.pdf`, até 25 MB e 200 MB descomprimidos para XLSX.
- Quando XLSX e PDF têm o mesmo stem, prefira XLSX para não contar duas vezes.
- `/send-report` envia como o e-mail do usuário autenticado e inclui a caixa do agente conforme configuração Graph.
- Não registre tokens Graph, anexos ou credenciais em logs.

## Contratos de API

Não altere nomes/casing sem migração coordenada.

- `/parse`: multipart `file`, `mode=single|multi` → `{packages, issues}`.
- `/parse-db`: `{month_label, mode}` → mesmo formato de `/parse`; identidade da sessão.
- `/parse-db-client`: `{project_ids, month_label, mode=projeto|pacote}`; gerente.
- `/my-hours?period=current_month|last_3|last_6|last_12`.
- `/generate`: `GeneratePayload` em snake_case; arquivo direto para 1 pacote/1 formato, ZIP nos demais casos. Headers `X-Report-Id`/`X-Report-Version-Id`/`X-Report-Version-Number` (caso único) ou `X-Report-Ids` (zip, `report_id:version_id` separados por vírgula) são **aditivos** — ausentes se a persistência em `reports_db` falhou (fail-open) ou está desligada; nunca confie na presença deles.
- `/send-report`: mesmos pacotes + destinatário/assunto/mensagem/formatos; nunca ZIPa anexos. Mesma persistência fail-open de `/generate` (`created_from="send_report_endpoint"`), sem headers extra na resposta (que é só `{"ok": true}`).
- `/chat`: `ChatState` em camelCase e histórico `{role,text}`; aplica operações atomicamente.
- `/translate-activities`: `{items:[{id,text}], target_language: en|de}`.
- `/management/kpis`: filtros repetíveis `cost_centers`, `clients`, `projects`, `packages`, `selected_months`, `persons`.
- `/management/kpis/samples`: CRUD de amostras; PATCH usa `exclude_unset` para distinguir `pacote_scope` ausente de `None`.
- `GET /reports`, `/reports/{id}`, `/reports/{id}/versions[/{version_id}]`, `/reports/{id}/generations`, `/reports/{id}/artifacts`, `/reports/{id}/audit`, `GET /artifacts/{id}/download`: histórico de `reports_db` (Fase 2+4). Autorização: quem criou o relatório ou gerente (`_require_report_access`, mesmo princípio de `/parse-db`/`/my-hours` — nunca expõe dado de uma pessoa pra outra sem ser gerente). Paginação `page`/`page_size` (máx. 100) em `{items, page, page_size, total}`. Download registra `artifact_downloaded` em `audit_log`.

`Field(..., allow_inf_nan=False)` e `_sanitize_nonfinite` evitam `NaN`/`Infinity`. Preserve esse comportamento em novos campos numéricos.

## Variáveis de ambiente

Fonte: `.env.example`.

- Projectile: `PROJECTILE_DB_HOST`, `PROJECTILE_DB_PORT`, `PROJECTILE_DB_USER`, `PROJECTILE_DB_NAME`; senha no keyring `projectile_mysql`. `PROJECTILE_SYS_CLIENT_ID` (default `"0"`) e `PROJECTILE_DB_POOL_SIZE` (default `5`, tamanho do pool de conexões — ver `projectile_db.py`) vêm de `core/config.Settings`.
- reports_db: `REPORTS_DB_HOST`, `REPORTS_DB_PORT`, `REPORTS_DB_USER`, `REPORTS_DB_NAME`; senha no keyring `reports_mysql`. `REPORTS_DB_ENABLED` (default `true`) desliga a persistência sem reverter código. `REPORTS_MYSQL_ROOT_PASSWORD`/`REPORTS_MYSQL_APP_PASSWORD` são só bootstrap do `docker-compose.yml` (primeira subida do container) — nunca lidos em runtime pela aplicação.
- Permissões: `MANAGEMENT_PANEL_LOGINS`, `TRANSLATE_ALLOWED_LOGINS`.
- Anthropic: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`.
- Graph: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `GRAPH_MAILBOX`, `ALBERTO_EMAIL`, `EMAIL_POLL_INTERVAL_SECONDS`.
- Arquivo: `REPORT_PROTECTION_PASSWORD`.

`load_dotenv()` precisa continuar antes dos imports de módulos que leem env no import (`management.py`). Reinicie o backend depois de mudar allowlists. `backend/alembic/env.py` roda como processo separado e chama `load_dotenv()` por conta própria.

## Comandos obrigatórios

```bash
# instalar
pip install -r backend/requirements-dev.txt
npm --prefix frontend install

# reports_db (uma vez, ou depois de recriar o volume Docker)
docker compose up -d reports-mysql
alembic upgrade head
python -c "import getpass, keyring; keyring.set_password('reports_mysql', 'reports_app', getpass.getpass())"

# backend
python -m pytest backend/tests -v

# frontend
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build

# execução
python -m uvicorn backend.app.main:app --reload --port 8011
npm --prefix frontend run dev
```

O script `frontend:lint` executa `tsc --noEmit`; não há ESLint/Prettier configurado.

Testes marcados `@pytest.mark.reports_db` (persistência em `reports_db`)
pulam automaticamente (`pytest.skip`) se `REPORTS_DB_HOST` não estiver
setado — a suíte local roda sem exigir Docker por padrão; rodam de verdade
só com o container de pé (schema de teste separado, `reports_db_test`, ver
`backend/tests/conftest.py:reports_db_engine`).

### Baseline atual de testes

Em 2026-09-22:

- backend: 274 testes coletados (211 + 62 novos de `reports_db`/snapshot/histórico/auditoria/upload/chat, 1 skip pré-existente);
- frontend: 134 testes em 10 arquivos;
- build: `tsc -b && vite build`.

Não atualize esses números sem executar as suítes. Falha `spawn EPERM` de Vitest/Vite no sandbox Windows indica bloqueio ao subprocesso do esbuild; repita fora do sandbox antes de classificar como falha do código.

## Vite, static files e cache

- `frontend/vite.config.ts` não define `root`; execute comandos a partir de `frontend/` ou use `npm --prefix frontend`.
- Proxy atual: `/auth`, `/parse`, `/parse-db*`, `/generate`, `/chat`, `/reports`, `/artifacts` → `:8011`.
- `/management/*`, `/my-hours`, `/send-report` e `/translate-activities` não estão no proxy atual. Para testar tudo sem alterar config, use o build servido pelo FastAPI.
- Logos e assets públicos devem ficar em `frontend/public/`.
- `NoCacheStaticFiles`: `assets/*` recebe cache immutable de um ano; demais arquivos recebem `no-store`.
- `frontend/dist` é gerado e ignorado pelo Git.

## CI e deploy

- `.github/workflows/ci.yml` roda em todo push para qualquer branch e em PR para `main`.
- Backend: sobe um serviço `mysql` (schema `reports_db_test`, usuário `reports_app`), instala `requirements-dev.txt`, roda `alembic upgrade head` (senha via `REPORTS_DB_TEST_PASSWORD`, não keyring — CI não tem Windows Credential Manager) e roda pytest.
- Frontend: Node 20, `npm ci`, Vitest e build.
- Não há deploy automático.
- `scripts/atualizar-servidor.bat` atualiza `main`, instala dependências, sobe `reports-mysql` via Docker + `alembic upgrade head` (nunca reinicia o backend se a migration falhar), builda e reinicia via NSSM quando configurado.

## Git e escopo

- Branch principal: `main`, acompanhando `origin/main`.
- Só faça commit/push quando o usuário pedir explicitamente.
- Para mudanças solicitadas, prefira commits lógicos com Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- Preserve alterações locais não relacionadas; não use reset destrutivo.
- Nunca comite `.env`, `backend/data/`, `frontend/dist/`, exports reais do Projectile ou credenciais.
- Antes de commit: `git diff --check`, testes relevantes, typecheck e build conforme o escopo.

## Onde mexer

| Objetivo | Arquivo principal |
|---|---|
| Importação/etapas | `frontend/src/components/FileUpload.tsx` |
| Estado do relatório | `frontend/src/store/useReportStore.ts` |
| Guias abertas | `frontend/src/store/useReportTabsStore.ts` |
| Sidebar/tema/navegação | `frontend/src/components/Sidebar.tsx`, `styles/index.css` |
| Preview | `frontend/src/components/Preview/` |
| Geração/download | `GenerateFooter.tsx`, `backend/app/api/routers/generation.py`, geradores |
| Dashboard pessoal | `MyHoursDashboard.tsx`, `useMyHoursStore.ts`, `hours_analytics.py` |
| KPIs gerenciais | `ManagementPanel.tsx`, `useManagementStore.ts`, `management.py` (regra), `api/routers/management.py` (rota) |
| Diagnóstico | `DiagnosticsPanel.tsx`, `useDiagnosticsStore.ts` |
| Parser XLSX | `backend/app/parser.py` |
| Queries Projectile | `backend/app/projectile_db.py` |
| E-mail | `backend/app/email_ingest.py`, `SendReportModal.tsx`, `api/routers/management.py` (`/management/kpis/check-emails`) |
| Chat/tradução (IDs estáveis desde a Fase 8) | `api/routers/chat.py`, `chatbot.py`, `chat_ops.py`, `translate_ops.py`, `Chat.tsx`, `useReportStore.applyChatState` |
| Proxy dev | `frontend/vite.config.ts` |
| Documentação de uso | `README.md` |
| Persistência de relatórios (histórico/versão) | `backend/app/services/report_persistence.py`, integração em `api/routers/generation.py` (`generate_endpoint`/`send_report_endpoint`) |
| Tela de histórico | `frontend/src/components/HistoryPanel.tsx`, `useHistoryStore.ts`, `utils/historyFormat.ts` |
| Schema do `reports_db` | `backend/app/db/reports_schema.py` + nova migration em `backend/alembic/versions/` |
| Config central (`reports_db`/`sysClientId`) | `backend/app/core/config.py` |
| Adicionar rota API nova | `backend/app/api/routers/<domínio>.py` (nunca `main.py` diretamente) — ver "API — routers" |
| Autenticação/sessão | `backend/app/auth.py` (regra), `api/routers/auth.py` (rota), `api/dependencies.py` (`require_session`/`require_manager`) |

## Checklist antes de concluir

- O comportamento solicitado funciona nos cinco contextos de navegação?
- Estado de uma guia não vazou para outra?
- Tema claro e escuro continuam legíveis?
- Sidebar expandida, recolhida e mobile continuam utilizáveis?
- Não foi alterado contrato API sem atualizar frontend, testes, README e este arquivo?
- XLSX e PDF mantêm os mesmos totais?
- Testes relevantes, typecheck e build passaram?
- Nenhum segredo ou dado real entrou no diff?
