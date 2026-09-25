# Automação de Relatório de Horas

Aplicação web interna da Schwaben Engineering para transformar apontamentos do Projectile em relatórios de horas padronizados para a Mercedes-Benz. Os dados podem vir de um export `.xlsx` ou diretamente do MySQL do Projectile, ser revisados no navegador e gerar arquivos `.xlsx`, `.pdf` ou `.zip` sem reconstruir manualmente o relatório a cada mês.

Além do gerador, a aplicação reúne:

- dashboard de horas (pessoal, ou de qualquer colaborador de engenharia pra gerente/coordenador);
- painel gerencial de KPIs;
- diagnóstico: status de envio dos relatórios e correção das amostras usadas nos KPIs;
- histórico de relatórios gerados, com versões e auditoria;
- analytics e chat analítico (perguntas em português sobre horas, faturado e envio);
- automação de leitura e envio de relatórios por e-mail via Microsoft Graph;
- edição assistida e tradução via Anthropic.

> O MySQL do Projectile continua sendo a fonte operacional, só leitura. Desde a introdução do histórico de relatórios, a aplicação também mantém um segundo banco próprio, `reports_db` (MySQL em container Docker), que guarda snapshot/versão/artifact de cada geração — ver [Histórico de relatórios (reports_db)](#histórico-de-relatórios-reports_db). Os dados do Painel de Gerência e do Diagnóstico (amostras, entradas manuais, fechados) também vivem no `reports_db`, nas tabelas `mgmt_*` — antes ficavam em `backend/data/management_kpi.json`.

## Fluxos disponíveis

### Gerar relatório de horas

O fluxo é organizado horizontalmente em etapas e oferece duas fontes:

1. **Buscar no Projectile**
   - **Meu usuário:** usa exclusivamente o `employee_id`/nome da sessão autenticada.
   - **Buscar cliente** (gerente ou coordenador): lista clientes com horas no período, permite escolher um cliente e selecionar múltiplos projetos.
   - Período de **mês único** ou **múltiplos meses**.
   - A seleção de ano vai de 2008 até o ano corrente, em ordem decrescente.
   - Organização consolidada ou separada:
     - usuário: relatório consolidado ou um por pacote;
     - cliente: um por projeto ou um por pacote.
2. **Arquivo do computador**
   - recebe o export `.xlsx` do Projectile;
   - relatório consolidado ou um por pacote de trabalho.

Depois da importação, o usuário pode:

- revisar e editar cabeçalho, grupos, atividades, horas e performance;
- mover atividades e grupos por drag-and-drop;
- trabalhar em duas folhas lado a lado;
- desfazer alterações durante a sessão;
- ativar gráficos de barras ou pizza;
- ampliar o preview e usar tela cheia;
- gerar XLSX, PDF ou ambos;
- incluir bruto/performance no arquivo final;
- enviar os relatórios por e-mail sem baixar os arquivos;
- traduzir grupos, atividades e rótulos fixos para inglês ou alemão quando o login estiver autorizado;
- usar o chat para editar o relatório por operações estruturadas.

O botão **Alterar dados** descarta o preview atual e devolve a guia ao fluxo de seleção zerado.

### Guias independentes

A seção **Relatórios abertos** da sidebar permite manter vários trabalhos independentes. Cada guia contém seu próprio relatório e é salva automaticamente no `localStorage` com debounce. A pilha de undo não é persistida em disco para evitar payloads excessivos.

### Dashboard de horas

O dashboard consulta os dados do usuário autenticado. Gerente e coordenador têm um seletor pra ver o dashboard de qualquer colaborador de engenharia (CAD+CAE com apontamento recente) — o backend re-resolve o colaborador no Projectile e nunca confia no nome/filial vindos da tela. Períodos:

- mês atual;
- últimos 3 meses;
- últimos 6 meses;
- últimos 12 meses.

Ele apresenta totais, dias com apontamento, média diária, referência de jornada, calendário, lacunas, distribuição por projeto/pacote, série mensal e comparação histórica. A jornada usa contrato quando disponível; caso contrário, o backend informa a fonte estimada e evita apresentar percentual como se fosse uma meta contratual.

O calendário considera feriados nacionais, o feriado estadual de São Paulo, o municipal de Santo André quando aplicável e pontes de segunda/sexta para feriados em terça/quinta.

### Painel de Gerência

Acesso controlado por `MANAGEMENT_PANEL_LOGINS`. O painel possui filtros de período, competência, centro de custo, cliente, pessoa, projeto e pacote de trabalho.

Os três KPIs principais são:

| Indicador | Meta | Cálculo |
|---|---:|---|
| Performance em horas | mínimo 10% | `(faturadas - trabalhadas) / trabalhadas` |
| Elaboração dos relatórios | máximo 5 dias úteis | dias úteis registrados nas amostras |
| Horas não faturáveis | máximo 10% | horas em pacotes com `tjob.pExternal = '0'` / trabalhadas |

O painel também inclui:

- evolução cronológica de trabalhado, faturado e delta;
- pacotes não faturáveis;
- leitura sob demanda dos e-mails de faturamento (**Verificar enviados**).

Quando o filtro por pessoa está ativo, faturado e performance ficam indisponíveis porque as amostras de faturamento existem no nível do projeto, não da pessoa.

### Diagnóstico de relatórios

Gerente e coordenador. O gerente vê todos os períodos; o coordenador, só os **últimos 12 meses e o ano passado** (o backend responde 403 pra outro período e só devolve amostras desses meses). O coordenador também não vê horas, faturado nem performance: a tela dele usa `/management/send-status`. Permite:

- acompanhar a situação de envio por projeto e mês (`enviado`, `parcial`, `não enviado`, `fechado`), com marcação manual de envio;
- manter o registro permanente de clientes/projetos fechados (popup **Fechados**);
- consultar amostras automáticas e manuais;
- corrigir projeto, competência, horas faturadas e dias úteis;
- definir se a amostra cobre o projeto inteiro ou pacotes específicos;
- identificar duplicidades;
- excluir amostras incorretas;
- consultar mensagens ignoradas pela automação;
- cadastrar manualmente uma amostra.

### Chat analítico

Só gerentes. Perguntas em português sobre os **últimos 12 meses** (a mesma janela do Painel de Gerência), respondidas com texto, gráfico e tabela, sempre com a fonte e o período usados. Cruza:

- **horas apontadas** (engenharia CAD+CAE) por cliente, projeto, colaborador, pacote, mês, centro de custo e faturável/não faturável — com contagem de pessoas, projetos e dias com apontamento, média por colaborador e % não faturável;
- **faturado x trabalhado** e performance por cliente, projeto e mês (mesma regra do Painel; não existe faturado por colaborador);
- **status de envio** dos relatórios por cliente, projeto e mês (mesma regra do Diagnóstico);
- **relatórios gerados** (histórico do `reports_db`).

Exemplos: "horas de cada colaborador por projeto no mês passado", "colaboradores com menos de 100 h em agosto", "top 5 projetos da Mercedes em 2026", "faturado x trabalhado por projeto em agosto", "quais projetos não tiveram relatório enviado em agosto?", "compare as horas por projeto de julho e agosto", "e em julho?" (continua a pergunta anterior).

Toda tabela tem ordenação por coluna, linha de total e botão **Baixar Excel**. O chat nunca executa consulta livre: a IA só escolhe entre medidas, dimensões e valores de um catálogo fixo, e todo número é calculado pelo backend — texto do Claude com número que não veio dos dados é descartado.

Pergunta sem período usa os últimos 12 meses, com aviso. Ano fora da janela recebe uma resposta fixa, sem consulta. Faturado só existe nos meses em que chegaram relatórios de faturamento; nos outros, o chat avisa em vez de calcular performance. O Jev (via OpenRouter ou TypeSafe) classifica a pergunta; sem chave, ou sem confiança, o Claude classifica.

## Histórico de relatórios (reports_db)

A cada `POST /generate` ou `POST /send-report`, a aplicação grava um snapshot imutável do relatório gerado (cabeçalho, grupos e atividades exatamente como recebidos), cria uma nova versão numerada do relatório correspondente e registra o resultado da geração — num segundo banco MySQL próprio, `reports_db`, totalmente separado do Projectile (roda como container Docker, ver [Começando](#começando)).

Pontos importantes:

- **Nunca bloqueia a geração do arquivo.** Se `reports_db` estiver fora do ar, com `REPORTS_DB_ENABLED=false`, ou qualquer chamada de persistência falhar, o `.xlsx`/`.pdf` é gerado e entregue normalmente — só fica sem registro no histórico dessa vez. A funcionalidade central do app nunca depende dessa infraestrutura secundária.
- O snapshot é **o payload exatamente como chegou em `/generate`** (já revisado/editado na tela, possivelmente via chat de IA) — não uma nova consulta ao Projectile.
- Duas gerações consecutivas do mesmo relatório (mesmo `project_code` + escopo de pacote + competência) viram versões sucessivas do mesmo `report`, nunca registros duplicados — protegido contra corrida em geração concorrente.
- O arquivo gerado é copiado pra `backend/data/report_artifacts/` (fora do Git), já que o caminho temporário original é apagado logo após o download.
- A resposta de `/generate` inclui os headers `X-Report-Id`/`X-Report-Version-Id`/`X-Report-Version-Number` (ou `X-Report-Ids` no caso `.zip`) quando a persistência funcionou — são **aditivos**, nunca assuma que vão estar presentes.
- Tela de histórico/versões (`HistoryPanel.tsx`, `GET /reports/*`), com uma barra de busca geral (número, projeto, competência e quem criou) que pesquisa enquanto você digita e trilha de auditoria formal (`audit_log`) já existem — visíveis a todo mundo, cada um só vendo os próprios relatórios (gerente vê todos).
- `GET /analytics/summary` (só gerente) agrega horas por competência/grupo/projeto, tempo médio de geração e taxa de falha sobre os mesmos dados — tela `AnalyticsPanel.tsx`, com no máximo 8 linhas visíveis por bloco (o resto rola). Fica esparso até acumular meses de uso real.

## Autenticação e permissões

- O login é validado diretamente na tabela `auser` do Projectile usando o mesmo hash `sha256(senha + salt)` do sistema legado.
- A senha do usuário não é persistida pela aplicação.
- A sessão usa token opaco em cookie `HttpOnly`, `SameSite=Lax`, com duração de 8 horas.
- O rate limit permite 5 falhas por IP antes de bloquear novas tentativas por 15 minutos.
- Todas as rotas de negócio exigem sessão.
- Três papéis, definidos por allowlist no `.env`:

  | Papel | Variável | Acesso |
  |---|---|---|
  | Gerente | `MANAGEMENT_PANEL_LOGINS` | tudo |
  | Coordenador | `COORDINATOR_LOGINS` | Gerar relatório (inclusive busca por cliente/projeto), Dashboard de horas (as próprias ou de qualquer colaborador de engenharia), o próprio Histórico e Diagnóstico de relatórios (últimos 12 meses e ano passado, sem horas/faturado/performance) |
  | Colaborador | — (qualquer outro login) | Gerar relatório (só as próprias horas), Dashboard de horas e o próprio Histórico |

- O coordenador não vê os KPIs do Painel de Gerência nem pela API: `/management/kpis`, `/analytics/summary` e `/analytics/chat` respondem 403 pra ele, e o Diagnóstico usa `/management/send-status`, que não traz horas, faturamento nem performance.
- A sidebar só esconde as telas; quem barra de verdade é o backend.
- Mudou uma allowlist? Reinicie o backend.
- `/translate-activities` exige login em `TRANSLATE_ALLOWED_LOGINS`.
- Swagger, ReDoc e OpenAPI ficam desativados em todas as execuções.

## Formato esperado do XLSX do Projectile

O parser procura uma linha de cabeçalho iniciada por `Dados | Horário | Hs`.

| Coluna | Uso |
|---|---|
| `Dados` | identifica uma linha real de apontamento |
| `Horário` | reconhecida no cabeçalho, não usada no agrupamento |
| `Hs` | horas, aceitando vírgula ou ponto decimal |
| `Observação` | `Prefixo-Descrição` ou `Prefixo_Descrição`; prefixo vira grupo e descrição vira atividade |
| `Projeto` | nome do projeto no modo consolidado |
| `Pacote de Trabalho` | identifica o pacote no modo separado |

O separador de pacote exige espaço em pelo menos um lado do hífen. Um texto como `Para-barro` não é dividido. Linhas de subtotal, assinatura ou totalmente vazias são ignoradas; dados parcialmente preenchidos viram avisos não bloqueantes.

Uploads são limitados a 25 MB e o conteúdo descomprimido do XLSX a 200 MB para reduzir o risco de zip bomb.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI 0.141.1, Uvicorn 0.49 |
| XLSX | openpyxl 3.1.5 para leitura; ZIP/XML direto para geração |
| PDF | ReportLab 5.0.1 e pypdf 6.16.2 |
| Banco do Projectile | MySQL via PyMySQL 1.2.0 (só leitura) |
| Banco de histórico | `reports_db`, MySQL em Docker; SQLAlchemy Core 2.0 + Alembic 1.14 |
| Identificadores | ULID (`python-ulid`) pras tabelas do histórico |
| Configuração | pydantic-settings 2.7 (`backend/app/core/config.py`) |
| Credenciais de banco | Windows Credential Manager via keyring 25.7.0 (Projectile e `reports_db`) |
| Frontend | React 18, TypeScript 5.6, Vite 7.3.6, Zustand 4, immer 10 |
| IA | Anthropic SDK 0.125 e truststore 0.10.4; Jev (TypeSafe AI, via OpenRouter ou direto) no chat analítico, por HTTP com `requests` |
| Pool do Projectile | DBUtils 3.1 (`PooledDB`) |
| E-mail | Microsoft Graph e MSAL 1.31 |
| Testes | pytest 8.3.4 e Vitest 4.1.11 |

## Arquitetura

```text
Projectile MySQL (leitura)          reports_db (Docker, leitura+escrita)
   ├── autenticação e sessão              ├── snapshot do payload gerado
   ├── horas do usuário / dashboard       ├── versões do relatório
   ├── horas por cliente/projeto          ├── registro de geração
   └── KPIs gerenciais                    ├── artifact (.xlsx/.pdf copiado)
                                          ├── auditoria (audit_log)
                                          └── Gerência/Diagnóstico (mgmt_*)
            │                                      │
            └──────────────┬───────────────────────┘
                            ▼
FastAPI (`backend/app/main.py`)
   ├── parser XLSX
   ├── agrupamento de horas
   ├── geração XLSX/PDF
   ├── persistência de histórico (fail-open)
   ├── automação Microsoft Graph
   ├── chat/tradução Anthropic
   └── chat analítico (Jev + consulta cruzada + Claude)
            │
            ▼
React + Zustand
   ├── Sidebar e guias persistentes
   ├── Gerador/preview
   ├── Dashboard de horas
   ├── Painel de Gerência
   ├── Diagnóstico
   ├── Histórico de relatórios
   ├── Analytics
   └── Chat analítico
```

Decisões importantes:

- `generator.py` edita o XLSX por ZIP/XML para preservar desenhos, imagens, fórmulas e proteção do template.
- `projectile_db.py` empresta conexões de um pool de verdade (`DBUtils.PooledDB`, tamanho configurável via `PROJECTILE_DB_POOL_SIZE`, padrão 5) com `ping=1` e `autocommit=True`.
- As consultas filtram `sysClientId` para aproveitar os índices compostos do banco legado.
- O painel gerencial usa cache em memória de 15 minutos por intervalo.
- O frontend não usa React Router: `App.tsx` controla a view ativa e a sidebar.
- O preview do documento é deliberadamente branco nos dois temas; o restante da aplicação usa tokens dark/light.
- O FastAPI serve `frontend/dist` quando existe; sem build, usa `frontend/` como fallback estático.
- `reports_db` é banco separado do Projectile (nunca há JOIN entre os dois) e a persistência nele é sempre fail-open — ver [Histórico de relatórios (reports_db)](#histórico-de-relatórios-reports_db).

## Estrutura do projeto

```text
backend/
  alembic/                 # migrations do reports_db
    versions/
  app/
    main.py               # monta o FastAPI + middlewares + include_router; sem endpoint nenhum
    api/
      dependencies.py      # require_session/require_manager/require_manager_or_coordinator/require_translate_access
      errors.py             # log_and_generic_error, mensagens genéricas
      shared.py             # resolve_month_range, build_parse_response
      routers/
        auth.py              # /auth/*
        parsing.py           # /parse, /parse-db, /parse-db-client (+ hardening de upload)
        my_hours.py          # /my-hours, /my-hours/employees
        management.py        # /management/* (rota — não confundir com ../management.py, regra)
        generation.py        # /generate, /send-report
        history.py           # /reports/*, /artifacts/*/download
        chat.py               # /chat, /translate-activities
        analytics.py          # /analytics/summary (só gerente)
        analytics_chat.py     # /analytics/chat, /analytics/chat/export (só gerente)
    analytics/             # chat analítico: catálogo, consulta cruzada, travas, gráficos, Excel
    integrations/
      jev.py               # cliente HTTP do Jev (OpenRouter ou TypeSafe)
    repositories/          # leituras do chat analítico (horas de engenharia, relatórios gerados)
    auth.py               # login Projectile, rate limit e sessões
    db_credentials.py     # leitura da senha no Windows Credential Manager (Projectile e reports_db)
    projectile_db.py      # consultas e agrupamento de dados do Projectile
    parser.py             # parser do export XLSX
    generator.py          # gerador XLSX por ZIP/XML e calendário de dias úteis
    pdf_generator.py      # gerador PDF e metadados do relatório
    hours_analytics.py    # métricas do dashboard pessoal
    management.py         # KPIs, cache, amostras e fechados (regra de negócio; persistência em services/management_store.py)
    email_ingest.py       # Microsoft Graph, ingestão e envio de relatórios
    chatbot.py            # chamadas Anthropic
    chat_ops.py           # operações permitidas pelo chat (id estável)
    translate_ops.py      # contrato de tradução
    core/
      config.py            # Settings central (reports_db, sysClientId)
    db/
      reports_db.py        # engine SQLAlchemy do reports_db
      reports_schema.py    # tabelas do histórico (SQLAlchemy Core)
    services/
      snapshot.py           # hash/identidade/canonical JSON
      report_persistence.py # begin/finish_generation, fail-open
      report_queries.py     # leituras do histórico + agregações de analytics (não fail-open)
      management_store.py   # persistência de Gerência/Diagnóstico nas tabelas mgmt_* (não fail-open)
      audit.py              # trilha de auditoria, fail-open
    tools/
      import_management_json.py  # importação única do antigo management_kpi.json
  templates/
    relatorio_final_template.xlsx
  tests/                  # suíte pytest
frontend/
  public/                 # logos da aplicação/e-mail
  src/
    App.tsx               # shell e troca das sete views
    appView.ts            # nomes/tipo das views
    components/
      Sidebar.tsx
      FileUpload.tsx
      Preview/
      MyHoursDashboard.tsx
      MyHours/             # partes do dashboard, inclusive EmployeePicker (seletor de colaborador)
      ManagementPanel.tsx
      ManagementFilters.tsx # filtros compartilhados entre Gerência e Diagnóstico
      DiagnosticsPanel.tsx
      SendStatusCard.tsx   # "Relatórios enviados" do Diagnóstico
      HistoryPanel.tsx
      AnalyticsPanel.tsx
      AnalyticsChatPanel.tsx
      analytics/VisualizationRenderer.tsx  # gráficos e tabelas do chat analítico (SVG)
      PageHeader.tsx
      GenerateFooter.tsx
      SendReportModal.tsx
    store/
      useReportStore.ts
      useReportTabsStore.ts
      useAuthStore.ts
      useMyHoursStore.ts
      useManagementStore.ts
      useDiagnosticsStore.ts
      useHistoryStore.ts
      useAnalyticsStore.ts
      useAnalyticsChatStore.ts
    styles/index.css
    utils/
  package.json
  vite.config.ts
scripts/
  atualizar-servidor.bat
.github/workflows/ci.yml
docker-compose.yml         # container reports-mysql
alembic.ini                # script_location = backend/alembic
README.md
CLAUDE.md
PLANO_CHAT_ANALITICO_JEV_CLAUDE_v2.md
```

## Começando

### Pré-requisitos

- Python 3.11+
- Node.js 20+
- Docker (pro container `reports-mysql` do histórico de relatórios)
- Windows para usar o Credential Manager no ambiente real
- acesso de rede ao MySQL do Projectile
- chave Anthropic somente para chat de edição, tradução e chat analítico
- chave OpenRouter ou TypeSafe (opcional) para o Jev no chat analítico
- credenciais Azure somente para leitura/envio de e-mail

### 1. Configuração

```powershell
git clone <URL_DO_REPOSITORIO>
cd automação-relatório-v1.0
Copy-Item .env.example .env
```

Preencha as variáveis necessárias e salve a senha do banco do Projectile no Credential Manager:

```bash
python -c "import getpass, keyring; keyring.set_password('projectile_mysql', 'SEU_USUARIO_DB', getpass.getpass())"
```

### 2. Instalação

```bash
pip install -r backend/requirements.txt
npm --prefix frontend install
```

Para executar testes de backend, instale as dependências de desenvolvimento:

```bash
pip install -r backend/requirements-dev.txt
```

### 3. Banco de histórico (reports_db)

Só na primeira vez (ou depois de recriar o volume Docker):

```bash
docker compose up -d reports-mysql
alembic upgrade head
python -c "import getpass, keyring; keyring.set_password('reports_mysql', 'reports_app', getpass.getpass())"
```

A senha do keyring precisa ser a mesma de `REPORTS_MYSQL_APP_PASSWORD` no `.env` — a imagem oficial do MySQL cria o usuário `reports_app`/schema `reports_db` sozinha no primeiro start do container. Se `reports-mysql` estiver fora do ar depois disso, a aplicação continua funcionando normalmente (a persistência é *fail-open* — ver [Histórico de relatórios](#histórico-de-relatórios-reports_db)); só o histórico fica incompleto enquanto isso.

### 4. Desenvolvimento

Backend:

```bash
python -m uvicorn backend.app.main:app --reload --port 8011
```

Frontend:

```bash
npm --prefix frontend run dev
```

- FastAPI: `http://localhost:8011`
- Vite: `http://localhost:5173`

> O proxy atual do Vite cobre `/auth`, `/parse`, `/parse-db*`, `/generate`, `/chat`, `/reports`, `/artifacts` e `/analytics`. As telas que chamam `/management/*`, `/my-hours`, `/send-report` ou `/translate-activities` devem ser testadas pelo build servido pelo FastAPI ou após ampliar explicitamente o proxy em `frontend/vite.config.ts`.

### 5. Produção local

```bash
npm --prefix frontend run build
python -m uvicorn backend.app.main:app --port 8011
```

Acesse `http://localhost:8011`.

## Variáveis e credenciais

| Variável | Obrigatória para | Default/observação |
|---|---|---|
| `PROJECTILE_DB_HOST` | login e dados | sem default |
| `PROJECTILE_DB_PORT` | login e dados | `3306` |
| `PROJECTILE_DB_USER` | login e dados | sem default |
| `PROJECTILE_DB_NAME` | login e dados | `projectile` |
| senha `projectile_mysql` no Credential Manager | login e dados | nunca vai no `.env` |
| `PROJECTILE_SYS_CLIENT_ID` | performance das queries | `0`; sysClientId fixo desta instalação |
| `PROJECTILE_DB_POOL_SIZE` | pool de conexões do Projectile | `5` |
| `REPORTS_DB_HOST` | histórico de relatórios | `127.0.0.1` |
| `REPORTS_DB_PORT` | histórico de relatórios | `3307` |
| `REPORTS_DB_USER` | histórico de relatórios | `reports_app` |
| `REPORTS_DB_NAME` | histórico de relatórios | `reports_db` |
| senha `reports_mysql` no Credential Manager | histórico de relatórios | nunca vai no `.env` |
| `REPORTS_DB_ENABLED` | histórico de relatórios | `true`; desliga a persistência sem reverter código |
| `REPORTS_MYSQL_ROOT_PASSWORD` / `REPORTS_MYSQL_APP_PASSWORD` | bootstrap do `docker-compose.yml` | só usadas na 1ª subida do container, nunca em runtime |
| `MANAGEMENT_PANEL_LOGINS` | acesso gerencial | lista CSV; fallback `dherrera` |
| `COORDINATOR_LOGINS` | acesso de coordenador | lista CSV; sem fallback (vazia = nenhum coordenador) |
| `TRANSLATE_ALLOWED_LOGINS` | tradução | lista CSV; fallback `dherrera` |
| `ANTHROPIC_API_KEY` | chat de edição, tradução e chat analítico | sem default |
| `ANTHROPIC_MODEL` | chat de edição e tradução | `claude-sonnet-5` |
| `OPENROUTER_API_KEY` | Jev pelo OpenRouter (`openrouter.ai/api/v1/systemone`) | sem default; tem prioridade sobre `TYPESAFE_API_KEY`. Sem nenhuma das duas, o Claude classifica |
| `TYPESAFE_API_KEY` | Jev direto na TypeSafe (`api.typesafe.ai/v1/systemone`) | sem default; sem nenhuma chave o Claude classifica (1 chamada a mais por pergunta). Com chave, a pergunta e as listas de clientes/colaboradores/projetos vão pro OpenRouter e/ou pra TypeSafe AI |
| `JEV_MODEL` | Jev | `jev-latest` |
| `JEV_MIN_CONFIDENCE` / `JEV_MIN_CONFIDENCE_NONE` | confiança mínima do Jev | `0.60` / `0.40` ("nenhum"); calibrados contra o Jev real, não mude sem recalibrar |
| `ANALYTICS_CHAT_MODEL` | Claude do chat analítico (sem thinking) | `claude-haiku-4-5-20251001`; o chat de edição continua em `ANTHROPIC_MODEL` |
| `ANALYTICS_CHAT_MAX_MONTHS` / `ANALYTICS_CHAT_MAX_ROWS` / `ANALYTICS_CHAT_MAX_CLAUDE_PAYLOAD_BYTES` | limites do chat analítico | `12` (a janela do Painel) / `1000` / `20000` |
| `AZURE_TENANT_ID` | automação de e-mail | sem default |
| `AZURE_CLIENT_ID` | automação de e-mail | habilita o polling no startup |
| `AZURE_CLIENT_SECRET` | automação de e-mail | sem default |
| `GRAPH_MAILBOX` | automação de e-mail | caixa monitorada/cópia do envio |
| `ALBERTO_EMAIL` | automação de e-mail | um ou mais remetentes separados por vírgula |
| `EMAIL_POLL_INTERVAL_SECONDS` | automação de e-mail | `30` |
| `REPORT_PROTECTION_PASSWORD` | proteção da planilha | vazia mantém a proteção sem senha |

O app registration do Azure precisa de permissões de aplicação `Mail.Read` e `Mail.Send` com consentimento administrativo. Restrinja o escopo com Exchange Application Access Policy no ambiente real.

## Comandos

| Comando | O que faz |
|---|---|
| `python -m pytest backend/tests -v` | executa os testes do backend (testes de `reports_db` pulam sem Docker) |
| `docker compose up -d reports-mysql` | sobe o container do histórico de relatórios |
| `alembic upgrade head` | aplica as migrations pendentes do `reports_db` |
| `alembic revision --autogenerate -m "..."` | gera uma nova migration a partir de `reports_schema.py` |
| `npm --prefix frontend test` | executa os testes Vitest |
| `npm --prefix frontend run lint` | checa tipos com `tsc --noEmit` |
| `npm --prefix frontend run build` | checa tipos e gera `frontend/dist` |
| `npm --prefix frontend run dev` | inicia Vite com HMR |
| `npm --prefix frontend run preview` | serve o build do Vite em `:5173` |

Não há ESLint ou Prettier configurado; o script `lint` é uma checagem TypeScript.

## API

Todas as rotas abaixo exigem cookie de sessão, exceto `POST /auth/login`.

### Autenticação

| Método e rota | Função |
|---|---|
| `POST /auth/login` | autentica no Projectile e cria sessão |
| `GET /auth/me` | recupera a sessão atual |
| `POST /auth/logout` | encerra a sessão |

### Relatórios e dashboard pessoal

| Método e rota | Função |
|---|---|
| `POST /parse` | lê um XLSX (`file`, `mode=single|multi`) |
| `POST /parse-db` | busca o usuário logado por mês/período |
| `POST /parse-db-client` | busca projetos selecionados; requer gerente ou coordenador |
| `GET /my-hours` | dashboard de horas (`current_month`, `last_3`, `last_6`, `last_12`); `employee_id` opcional pra gerente/coordenador ver alguém de engenharia (CAD+CAE) |
| `GET /my-hours/employees` | lista do seletor de colaborador (engenharia com apontamento recente); requer gerente ou coordenador |
| `POST /generate` | gera XLSX/PDF direto ou ZIP; persiste histórico em `reports_db` (fail-open) |
| `POST /send-report` | gera anexos e envia via Microsoft Graph; mesma persistência fail-open |
| `POST /chat` | aplica operações de edição sugeridas pela IA |
| `POST /translate-activities` | traduz para `en` ou `de`; requer allowlist |

### Histórico de relatórios

Visíveis a todo mundo — quem não é gerente só vê os próprios relatórios (filtro aplicado no backend).

| Método e rota | Função |
|---|---|
| `GET /reports` | lista relatórios (paginado; `q` = busca geral por número, projeto, competência e quem criou — cada palavra precisa aparecer em alguma dessas colunas; filtros `report_number`/`competence`/`status`/`created_by`) |
| `GET /reports/{id}` | detalhe do relatório + número da versão atual |
| `GET /reports/{id}/versions[/{version_id}]` | versões do relatório, ou o snapshot completo de uma versão |
| `GET /reports/{id}/generations` | tentativas de geração de arquivo (sucesso/falha, duração) |
| `GET /reports/{id}/artifacts` | arquivos gerados |
| `GET /reports/{id}/audit` | trilha de auditoria do relatório |
| `GET /artifacts/{id}/download` | baixa um artifact; registra `artifact_downloaded` na auditoria |

### Gerência, diagnóstico e analytics

**Só gerente:**

| Método e rota | Função |
|---|---|
| `GET /management/kpis` | KPIs e filtros gerenciais |
| `POST /management/kpis/check-emails` | executa a ingestão de e-mails sob demanda |
| `PUT /management/kpis/{month}` | atualiza entrada manual mensal legada |
| `GET /analytics/summary` | métricas agregadas: horas por competência/grupo/projeto, tempo médio de geração, taxa de falha, relatórios por mês, responsáveis |
| `POST /analytics/chat` | chat analítico: pergunta em português → `{reply, visualizations, tables, metadata, context}`. Consulta cruzada sobre um catálogo fixo (nunca SQL gerado por IA); Jev classifica e o Claude só planeja/explica |
| `POST /analytics/chat/export` | tabela já exibida no chat → `.xlsx` (não consulta nada) |

**Gerente ou coordenador** (`test_coordinator_access.py` exige que toda rota nova desses routers esteja classificada numa das duas listas):

| Método e rota | Função |
|---|---|
| `GET /management/send-status` | status de envio por projeto/mês e opções de filtro, sem números de KPI; coordenador só nos últimos 12 meses ou no ano passado |
| `GET /management/clients-with-hours` | clientes ativos no mês/período |
| `GET /management/client-projects` | projetos ativos de um cliente |
| `GET /management/projects` | lista projetos para o diagnóstico |
| `GET/POST /management/kpis/samples` | lista ou cria amostras (a lista do coordenador fica nos meses que ele pode ver) |
| `PATCH/DELETE /management/kpis/samples/{sample_id}` | corrige ou exclui amostra |
| `GET /management/projects/{project_id}/packages` | pacotes do projeto em um mês |
| `GET /management/projects/{project_id}/all-packages` | histórico completo de pacotes |
| `GET /management/closed-registry` | lista clientes/projetos fechados |
| `POST/DELETE /management/closed-registry/clients/{client}` | fecha/reabre cliente |
| `POST/DELETE /management/closed-registry/projects/{project_id}` | fecha/reabre projeto |

## Geração de arquivos

- Um pacote + um formato: resposta com o arquivo direto.
- Mais de um pacote ou formato: resposta `.zip` com um arquivo por `(pacote, formato)`.
- Nomes duplicados recebem sufixo ` (n)`.
- Valores `NaN`/`Infinity` são rejeitados.
- XLSX e PDF carregam identidade, total e escopo de pacote usados pela automação de e-mail.
- O XLSX oficial é copiado e alterado internamente; não substitua esse fluxo por `openpyxl.save()`.
- Cada `(pacote, formato)` gerado também vira snapshot + versão + registro de geração em `reports_db` — ver [Histórico de relatórios](#histórico-de-relatórios-reports_db).

## CI e atualização do servidor

`.github/workflows/ci.yml` executa:

- backend: sobe um serviço `mysql` (`reports_db_test`), aplica `alembic upgrade head` e roda pytest — em todo push e em PR para `main`;
- Vitest, typecheck e build do frontend nas mesmas condições.

Não há deploy automático. No servidor Windows, use:

```powershell
.\scripts\atualizar-servidor.bat
```

O script faz `git pull origin main`, instala dependências, sobe `reports-mysql` via Docker e aplica `alembic upgrade head` (nunca reinicia o backend se a migration falhar), recompila o frontend, importa os dados de gerência do antigo `management_kpi.json` pro `reports_db` e reinicia via NSSM quando `SERVICE_NAME` estiver configurado.

**Primeira atualização depois da migração dos dados de gerência:** a importação roda uma única vez e renomeia o JSON pra `management_kpi.json.migrated-<data>` (backup, nunca apagado). Evite editar o Diagnóstico/Painel de Gerência durante a atualização: até o restart, o backend antigo ainda grava no JSON. Sem NSSM configurado, reinicie o backend logo depois do script terminar, antes de alguém usar o sistema.

## Troubleshooting

- **Login ou dados não conectam:** confira variáveis `PROJECTILE_DB_*`, senha no Credential Manager e acesso à rede interna.
- **403 em páginas gerenciais:** o login não está em `MANAGEMENT_PANEL_LOGINS` (ou em `COORDINATOR_LOGINS`, pro Diagnóstico); reinicie o backend após alterar `.env`.
- **403 no Diagnóstico de um coordenador:** o período pedido está fora dos últimos 12 meses e do ano passado. A tela só oferece esses dois; o 403 aparece quando a chamada vai direto na API.
- **Chat analítico lento na 1ª pergunta (~20 s):** é a carga das horas da janela de 12 meses; as seguintes usam o cache de 15 minutos.
- **Chat analítico sempre com `classifier: claude`:** falta `OPENROUTER_API_KEY`/`TYPESAFE_API_KEY`, ou o Jev está fora do ar ou sem confiança. Funciona igual, com uma chamada a mais ao Claude.
- **403 na tradução:** o login não está em `TRANSLATE_ALLOWED_LOGINS`.
- **Chat/tradução 500:** `ANTHROPIC_API_KEY` ausente ou modelo inválido.
- **E-mail 400/502:** confira variáveis Azure/Graph, permissões e Application Access Policy.
- **Vite retorna 404 em uma tela interna:** veja a limitação de proxy descrita na seção Desenvolvimento.
- **Logo ausente no build:** confirme os arquivos em `frontend/public/` antes de compilar.
- **Template perde logo/desenhos:** não use `openpyxl.save()` na geração.
- **`/generate` funciona mas nunca aparece `X-Report-Id` na resposta:** `reports-mysql` está fora do ar, `REPORTS_DB_ENABLED=false`, ou falta senha no keyring `reports_mysql` — isso é esperado ser silencioso (fail-open), não um erro; confira os logs do backend pra ver a causa.
- **Painel de Gerência/Diagnóstico responde 502:** esses dados vivem no `reports_db` e, diferente do histórico, não têm fail-open — confira se o container `reports-mysql` está de pé (`docker compose ps`) e a senha no keyring `reports_mysql`.
- **Importação do JSON de gerência recusa com "já tem dados de gerência sem registro de importação":** o backend novo subiu antes da importação e o polling de e-mail recriou as amostras a partir dos e-mails — **sem** as correções manuais feitas no Diagnóstico, que só o JSON tem. Rode `python -m backend.app.tools.import_management_json --replace-existing`: o JSON prevalece e o que estava no banco fica guardado em `mgmt_meta`.
- **`alembic upgrade head` falha com "tabela já existe":** o schema já tem tabelas de uma tentativa anterior sem `alembic_version` atualizada — confira `SELECT * FROM alembic_version` no `reports_db` antes de rodar de novo.

## Documentação adicional

O arquivo [PLANO_CHAT_ANALITICO_JEV_CLAUDE_v2.md](PLANO_CHAT_ANALITICO_JEV_CLAUDE_v2.md) é o plano de origem do chat analítico; o estado implementado está na seção "Chat analítico" do `CLAUDE.md`.
