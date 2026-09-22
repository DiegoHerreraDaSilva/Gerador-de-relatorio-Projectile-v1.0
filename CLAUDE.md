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

`App.tsx` controla quatro views sem React Router:

```ts
type AppView = "report" | "dashboard" | "management" | "diagnostics";
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

## Backend

### Módulos

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | app FastAPI, modelos, dependências, endpoints e static mount |
| `auth.py` | login Projectile, rate limit e sessões em memória |
| `db_credentials.py` | leitura da senha no Windows Credential Manager/keyring |
| `projectile_db.py` | conexão/reconexão, queries e agrupamento |
| `parser.py` | parser do export XLSX e `RowIssue` |
| `generator.py` | geração XLSX, feriados e dias úteis |
| `pdf_generator.py` | PDF A4 e metadados |
| `hours_analytics.py` | contrato, baseline, lacunas, outliers e séries |
| `management.py` | KPIs, cache, amostras, fechados e JSON local |
| `email_ingest.py` | Graph, anexos, matching, leitura e envio de e-mail |
| `chatbot.py` | chamadas Anthropic |
| `chat_ops.py` | schema/aplicação das operações do chat |
| `translate_ops.py` | contrato de tradução |
| `core/config.py` | `Settings` (pydantic-settings) — só `reports_db_*`/`projectile_sys_client_id` por ora, não todas as env vars |
| `db/reports_db.py` | engine SQLAlchemy do `reports_db` (pool de verdade, `connect_timeout` curto) |
| `db/reports_schema.py` | `Table`/`MetaData` das 7 tabelas do histórico (SQLAlchemy Core, não ORM); alvo do `alembic revision --autogenerate` |
| `services/snapshot.py` | funções puras: canonical JSON, hash de dado/identidade, parse de competência |
| `services/report_persistence.py` | `begin_generation`/`finish_generation_success`/`finish_generation_failure`/`reconcile_orphaned_generations`, `GenerationGuard` — sempre fail-open |

### Banco do Projectile

- Importe o backend como `backend.app.*`; use imports relativos dentro do pacote.
- `projectile_db._get_connection()` reutiliza uma conexão com `ping(reconnect=True)` e `autocommit=True`.
- Queries relevantes devem filtrar `sysClientId` para usar os índices compostos do banco legado.
- Não mantenha transação de leitura aberta numa conexão reutilizada.
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

`Field(..., allow_inf_nan=False)` e `_sanitize_nonfinite` evitam `NaN`/`Infinity`. Preserve esse comportamento em novos campos numéricos.

## Variáveis de ambiente

Fonte: `.env.example`.

- Projectile: `PROJECTILE_DB_HOST`, `PROJECTILE_DB_PORT`, `PROJECTILE_DB_USER`, `PROJECTILE_DB_NAME`; senha no keyring `projectile_mysql`. `PROJECTILE_SYS_CLIENT_ID` (default `"0"`) vem de `core/config.Settings`.
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

- backend: 236 testes coletados (211 + 24 novos de `reports_db`/snapshot, 1 skip pré-existente);
- frontend: 120 testes em 9 arquivos;
- build: `tsc -b && vite build`.

Não atualize esses números sem executar as suítes. Falha `spawn EPERM` de Vitest/Vite no sandbox Windows indica bloqueio ao subprocesso do esbuild; repita fora do sandbox antes de classificar como falha do código.

## Vite, static files e cache

- `frontend/vite.config.ts` não define `root`; execute comandos a partir de `frontend/` ou use `npm --prefix frontend`.
- Proxy atual: `/auth`, `/parse`, `/parse-db*`, `/generate`, `/chat` → `:8011`.
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
| Geração/download | `GenerateFooter.tsx`, `backend/app/main.py`, geradores |
| Dashboard pessoal | `MyHoursDashboard.tsx`, `useMyHoursStore.ts`, `hours_analytics.py` |
| KPIs gerenciais | `ManagementPanel.tsx`, `useManagementStore.ts`, `management.py` |
| Diagnóstico | `DiagnosticsPanel.tsx`, `useDiagnosticsStore.ts` |
| Parser XLSX | `backend/app/parser.py` |
| Queries Projectile | `backend/app/projectile_db.py` |
| E-mail | `backend/app/email_ingest.py`, `SendReportModal.tsx` |
| Chat/tradução | `chatbot.py`, `chat_ops.py`, `translate_ops.py`, `Chat.tsx` |
| Proxy dev | `frontend/vite.config.ts` |
| Documentação de uso | `README.md` |
| Persistência de relatórios (histórico/versão) | `backend/app/services/report_persistence.py`, integração em `main.py` (`generate_endpoint`/`send_report_endpoint`) |
| Schema do `reports_db` | `backend/app/db/reports_schema.py` + nova migration em `backend/alembic/versions/` |
| Config central (`reports_db`/`sysClientId`) | `backend/app/core/config.py` |

## Checklist antes de concluir

- O comportamento solicitado funciona nos quatro contextos de navegação?
- Estado de uma guia não vazou para outra?
- Tema claro e escuro continuam legíveis?
- Sidebar expandida, recolhida e mobile continuam utilizáveis?
- Não foi alterado contrato API sem atualizar frontend, testes, README e este arquivo?
- XLSX e PDF mantêm os mesmos totais?
- Testes relevantes, typecheck e build passaram?
- Nenhum segredo ou dado real entrou no diff?
