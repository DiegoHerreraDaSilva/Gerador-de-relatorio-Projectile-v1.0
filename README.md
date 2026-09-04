# Automação de Relatório de Horas

Aplicação web **interna** (Schwaben Engineering) que converte horas apontadas no **Projectile** — via export `.xlsx` ou direto do banco de dados — no relatório final formatado para **Mercedes-Benz**: mesma logo, mesmas caixas de assinatura, mesmas fórmulas e tabela auxiliar "Week/AK/Days/Hours" — sem montar manualmente todo mês.

Fluxo: **Login com usuário do Projectile → Importar horas (planilha ou banco) → Revisar/editar na tela → Gerar `.xlsx` final (ou `.zip` com 1 por Pacote).**

Quem tem acesso de gerência também tem um segundo fluxo: **Painel de Gerência**, um dashboard de KPIs de engenharia (horas trabalhadas/faturadas, performance, elaboração de relatórios, horas não faturáveis) alimentado direto do banco do Projectile.

> App sem banco/ORM próprio para o relatório em si — arquivos temporários em `tempfile.gettempdir()/relatorio_horas_output`. O template Excel oficial nunca é recriado, só injetado (ver [por que `generator.py` não usa `openpyxl.save()`](#por-que-generatorpy-não-usa-openpyxlsave)). Login e dados de horas vêm do **banco MySQL do Projectile** (leitura); os únicos dados que este app persiste sozinho são os KPIs manuais do Painel de Gerência, num JSON simples fora do git.

---

## Funcionalidades

- **Login com as credenciais do Projectile** (`backend/app/auth.py`):
  - Autentica direto contra `auser` do MySQL do Projectile (mesmo hash `sha256(senha+salt)` que o Projectile usa) — sem duplicar usuário/senha neste app.
  - Sessão em memória do processo (token opaco em cookie `httponly`, 8h), rate limit de tentativas por IP (5 tentativas → bloqueio de 15min), mensagem de erro genérica (não revela se o login existe).
  - Todas as rotas sensíveis (`/parse`, `/parse-db`, `/generate`, `/chat`, `/management/*`) exigem sessão válida.
- **Duas formas de importar horas**:
  - **Planilha** — parse inteligente do export `.xlsx` do Projectile (`backend/app/parser.py:109`): agrupa por `Observação` (`Prefixo-Descrição` ou `Prefixo_Descrição`), soma horas case-insensitive, aceita `,`/`.` decimal, cabeçalho `Dados/Horário/Hs` em qualquer linha. Banner não-bloqueante de validação para linhas ignoradas.
  - **Direto do banco** (`POST /parse-db`, botão "Buscar do Projectile") — busca as horas do **próprio usuário logado** num mês de referência, direto do MySQL do Projectile, sem precisar exportar/subir planilha. Mesma regra de agrupamento da planilha.
- **Revisão rica na tela** (React + Zustand):
  - Edição inline de horas/performance/nomes, preview espelho em tempo real (nunca perde foco).
  - Drag-and-drop: atividades entre grupos, grupos inteiros entre relatórios (split view), abas de pacote para merge.
  - Split view (2 relatórios lado a lado), undo global (50 níveis, por `id`), zoom 50–150%, fullscreen, tema claro/escuro.
  - **Chat IA** (`backend/app/chatbot.py` + `POST /chat`) — "renomeie o grupo X", "performance 1.1 em todos" etc. O modelo devolve uma **lista de operações** (`backend/app/chat_ops.py`) em vez de reescrever o relatório inteiro, o que reduz bastante os tokens de saída (e portanto a latência).
- **Geração fiel ao template** (`backend/app/generator.py:461`):
  - Edição direta do XML `xl/worksheets/sheet1.xml` (preserva `xl/drawings`, `xl/media` — nunca `openpyxl.save()`).
  - Cálculo automático de dias úteis por semana, descontando feriados nacionais fixos e móveis (Páscoa → Carnaval/Sexta/Corpus Christi, Consciência Negra ≥2024).
  - **Relatório único** (1 `.xlsx`) ou **múltiplos** (1 `.xlsx` por Pacote de Trabalho, zipado com dedup `arcname (n)`).
- **Painel de Gerência** (`backend/app/management.py`, acesso restrito — ver abaixo): dashboard de KPIs de engenharia direto do banco do Projectile, com filtros e edição de metas manuais. Detalhes na seção própria.

---

## Painel de Gerência

Reconstrói dentro do app um relatório de KPIs de engenharia (times **CAD+CAE**) que antes só existia num Power BI separado. Acesso restrito a quem está em `MANAGEMENT_PANEL_LOGINS` (`backend/app/management.py:41` — hoje só `dherrera`; para liberar outro login, adicione à lista).

Três cartões, cada um com um *gauge* e uma tabela mês a mês (competência):

| Cartão | Meta | Fórmula |
|---|---|---|
| **Performance em Horas** | mínimo 10% | `Trabalhadas` = soma de horas CAD+CAE no mês (banco); `Faturadas` = input manual do gerente; `Perf. H = Faturadas − Trabalhadas`; `KPI % = Perf. H / Trabalhadas` |
| **Elaboração dos relatórios** | máximo 5 dias úteis | `KPI (Dias)` = 100% input manual, sem fórmula |
| **Horas não faturáveis** | máximo 10% | `Horas NãoFat` = soma de horas cujo pacote de trabalho tem `tjob.pExternal = '0'` no Projectile; `KPI % = Horas NãoFat / Trabalhadas` |

Já existiu uma lista manual de nomes de pacote (ex: "Treinamento") pra decidir "não faturável" — trocada por `pExternal` depois de uma auditoria estatística mostrar que esse campo do Projectile já é consistente pro que realmente importa (pacotes ativos hoje e com apontamento nos últimos 12 meses batem 100% com a expectativa; a inconsistência real fica só no histórico antigo/fechado, fora de qualquer período que o painel consulta). Mais simples e sem lista pra manter.

Filtros (`frontend/src/components/ManagementFilters.tsx`), todos client-side sobre o mesmo resultado cacheado, exceto quando mudam o recorte do banco:

- **Período**: últimos 12 meses corridos (padrão) ou um ano fechado específico (Jan–Dez), até o ano do primeiro lançamento no banco.
- **Competência**: filtro de exibição, não refaz busca.
- **Centro de Custo**: CAD/CAE (os dois por padrão).
- **Cliente** / **Projeto**: só mostram quem teve horas no período em vista — `Projeto` usa `tproject` de verdade (não o pacote de trabalho, que é mais granular).

Persistência: os valores manuais (Faturadas, dias de elaboração) sobrevivem a reinícios do backend num JSON simples, `backend/data/management_kpi.json` (fora do git — ver [Variáveis](#variáveis-e-credenciais)).

---

## Formato esperado do export do Projectile (modo planilha)

Cabeçalho procurado: linha que começa com `Dados | Horário | Hs` (`backend/app/parser.py:101`).

| Coluna | Uso |
|---|---|
| `Dados` | data do apontamento (diferencia linha real de subtotal) |
| `Horário` | ignorada |
| `Hs` | horas; aceita `2,5` ou `2.5` |
| `Observação` | `Prefixo-Descrição` ou `Prefixo_Descrição` → `prefixo` vira **Grupo**, `descrição` vira **Atividade** (`re.search(r"[-_]")`) |
| `Projeto` | nome do projeto (modo único) |
| `Pacote de Trabalho` | `código - Pacote - Projeto - resto` → 2º segmento é o `key` do relatório (modo múltiplos). Separador exige espaço ao menos de um lado (`\s+-\s*|\s*-\s+`); hífen sem espaço (`Para-barro`) **não** é separador |

> Linhas totalmente em branco ou rodapé de assinatura (`Supervisor` etc.) são ignoradas silenciosamente; só `Hs`/`Observação` parcialmente preenchidos com dado real viram aviso de validação (banner não-bloqueante).

O modo "Buscar do Projectile" (direto do banco) usa a mesma regra de agrupamento, mas os dados já vêm limpos (sem rodapé, sem `Hs` de texto livre) — ver `backend/app/projectile_db.py:group_hours`.

---

## Stack

| Camada | Tecnologia | Onde |
|---|---|---|
| **Backend** | Python 3.11+, FastAPI 0.141.1, Uvicorn 0.49 | `backend/app/main.py` |
| **Excel** | openpyxl 3.1.5 (leitura) + ZIP/XML manual (escrita) | `backend/app/parser.py`, `generator.py` |
| **Banco do Projectile** | MySQL (legado, on-premise) via PyMySQL 1.2.0 | `backend/app/projectile_db.py`, `auth.py`, `management.py` |
| **Credenciais do banco** | Windows Credential Manager via `keyring` 25.7.0 (senha nunca em texto puro) | `backend/app/db_credentials.py` |
| **Frontend** | React 18, Vite 7.3.6, TypeScript 5.6, Zustand 4 + immer 10 | `frontend/src/`, `frontend/vite.config.ts` |
| **IA (chat de edição)** | Anthropic SDK 0.125, modelo `claude-sonnet-5` (padrão), truststore 0.10.4 (proxy corporativo) | `backend/app/chatbot.py`, `chat_ops.py` |
| **Build** | Vite (hash em `assets/`, `public/logo*.png` → `dist/`) | `frontend/dist/` servido pelo FastAPI |

Sem ORM, sem ESLint/Prettier configurado, sem testes automatizados ainda.

---

## Arquitetura

```
                          ┌──────────────────────────────┐
                          │        auser (Projectile)     │
        login/senha ─────►│  verify_projectile_login       │──► sessão em memória (cookie)
                          └──────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
     .xlsx --POST /parse-->      POST /parse-db -->      GET /management/kpis
       [parser.py]              [projectile_db.py]         [management.py]
                    │             fetch_employee_hours       fetch_engineering_hours
                    └──────────┬──────────┘                        │
                               ▼                                   ▼
                    [Zustand: useReportStore]           [Zustand: useManagementStore]
                               │                                   │
                    React (App.tsx) — Header/Stepper/           ManagementPanel +
                    FileUpload/PackageTabs/Preview/              ManagementFilters +
                    Chat/GenerateFooter                          Gauge (3 cartões)
                               │
                               ▼ POST /generate
                    [generator.py] --ZIP/XML--> .xlsx / .zip
```

- **Acesso ao banco do Projectile**: uma única conexão MySQL persistente por processo (`backend/app/projectile_db.py:_get_connection`), reaproveitada entre requisições em vez de abrir/fechar uma a cada chamada — ver [Performance e acesso ao banco](#performance-e-acesso-ao-banco-do-projectile).
- **API** em `backend/app/main.py` monta `NoCacheStaticFiles` por último (`html=True`). Em prod serve `frontend/dist` (hash `immutable` para `assets/*`, `no-store` para o resto); sem `dist`, cai para `frontend/`.
- **Proxy dev**: `frontend/vite.config.ts` → `/parse`, `/parse-db`, `/generate`, `/chat`, `/auth/*`, `/management/*` → `http://localhost:8011`.

---

## Performance e acesso ao banco do Projectile

O MySQL do Projectile é uma instalação legada, on-premise, de **cliente único** — toda tabela relevante (`ttimebit`, `tjob`, `temployee`, `tproject`, `auser`) tem `sysClientId` como primeira coluna de todo índice composto. Nenhuma das queries originais filtrava por essa coluna, então o MySQL nunca conseguia usar os índices e caía sempre para *table scan* completo (medido: consultas de ~37s numa tabela de ~320 mil lançamentos). Filtrando por `sysClientId` (constante `_SYS_CLIENT_ID` em `projectile_db.py`, confirmado como valor único do banco), as mesmas consultas passam a usar os índices certos — a mesma query cai para **~0.4s**, mesmo resultado.

Além disso:

- **Conexão persistente e reaproveitada** (`projectile_db.py:_get_connection`) — como as rotas que tocam esse banco são síncronas, uma única conexão por processo (com `ping(reconnect=True)` para detectar e recuperar quedas) é suficiente; abrir uma conexão nova a cada chamada é o custo dominante quando o servidor do Projectile está sob carga (chegou a ser medido em ~20s só para conectar). A conexão usa `autocommit=True`: como este módulo só faz leitura, isso evita que o isolamento `REPEATABLE READ` do MySQL "congele" a foto dos dados na primeira consulta da conexão para sempre.
- **Cache em memória** de 15 min por intervalo de datas (`management.py:_HOURS_CACHE`) para a busca de horas de engenharia, evitando repetir a mesma consulta a cada troca de filtro no Painel de Gerência.
- **Login em uma única query** (`auth.py:verify_projectile_login`) — `auser` + `temployee` resolvidos com um `LEFT JOIN`, numa conexão só, em vez de duas consultas seriais.
- **Busca de horas por ID, não por nome**: `POST /parse-db` usa o `employee_id` (FK real, resolvido no login) para filtrar `tjob.pEmployee = %s`, com fallback por nome parcial (`LIKE`) só quando não há `employee_id` disponível.

---

## Começando

### Pré-requisitos

- Python 3.11+ e Node 18+ (testado Node 24, npm 12)
- Windows (o cofre de credenciais do banco usa o Windows Credential Manager via `keyring`)
- Acesso de rede ao MySQL do Projectile (obrigatório — login e busca de horas dependem dele)
- Chave Anthropic se for usar o chat de edição

### 1. Clonar e configurar `.env`

```bash
git clone <repo> && cd automação-relatório-v1.0
cp .env.example .env
```

Edite `.env`:

```bash
ANTHROPIC_API_KEY=            # obrigatória só para o chat de edição
ANTHROPIC_MODEL=claude-sonnet-5

PROJECTILE_DB_HOST=           # obrigatório
PROJECTILE_DB_PORT=3306
PROJECTILE_DB_USER=           # obrigatório
PROJECTILE_DB_NAME=projectile
```

A **senha** do banco do Projectile não vai no `.env` — fica no Windows Credential Manager:

```bash
python -c "import getpass, keyring; keyring.set_password('projectile_mysql', 'SEU_USUARIO_DB', getpass.getpass())"
```

### 2. Backend

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8011
# → http://localhost:8011  (serve frontend/dist se existir)
```

`.claude/launch.json` já usa `backend.app.main:app --port 8011`.

### 3. Frontend

```bash
npm --prefix frontend install
npm --prefix frontend run dev    # http://localhost:5173  (HMR + proxy)
npm --prefix frontend run build  # gera frontend/dist → servido pelo FastAPI em prod
npm --prefix frontend run preview
```

**Prod sem Vite dev**: só `npm --prefix frontend run build` + `uvicorn backend.app.main:app --port 8011` e abra `http://localhost:8011`.

### Variáveis e credenciais

| Var / credencial | Onde | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | `backend/app/chatbot.py` | — (obrigatória p/ chat) |
| `ANTHROPIC_MODEL` | `backend/app/chatbot.py` | `claude-sonnet-5` |
| `PROJECTILE_DB_HOST` / `_PORT` / `_USER` / `_NAME` | `backend/app/projectile_db.py` | porta `3306`, nome `projectile` |
| senha do banco do Projectile | Windows Credential Manager, serviço `projectile_mysql` (via `keyring`) | — (obrigatória p/ login e busca de horas) |
| `PORT` | `uvicorn --port` | `8011` (dev) / `5173` (Vite) |
| `backend/data/management_kpi.json` | KPIs manuais + pacotes não faturáveis do Painel de Gerência | criado automaticamente, fora do git |

---

## CI (GitHub Actions)

`.github/workflows/ci.yml` — 2 jobs, todo push e todo PR pra `main`:

| Job | O que faz |
|---|---|
| `backend-tests` | `pip install -r backend/requirements-dev.txt` + `pytest backend/tests/` |
| `frontend-build` | `npm ci` + `npm run test` (vitest) + `npm run build` (tsc -b && vite build) |

Sem deploy automático — a conexão SSH direto entre o servidor e o GitHub foi avaliada como um risco não aceitável pra esse projeto. Atualizar o servidor continua manual, seguindo os passos de **Build & Run** acima (`git pull`, reinstalar dependências, `npm run build`, reiniciar o processo/serviço).

---

## Estrutura do projeto

```
backend/
  app/
    main.py           # FastAPI: /auth/*, /parse, /parse-db, /generate, /chat,
                       # /management/*, NoCacheStaticFiles + mount
    auth.py            # login via Projectile (auser+temployee), sessão em memória,
                       # rate limit de tentativas
    db_credentials.py  # senha do banco via Windows Credential Manager (keyring)
    projectile_db.py   # conexão persistente com o MySQL do Projectile,
                       # fetch_employee_hours/fetch_engineering_hours/group_hours
    management.py      # KPIs do Painel de Gerência (fórmulas, cache, persistência)
    parser.py          # parse_projectile_export() do .xlsx, RowIssue
    generator.py        # generate_report() via ZIP/XML, feriados, dias úteis
    chatbot.py          # call_chat() com tool_use forçado
    chat_ops.py         # catálogo de operações que o chat pode aplicar
    __init__.py
  templates/
    relatorio_final_template.xlsx  # 49KB, fonte da verdade (nunca recriar)
  data/
    management_kpi.json  # gerado em runtime, fora do git
  requirements.txt
frontend/
  index.html
  vite.config.ts     # proxy + build.outDir=dist
  tsconfig.json / tsconfig.node.json
  public/
    logo.png / logo-light.png
  src/
    main.tsx
    App.tsx            # roteamento entre "report" e "management" + composição geral
    styles/index.css
    api/types.ts        # WorkPackage, Group, Activity, RowIssue, ParseResponse, ChatState
    utils/{fmt.ts, calc.ts, fileName.ts, theme.ts}
    store/
      useReportStore.ts      # Zustand+immer: packages por id, undo snapshot, split, drag
      useAuthStore.ts         # sessão (login/logout/checkSession), isManager
      useManagementStore.ts   # dados/filtros do Painel de Gerência, carregamento único
    components/
      LoginScreen.tsx, Header.tsx, Stepper.tsx, FileUpload.tsx, ValidationBanner.tsx
      PackageTabs.tsx, PackageFileName.tsx
      Preview/Preview.tsx, Preview/PreviewSheet.tsx
      Chat.tsx, GenerateFooter.tsx, SummaryBar.tsx
      ManagementPanel.tsx, ManagementFilters.tsx, Gauge.tsx, ExtraHoursInput.tsx

templates/exemplo_projectile.xlsx  # ignorado (.gitignore) — dados reais, só local
```

Root: `README.md`, `CLAUDE.md`, `.gitignore`, `.env`, `.claude/launch.json`.

---

## API

Todas as rotas abaixo, exceto `/auth/login`, exigem sessão válida (cookie `session_token`); as de `/management/*` exigem também que o login esteja em `MANAGEMENT_PANEL_LOGINS`.

### `POST /auth/login`

`{ login, password }` → `200 { name, login, email, is_manager }` + cookie de sessão (8h). `401` login/senha incorretos, `429` rate limit.

### `GET /auth/me`

Sem corpo → `200` (mesmo formato do login) se a sessão for válida, `401` senão. Usado no boot do app pra manter a sessão entre recarregamentos.

### `POST /auth/logout`

Encerra a sessão atual.

### `POST /parse`

`multipart/form-data`: `file: .xlsx`, `mode: "single"|"multi"` (Form).

**200**
```json
{
  "packages": [{ "key": "Sangam", "project_name": "1540 ...", "groups": [{ "name": "Bumper", "total_hours": 165, "activities": [{ "description": "Modelagem", "hours": 12.5 }] }] }],
  "issues": [{ "row": 42, "reason": "sem_separador", "message": "Linha 42: Observação \"X\" sem \"-\" ou \"_\" ..." }]
}
```
Erros: `400` BadZipFile / ValueError / KeyError.

### `POST /parse-db`

`{ month_label: "Agosto/2026", mode: "single"|"multi" }` → busca as horas do **usuário logado** (nunca de um nome vindo do cliente) direto no Projectile e devolve o mesmo formato de `/parse`. `404` se não encontrar lançamento no mês, `502` se o banco falhar.

### `POST /generate`

`application/json`: `{ packages: [{ header: {project_code, project_name, location_date, month_label, signer1_name/company, signer2_name/company}, groups: [{name, performance, activities: [{description, hours}] }], file_name? }], formats?: ["xlsx"|"pdf"] }` (default `["xlsx"]`)

- `.xlsx` via `generator.py` (ZIP/XML do template, nunca `openpyxl.save()`); `.pdf` via `pdf_generator.py` (`reportlab`, A4 retrato, mesmos dados/totais que o `.xlsx`)
- `len(packages)==1` e `len(formats)==1` → `200`, arquivo direto (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` ou `application/pdf`)
- qualquer outra combinação → `200 application/zip` (`Relatórios_Horas.zip`, um arquivo por `(pacote, formato)`, dedup `arcname (n)`)
- `NonFiniteValueError → 400`, template corrompido `→ 500`

Validação `allow_inf_nan=False` evita `NaN/Infinity` virar `500`.

### `POST /chat`

`{ message: string, state: ChatState }` → `{ reply: string, state: ChatState }`. `ChatState` usa **camelCase**, diferente de `/generate` (`snake_case`) — proposital. Valida `len(packages)` não mudou senão `502`. `ChatConfigError→500`, `ChatUpstreamError→502`.

### `GET /management/kpis`

Query params: `months` (default 12), `year` (opcional, ano fechado), `cost_centers`/`clients`/`projects` (listas repetíveis), `force_refresh` (bool, ignora o cache de 15min). Requer gerente. → `{ months: [...], cost_centers, available_projects, available_clients }`.

### `PUT /management/kpis/{month}`

`{ billed_hours, elaboration_days }` (mês `AAAA-MM`) — grava os valores manuais de um mês. Requer gerente.

---

## Frontend — pontos-chave

- **`useReportStore.ts`**: `packages: WorkPackage[]` por `id` (não índice), `activePackageId`, `header: ReportHeader` (global), `undoStack: string[]` (JSON com `Set` serializado como `{__set:[...]}`), `isSplit/paneBPackageId`, drag state. `enableMapSet()` obrigatório para `Set` no immer. `Activity.extra` marca atividades criadas manualmente (independente do valor de `hours`, pra não sumir o campo editável no meio da digitação).
- **`useAuthStore.ts`**: `user` (com `isManager`), `login`/`logout`/`checkSession` — chamado uma vez no boot do `App.tsx`.
- **`useManagementStore.ts`**: dados e filtros do Painel de Gerência; carrega uma única vez ao abrir o painel (não recarrega ao trocar de volta pra "Geração de Relatório" e voltar), com guarda contra requisições concorrentes sobrepostas.
- **Preview**: `PreviewSheet.tsx` renderiza folha sempre branca `#fff`/`#1a1a1a` (não usa tokens dark/light), inputs `pv-input` transparentes, updates pontuais via `textContent` (nunca `innerHTML` com foco).
- **Tema**: script inline no `<head>` evita FOUC; `Header.tsx` troca `document.documentElement.dataset.theme` + `localStorage` + logo por tema; CSS vars `:root` / `:root[data-theme="light"]`.
- **Cache HTTP**: `NoCacheStaticFiles` → `assets/*: immutable 1y`, resto `no-store`.

---

## Scripts

| Comando | Onde | O que faz |
|---|---|---|
| `pip install -r backend/requirements.txt` | root | instala backend |
| `python -m uvicorn backend.app.main:app --reload --port 8011` | root | dev backend |
| `npm --prefix frontend install` | root | instala frontend |
| `npm --prefix frontend run dev` | root | Vite dev `:5173` |
| `npm --prefix frontend run build` | root | `tsc -b && vite build` → `frontend/dist` |
| `npx --prefix frontend tsc --noEmit` | root | checa tipos |

---

## Troubleshooting

- **Porta ocupada**: troque `--port 8012` nos dois lugares (uvicorn + `vite.config.ts` proxy).
- **Login falha com "Erro ao conectar no banco do Projectile"**: confira `PROJECTILE_DB_HOST/USER/NAME` no `.env` e se a senha foi salva no Credential Manager (`db_credentials.py`).
- **Login lento na primeira tentativa depois do backend subir**: normal — é o custo de abrir a primeira conexão MySQL do processo; as próximas ficam rápidas (conexão reaproveitada). Se continuar lento sempre, o servidor do Projectile pode estar sob carga (fora do controle deste app).
- **`403` no Painel de Gerência**: seu login não está em `MANAGEMENT_PANEL_LOGINS` (`backend/app/management.py`).
- **Chat 500**: `ANTHROPIC_API_KEY` não configurada.
- **Chat 502**: rede/proxy corporativo — `truststore.inject_into_ssl()` já usa o armazém de certificados do Windows; tente `Invoke-WebRequest` para testar conectividade.
- **Geração com `Infinity`**: horas muito grandes que somadas estouram `float` viram `NonFiniteValueError → 400` (corrija horas).
- **Logo sumida em prod**: `frontend/public/logo*.png` deve existir antes do `build` (`publicDir` do Vite).

---

## Por que `generator.py` não usa `openpyxl.save()`

`openpyxl` descarta `xl/drawings` e `xl/media`. Para preservar 100% (logo, caixas, fórmulas), `backend/app/generator.py` copia o `.xlsx` byte-a-byte e substitui só `xl/worksheets/sheet1.xml`, `xl/drawings/drawing1.xml`, `xl/workbook.xml`, limpando `calcChain.xml`.
