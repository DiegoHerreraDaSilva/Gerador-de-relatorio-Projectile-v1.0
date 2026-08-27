# Automação de Relatório de Horas

Aplicação web **local** que converte o export de horas do **Projectile** (`.xlsx`) no relatório final da **Schwaben Engineering / Mercedes-Benz** — já formatado: mesma logo, mesmas caixas de assinatura, mesmas fórmulas e tabela auxiliar “Week/AK/Days/Hours” — sem montar manualmente todo mês.

Fluxo: **Importar export do Projectile → Revisar/editar na tela → Gerar `.xlsx` final (ou `.zip` com 1 por Pacote).**

> App sem DB/ORM, sem login. Arquivos temporários em `tempfile.gettempdir()/relatorio_horas_output` (`backend/app/main.py:71`). Template oficial nunca é recriado, só injetado.

---

## Funcionalidades

- **Parse inteligente do Projectile** (`backend/app/parser.py:109`):
  - Agrupa por `Observação` (`Prefixo-Descrição` ou `Prefixo_Descrição`), somando horas case-insensitive; aceita `,` ou `.` como separador decimal (`_parse_hs_value`).
  - Cabeçalho `Dados, Horário, Hs` pode estar em qualquer linha (`_find_header_row`).
  - Banner **não-bloqueante** de validação para linhas ignoradas: sem separador, descrição vazia, `Hs` inválido, pacote não identificado, apontamento incompleto (`RowIssue` → `ValidationBanner.tsx`).
- **Revisão rica na tela** (React + Zustand):
  - Edição inline de horas/performance/nomes, preview espelho em tempo real (nunca perde foco).
  - Drag-and-drop: atividades entre grupos, grupos inteiros entre relatórios (split view), abas de pacote para merge (`mergePackages`).
  - **Split view** 2 relatórios lado a lado, **undo global** (50 níveis, por `id`), **zoom 50–150%**, **fullscreen** da folha, **tema claro/escuro** com ícones minimalistas (`THEME_ICONS`).
  - **Chat IA** (`backend/app/chatbot.py:136` + `POST /chat`) — “renomeie o grupo X”, “performance 1.1 em todos” via `tool_choice` Anthropic.
- **Geração fiel ao template** (`backend/app/generator.py:461`):
  - Edição direta do XML `xl/worksheets/sheet1.xml` (preserva `xl/drawings`, `xl/media` — nunca `openpyxl.save()`).
  - Cálculo automático de dias úteis por semana do mês, descontando feriados nacionais fixos e móveis (Páscoa → Carnaval/Sexta/Corpus Christi, Consciência Negra ≥2024).
  - Deslocamento automático das caixas de assinatura conforme tamanho do conteúdo.
- **Dois modos**
  - **Relatório único**: 1 `.xlsx` direto.
  - **Múltiplos relatórios**: 1 `.xlsx` por *Pacote de Trabalho* (2º segmento de `Pacote de Trabalho` separado por ` - ` → ex: `1546.6.4-002 Legislation Package - Sangam - Cabina` → `Sangam`), zipado com dedup `arcname (n)`.

---

## Formato esperado do export do Projectile

Cabeçalho procurado: linha que começa com `Dados | Horário | Hs` (`backend/app/parser.py:101`).

| Coluna | Uso |
|---|---|
| `Dados` | data do apontamento (diferencia linha real de subtotal) |
| `Horário` | ignorada |
| `Hs` | horas; aceita `2,5` ou `2.5` |
| `Observação` | `Prefixo-Descrição` ou `Prefixo_Descrição` → `prefixo` vira **Grupo**, `descrição` vira **Atividade** (`re.search(r"[-_]")`) |
| `Projeto` | nome do projeto (modo único) |
| `Pacote de Trabalho` | `código - Pacote - Projeto - resto` → 2º segmento é o `key` do relatório (modo múltiplos). Separador exige espaço ao menos de um lado (`\s+-\s*|\s*-\s+` `backend/app/parser.py:77`); hífen sem espaço (`Para-barro`) **não** é separador |

> Linhas totalmente em branco ou rodapé de assinatura (`Supervisor` etc.) são ignoradas silenciosamente; só `Hs`/`Observação` parcialmente preenchidos com dado real viram `RowIssue`.

---

## Stack

| Camada | Tecnologia | Onde |
|---|---|---|
| **Backend** | Python 3.11+, FastAPI 0.141.1, Uvicorn 0.49 | `backend/app/main.py:40` |
| **Excel** | openpyxl 3.1.5 (leitura) + ZIP/XML manual | `backend/app/parser.py:7`, `generator.py:1` |
| **Frontend** | React 18, Vite 7.3.6, TypeScript 5.6, Zustand 4 + immer 10 | `frontend/src/`, `frontend/vite.config.ts:1` |
| **IA** | Anthropic SDK 0.69, truststore 0.10.4 (proxy corporativo) | `backend/app/chatbot.py:22` |
| **Build** | Vite (hash em `assets/`, `public/logo.png` → `dist/`) | `frontend/dist/` servido por FastAPI |

Sem DB, sem ORM, sem ESLint/Prettier configurado.

---

## Arquitetura

```
Projectile .xlsx --POST /parse--> [parser.py] --packages/issues--> [Zustand store]
                                                            │
                                        ┌───────────────────┴───────────────────┐
                                        │  React (App.tsx)                    │
                                        │  Header/Stepper/ValidationBanner    │
                                        │  PackageTabs (drag merge)           │
                                        │  HeaderDataCard + GroupsPanel       │
                                        │  Preview (2 panes, drag, zoom)      │
                                        │  Chat + GenerateFooter              │
                                        └───────────────────┬───────────────────┘
                                                            │ POST /generate
                                                            ▼
                                              [generator.py] --ZIP/XML--> .xlsx/.zip
```

- **API** em `backend/app/main.py` monta `NoCacheStaticFiles` por último (`html=True`, `backend/app/main.py:311`). Em prod serve `frontend/dist` (hash `immutable` para `assets/*`, `no-store` para `index.html`); em dev faltando `dist`, cai para `frontend/` (ou Vite dev server).
- **Proxy dev**: `frontend/vite.config.ts:8` → `"/parse" "/generate" "/chat" → http://localhost:8011` (mesma origem em prod, sem CORS extra, mas `CORSMiddleware allow_origins=*` já está ativo).

---

## Começando

### Pré-requisitos

- Python 3.11+ e Node 18+ (testado Node 24, npm 12)
- Chave Anthropic se for usar o chat

### 1. Clonar e env

```bash
git clone <repo> && cd automação-relatório-v1.0
cp .env.example .env   # edite ANTHROPIC_API_KEY e ANTRHOPIC_MODEL
# .env.example: ANTHROPIC_API_KEY=, ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

### 2. Backend

```bash
pip install -r backend/requirements.txt
# requirements: fastapi==0.141.1, uvicorn==0.49.0, openpyxl==3.1.5,
# pydantic==2.13.4, python-multipart==0.0.32, anthropic==0.69.0,
# python-dotenv==1.1.1, truststore==0.10.4
python -m uvicorn backend.app.main:app --reload --port 8011
# → http://localhost:8011  (serve frontend/dist se existir)
```

`.claude/launch.json:7` já usa `backend.app.main:app --port 8011`.

### 3. Frontend

```bash
npm --prefix frontend install
npm --prefix frontend run dev    # http://localhost:5173  (HMR + proxy)
npm --prefix frontend run build  # gera frontend/dist → servido pelo FastAPI em prod
npm --prefix frontend run preview
```

**Prod sem Vite dev**: só `npm --prefix frontend run build` + `uvicorn backend.app.main:app --port 8011` e abra `http://localhost:8011`.

### Variáveis

| Var | Onde | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | `backend/app/chatbot.py:126` | — (obrigatória p/ chat) |
| `ANTHROPIC_MODEL` | `backend/app/chatbot.py:144` | `claude-haiku-4-5-20251001` |
| `PORT` | `uvicorn --port` | `8011` (dev) / `5173` (Vite) |

---

## Estrutura do projeto

```
backend/
  app/
    main.py        # FastAPI: POST /parse, /generate, /chat + NoCacheStaticFiles + mount
    parser.py      # parse_projectile_export(), _extract_package_key(), RowIssue
    generator.py   # generate_report() via ZIP/XML, feriados, _business_days_per_week()
    chatbot.py     # call_chat() com tool_use, SYSTEM_PROMPT, TOOL_SCHEMA
    __init__.py
  templates/
    relatorio_final_template.xlsx  # 49KB, fonte da verdade (nunca recriar)
  requirements.txt
frontend/
  index.html       # entry Vite: <div id="root"> + <script type=module src="/src/main.tsx">
  vite.config.ts   # proxy + build.outDir=dist
  tsconfig.json / tsconfig.node.json
  public/
    logo.png / logo-light.png  # copiados para dist (Vite publicDir)
  src/
    main.tsx       # ReactDOM.createRoot + import styles
    App.tsx        # composição: Header/Stepper/Summary/Validation/FileUpload/PackageTabs/HeaderData/Groups/Preview/Chat/Generate
    styles/index.css  # 38853 chars extraídos de web/index.html (visual idêntico)
    api/types.ts   # WorkPackage, Group, Activity, RowIssue, ParseResponse, ChatState
    utils/{fmt.ts, calc.ts, fileName.ts, theme.ts}
    store/useReportStore.ts  # Zustand+immer, packages por id, undo snapshot, split, drag
    components/
      Header.tsx, Stepper.tsx, FileUpload.tsx, ValidationBanner.tsx
      PackageTabs.tsx, PackageFileName.tsx, HeaderDataCard.tsx, GroupsPanel.tsx
      Preview/Preview.tsx, Preview/PreviewSheet.tsx
      Chat.tsx, GenerateFooter.tsx, SummaryBar.tsx (legado)

templates/exemplo_projectile.xlsx  # ignorado (.gitignore) — dados reais, só local
```

Root: `README.md`, `CLAUDE.md`, `.gitignore`, `.env`, `.claude/launch.json`.

---

## API

### `POST /parse` — `backend/app/main.py:75`

`multipart/form-data`: `file: .xlsx`, `mode: "single"|"multi"` (Form)

**200**
```json
{
  "packages": [{ "key": "Sangam", "project_name": "1540 ...", "groups": [{ "name": "Bumper", "total_hours": 165, "activities": [{ "description": "Modelagem", "hours": 12.5 }] }] }],
  "issues": [{ "row": 42, "reason": "sem_separador", "message": "Linha 42: Observação \"X\" sem \"-\" ou \"_\" ..." }]
}
```
Erros: `400` BadZipFile / ValueError / KeyError.

### `POST /generate` — `backend/app/main.py:169`

`application/json`: `{ packages: [{ header: {project_code, project_name, location_date, month_label, signer1_name/company, signer2_name/company}, groups: [{name, performance, activities: [{description, hours}] }], file_name? }] }`

- `len==1` → `200 application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` (`.xlsx` direto)
- `len>1` → `200 application/zip` (`Relatórios_Horas.zip` com dedup `arcname (n)`)
- Erro `NonFiniteValueError → 400`, template corrompido `→ 500`

Validação `allow_inf_nan=False` (`backend/app/main.py:114`) + `_sanitize_nonfinite` (`:49`) evita `NaN/Infinity` virar `500`.

### `POST /chat` — `backend/app/main.py:282`

`{ message: string, state: ChatState }` → `{ reply: string, state: ChatState }`

`ChatState` usa **camelCase** (`projectCode` etc.) diferente de `/generate` (`snake_case`) — proposital. Valida `len(packages)` não mudou senão `502`. `ChatConfigError→500`, `ChatUpstreamError→502`.

---

## Frontend — pontos-chave

- **Estado**: `frontend/src/store/useReportStore.ts:1` — `packages: WorkPackage[]` por `id` (não índice), `activePackageId`, `header: ReportHeader` (global), `undoStack: string[]` (JSON com `Set` serializado), `isSplit/paneBPackageId`, `draggedPackageId/Activities/Group`, `selectedByPane`. `enableMapSet()` obrigatório para `Set` no immer.
- **Preview**: `PreviewSheet.tsx` renderiza folha sempre branca `#fff`/`#1a1a1a` (não usa tokens dark/light), inputs `pv-input` transparentes (`preview.css`), updates pontuais via `textContent` (nunca `innerHTML` com foco). Drag de atividade (handle `pv-remove-activity` + marquee Ctrl+drag) e de grupo (`⠿`).
- **Tema**: script inline no `<head>` (`frontend/index.html:8`) evita FOUC; `Header.tsx` troca `document.documentElement.dataset.theme` + `localStorage` + `logo.png`↔`logo-light.png`; CSS vars `:root` / `:root[data-theme="light"]`.
- **Cache**: `NoCacheStaticFiles` (`backend/app/main.py:19`) → `assets/*: immutable 1y`, resto `no-store`.

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

- **Porta ocupada**: troque `--port 8012` nos dois lugares (uvicorn + `vite.config.ts:8` proxy).
- **Chat 500**: `ANTHROPIC_API_KEY` não configurada (`backend/app/chatbot.py:126`).
- **Chat 502**: rede/proxy corporativo — `truststore.inject_into_ssl()` (`backend/app/chatbot.py:22`) já usa store do Windows; tente `Invoke-WebRequest` para testar conectividade.
- **Geração com `Infinity`**: horas muito grandes que somadas estouram `float` viram `NonFiniteValueError → 400` (corrija horas).
- **Logo sumida em prod**: `frontend/public/logo*.png` deve existir antes do `build` (`frontend/vite.config.ts:1` `publicDir`).

---

## Por que `generator.py` não usa `openpyxl.save()`

`openpyxl` descarta `xl/drawings` e `xl/media`. Para preservar 100% (logo, caixas, fórmulas), `backend/app/generator.py:1` copia o `.xlsx` byte-a-byte e substitui só `xl/worksheets/sheet1.xml`, `xl/drawings/drawing1.xml`, `xl/workbook.xml`, limpando `calcChain.xml`.
