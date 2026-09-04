# Project Instructions — Automação de Relatório de Horas

## Tech Stack

| Camada | Tecnologia | Versão / Onde |
|---|---|---|
| **Language** | Python + TypeScript | 3.11+ / 5.6 |
| **Backend** | FastAPI + Uvicorn | 0.141.1 / 0.49 (`backend/app/main.py:40`) |
| **Excel** | openpyxl (leitura) + ZIP/XML manual | 3.1.5 (`backend/app/parser.py:7`, `backend/app/generator.py:1`) |
| **Frontend** | React 18 + Vite 7.3.6 + Zustand 4 + immer 10 | `frontend/src/`, `frontend/vite.config.ts:1` |
| **IA** | Anthropic SDK + truststore | 0.125 / 0.10.4 (`backend/app/chatbot.py:22`) |
| **Storage** | Sem DB/ORM — `tempfile.gettempdir()/relatorio_horas_output` (`backend/app/main.py:71`) para saída gerada; `backend/data/management_kpi.json` (fora do git) para os dados manuais do painel de gerência (`backend/app/management.py`) |

## Code Style

- **Python** `snake_case`, **TS/JS** `camelCase`, React `PascalCase`. Zustand store `useReportStore.ts:1` é fonte da verdade.
- **Erros**: usuário → `HTTPException(400/422)` (`backend/app/main.py:83`), template corrompido → `ValueError` 500 (`backend/app/generator.py:21`), IA → `ChatConfigError 500` / `ChatUpstreamError 502` (`backend/app/chatbot.py:27`).
- **Frontend**: `packages: WorkPackage[]` por `id` (não índice), `header: ReportHeader` global, `enableMapSet()` obrigatório para `Set` no immer (`frontend/src/store/useReportStore.ts:4`). Preview é espelho editável — nunca `innerHTML` com foco, só `textContent` pontual.
- **Validação**: `Field(..., allow_inf_nan=False)` (`backend/app/main.py:114`) + `_sanitize_nonfinite` (`:49`) evita `NaN/Infinity` virar `500`.
- **Imports backend**: relativos `from .chatbot import ...` (`backend/app/main.py:32`) para rodar como `backend.app.main`.

## Testing

- **Nenhum teste detectado** (`No tests found`) — ao adicionar usar `pytest` + `pytest.ini` (backend) e `Vitest` (frontend `utils/`).
- **Manual**: `python -m uvicorn backend.app.main:app --reload --port 8011` → `http://localhost:8011` (serve `frontend/dist` se existir). Teste rápido: `TestClient GET /` deve conter `id="root"` e `assets/index-`.
- **Parse fixture**: `backend/templates/exemplo_projectile.xlsx` (ignorado) — `POST /parse` deve retornar `1 pacote` em `single`.

## Build & Run

```bash
# instalar
pip install -r backend/requirements.txt
npm --prefix frontend install

# dev (2 terminais)
python -m uvicorn backend.app.main:app --reload --port 8011  # backend :8011
npm --prefix frontend run dev                               # frontend :5173 proxy vite.config.ts:8

# prod
npm --prefix frontend run build   # tsc -b && vite build → frontend/dist/
python -m uvicorn backend.app.main:app --port 8011  # serve dist em /
```

- **Env**: `cp .env.example .env` → `ANTHROPIC_API_KEY` (obrigatória p/ chat) e `ANTHROPIC_MODEL` (default `claude-sonnet-5` `backend/app/chatbot.py:68`). `load_dotenv()` sem path lê `.env` da raiz.
- **Launch**: `.claude/launch.json:7` `backend.app.main:app --port 8011`.
- **Lint**: não configurado.

## Project Structure

```
backend/
  app/
    main.py        # FastAPI, 3 rotas + NoCacheStaticFiles + mount (linha 311)
    parser.py      # parse_projectile_export(), _extract_package_key() :77, _parse_hs_value()
    generator.py   # generate_report() :461, feriados, BUSINESS_DAYS, ZIP/XML
    chatbot.py     # call_chat() :59, truststore.inject_into_ssl(); SYSTEM_PROMPT/TOOL_SCHEMA vêm de chat_ops.py
  templates/
    relatorio_final_template.xlsx  # 49KB, nunca recriar
  requirements.txt
frontend/
  index.html       # entry Vite <div id="root"> + <script type=module src="/src/main.tsx">
  vite.config.ts   # proxy /parse /generate /chat → :8011, build.outDir=dist
  tsconfig.json
  public/logo*.png # copiados para dist (publicDir)
  src/
    main.tsx, App.tsx
    api/types.ts   # WorkPackage, Group, Activity, RowIssue, ParseResponse, ChatState
    utils/{fmt.ts (fmtNum, parseLocaleNumber), calc.ts (computeGroupTotals), fileName.ts, theme.ts (THEME_ICONS)}
    store/useReportStore.ts  # Zustand+immer, snapshot JSON com Set→{__set}, split, drag, undo
    styles/index.css  # 38853 chars extraídos (visual idêntico)
    components/
      Header.tsx (theme toggle svg), LoginScreen.tsx, FileUpload.tsx (FormData), ValidationBanner.tsx
      PackageTabs.tsx (drag merge), PackageFileName.tsx
      Preview/Preview.tsx (2 panes, drop zone grupo) + PreviewSheet.tsx (drag atividade/grupo, marquee — inclui edição de cabeçalho/grupo)
      Chat.tsx (drag/resize, pushUndo), GenerateFooter.tsx (blob download)
      ManagementPanel.tsx (painel de gerência, KPIs mensais) + ManagementFilters.tsx, KpiCard.tsx, Gauge.tsx (SVG semicircular), ExtraHoursInput.tsx
```

## Conventions

- **Git**: histórico começou com `main` único branch, sem PR — PT-BR curtos, sem Conventional Commits. **A partir de 2026-09** (desde que `.github/workflows/ci.yml` existe): mudança pequena/óbvia pode ir direto pra `main`; mudança maior ou que mexa em CI/deploy/infra vai numa branch com PR, pra ver o ✅/❌ do Actions antes de mergear (evita repetir o incidente de levar um `ci.yml` quebrado direto pra `main`).
- **Nomes**: `snake_case` em Python, `camelCase` em TS, `PascalCase` para componentes. Arquivos `kebab` não usado.
- **Commits**: curtos, sem prefixo. Histórico raso — não inferir padrão estável.
- **Estilo frontend**: CSS vars `:root` / `:root[data-theme="light"]` (`frontend/src/styles/index.css:19`), preview sempre `#fff/#1a1a1a` (não usa tokens). `escapeHtml` não necessário em JSX (React escapa).

## Gotchas — leia antes de codar

- **NUNCA `openpyxl.save()`** em `generator.py` — destrói `xl/drawings`/`xl/media`. Sempre ZIP/XML (`backend/app/generator.py:1`).
- **`_extract_package_key()`** exige ` - ` com espaço ao menos de um lado (`backend/app/parser.py:77` `r"\s+-\s*|\s*-\s+"`); hífen colado (`Para-barro`) não é separador. Normaliza `–—−－` e `\xa0`.
- **Undo global** por `packageId` (não índice) — `splice`/`mergePackages` invalida snapshots, por isso `undoStack = []` após `removePackage`/`mergePackages` (`frontend/src/store/useReportStore.ts:390`). Snapshot serializa `Set` como `{__set: [...]}`.
- **Vite**: `frontend/vite.config.ts:1` sem `root` (é `frontend/`). Logos **devem** estar em `frontend/public/` para irem para `frontend/dist/` (Vite `publicDir`). Build hash em `assets/*`.
- **Cache**: `NoCacheStaticFiles` (`backend/app/main.py:19`) → `assets/*: public, max-age=31536000, immutable`, resto `no-store`. Se mudar para `web/`, quebra.
- **Foco no preview**: inputs `pv-input` são `border:none` transparentes; handlers nunca fazem `container.innerHTML =` com foco, só `textContent` pontual. Re-render com `key` estável.
- **NaN/Infinity**: `allow_inf_nan=False` + `_sanitize_nonfinite` evita `500` em erro de validação (`backend/app/main.py:49`).
- **Splitter**: `paneB` é singleton `useRef` + `useEffect` cleanup — recriar `pane` a cada `enterSplitMode` duplica listeners (`frontend/src/components/Preview/Preview.tsx:1`).
- **Python imports**: relativos (`from .parser import`) — rodar como `backend.app.main`, não `app.main`.

## Request Lifecycle

**Ex: `POST /parse` com `mode=single`**

1. `frontend/src/components/FileUpload.tsx:1` `FormData{file, mode} → fetch("/parse")` (dev via Vite proxy, prod mesma origem)
2. `backend/app/main.py:75` `parse_endpoint` salva `NamedTemporaryFile`, chama `parse_projectile_export(tmp, split_by_package)` (`backend/app/parser.py:109`)
3. `parser.py:101` `_find_header_row` procura `["Dados","Horário","Hs"]`; valida `Hs/Observação` (`:143`); loop `iter_rows` → agrupa por `Observação` `re.split(r"[-_]")`, soma case-insensitive, trata `Hs` `,`→`.`, extrai pacote ` _extract_package_key` se `multi`
4. Retorna `{packages, issues}` → `FileUpload.tsx` mapeia para `WorkPackage {id, key, projectCode, groups: [{id, name, performance, activities: [{id, description, hours}]}]}` + `collapsedGroupIds = Set(ids)` + `issues → ValidationBanner`

## Onde mexer

| Quero... | Arquivo |
|---|---|
| Mudar parse/agrupamento | `backend/app/parser.py:109` |
| Mudar geração/feriados | `backend/app/generator.py:165` (`_easter_sunday`), `:208` (`_business_days_per_week`) |
| Mudar cálculo horas | `frontend/src/utils/calc.ts:1` + `backend/app/generator.py:273` (devem espelhar) |
| Mudar IA prompt | `backend/app/chat_ops.py:17` `SYSTEM_PROMPT` |
| Mudar tema/layout | `frontend/src/styles/index.css:19` vars + `frontend/src/components/Header.tsx:1` |
| Adicionar rota API | `backend/app/main.py:75` + `BaseModel` com `allow_inf_nan=False` |
| Adicionar componente | `frontend/src/components/` + estado em `useReportStore.ts:15` |
| Mudar cache estático | `backend/app/main.py:19` `NoCacheStaticFiles` |
| Mudar proxy dev | `frontend/vite.config.ts:8` |

## API Contracts (não quebrar)

- `POST /parse` `multipart` → `{packages: [{key, project_name, groups: [{name, total_hours, activities}]}], issues}`
- `POST /generate` `json` `GeneratePayload` (`snake_case`) → `200 .xlsx` se `len==1` senão `200 .zip` com dedup `arcname (n)` (`backend/app/main.py:210`)
- `POST /chat` `json` `{message, state: ChatState (camelCase)}` → `{reply, state}` — valida `len(packages)` não mudou (`:296`)

## Tarefas comuns

- **Adicionar validação de linha**: `backend/app/parser.py:179` + `frontend/src/components/ValidationBanner.tsx:1` `ISSUE_HIGHLIGHT_PHRASES`
- **Adicionar campo cabeçalho**: `backend/app/main.py:122` `HeaderPayload` + `frontend/src/store/useReportStore.ts` `header` + `Preview/PreviewSheet.tsx` (`setHeaderField`)
- **Mudar performance/bruto**: `frontend/src/utils/calc.ts` + `backend/app/generator.py:273` `_build_groups_xml`
