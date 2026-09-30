# Project Instructions — Automação de Relatório de Horas

Este arquivo descreve o estado implementado do repositório e as regras para agentes que forem alterá-lo.

## Visão geral

Aplicação interna full stack para:

1. autenticar usuários no Projectile;
2. importar horas por XLSX ou MySQL;
3. revisar e editar relatórios;
4. gerar/enviar XLSX e PDF;
5. acompanhar horas pessoais (ou de um colaborador de engenharia, pra gerente/coordenador);
6. acompanhar e diagnosticar KPIs gerenciais e o status de envio dos relatórios;
7. automatizar ingestão de relatórios por Microsoft Graph;
8. editar/traduzir conteúdo com Anthropic;
9. consultar o histórico de relatórios gerados (versões, arquivos, auditoria);
10. analisar horas, faturado e envio em linguagem natural (Analytics e Chat analítico);
11. gerar automaticamente os rascunhos mensais de todos os projetos, pra revisão e aprovação (Geração automática).

O MySQL do Projectile é somente lido. Existe um SEGUNDO banco próprio,
`reports_db` (MySQL em container Docker, acessado via SQLAlchemy Core +
Alembic), que persiste histórico/versionamento de cada geração de relatório
— ver seção "Persistência de relatórios (reports_db)". Os dados do Painel
de Gerência/Diagnóstico também vivem no `reports_db` (tabelas `mgmt_*`,
antes em `backend/data/management_kpi.json`) — ver "Persistência
gerencial". As guias do frontend continuam em `localStorage`.

## Stack atual

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI 0.141.1, Uvicorn 0.49 |
| XLSX/PDF | openpyxl para leitura, ZIP/XML para escrita, ReportLab, pypdf |
| Banco Projectile | MySQL/PyMySQL (só leitura); senha via Windows Credential Manager/keyring |
| Banco reports_db | MySQL em Docker; SQLAlchemy Core + Alembic; senha via keyring. Guarda histórico de relatórios e os dados de Gerência/Diagnóstico |
| Frontend | React 18, TypeScript 5.6, Vite 7.3.6, Zustand 4, immer 10 |
| IA | Anthropic SDK + truststore; Jev (TypeSafe AI, API oficial `api.typesafe.ai`) só no chat analítico, por HTTP (`integrations/jev.py`) |
| E-mail | Microsoft Graph via MSAL |
| Testes | pytest + Vitest |

## Regras que não podem ser quebradas

### Geração XLSX

- **Nunca use `openpyxl.save()` no caminho de geração.** Ele pode remover `xl/drawings` e `xl/media` do template.
- `backend/app/generator.py` copia o template e altera ZIP/XML diretamente.
- `backend/templates/relatorio_final_template.xlsx` é a fonte da verdade e não deve ser recriado por código.
- Mantenha os cálculos equivalentes entre `frontend/src/utils/calc.ts`, `generator.py` e `pdf_generator.py`.
- **Relatório nunca mostra Bruto/Performance** (decisão do usuário, 2026-09-28), por nenhum meio: download, envio, aprovação e envio da geração automática. `services/report_files.build_report_file` — a porta única de saída de XLSX/PDF — sempre gera com `include_performance=False` e nem aceita o parâmetro; o campo `include_performance` dos payloads é aceito por compatibilidade (guias antigas) e ignorado. A opção saiu das telas (rodapé de Gerar, barra da guia automática, padrão geral e configuração do projeto). A performance continua no CÁLCULO (horas = bruto × performance); só a exibição dela no arquivo não existe. Os geradores (`generator.py`/`pdf_generator.py`) ainda sabem desenhar as colunas (testados direto), mas nada no app pede isso — não reative sem decisão explícita. Teste: `test_no_performance_in_files.py`.
- Preserve os metadados/markers de identidade, total e `pacote_scope`; `email_ingest.py` depende deles.

### Identidade e autorização

- `/parse-db` sempre usa a identidade da sessão; nunca aceite `employee_id`/nome vindo do cliente para consultar outra pessoa. As horas pessoais (`fetch_employee_hours`/`fetch_my_hours`/`fetch_daily_hours_totals`) são buscadas SÓ por `employee_id` (`tjob.pEmployee`); não existe busca por nome (`capEmployee LIKE` casava homônimos). Sem vínculo em `temployee`, `EmployeeNotLinkedError` → 409 com instrução clara.
- `/my-hours` usa a sessão por padrão. **Única exceção deliberada:** `?employee_id=` de outra pessoa, só pra gerente/coordenador (colaborador → 403) e só pra alguém de engenharia (CAD+CAE com apontamento na janela do histórico; fora disso → 404). O id do cliente nunca é usado direto: `my_hours._resolve_target` re-resolve contra `fetch_engineering_employees`, e nome e **filial** (que decide o feriado municipal de Santo André) vêm do Projectile, não do cliente. Lista do seletor: `GET /my-hours/employees` (cache de 15 min, sem filial no payload).
- Três papéis: **gerente** (`MANAGEMENT_PANEL_LOGINS`, acesso a tudo), **coordenador** (`COORDINATOR_LOGINS`) e colaborador (o resto). Allowlists e checagens ficam em `core/authz.py` (lidas de `core.config.Settings`; consumidores chamam `is_manager`/`roles_for`, nunca importam os sets — ver "API — routers").
- Coordenador: Gerar relatório (inclusive busca por cliente/projeto), Dashboard de horas, o **próprio** Histórico e o Diagnóstico. Nunca Painel de Gerência nem Analytics, e **nunca os KPIs nem pela API**: o Diagnóstico dele usa `/management/send-status` (sem horas/faturamento/performance, resposta montada por lista branca `_SEND_STATUS_KEYS`), e `/management/kpis` responde 403. **Período do Diagnóstico:** gerente vê todos os anos; coordenador só os últimos 12 meses e o ano atual — `send-status` com outro `year`/`months` responde 403 (`_check_coordinator_period`), e `/management/kpis/samples` devolve só amostras/mensagens puladas desses meses (`_coordinator_months`).
- **Janela de período de quem NÃO é gerente** (coordenador E colaborador, decisão do usuário de 2026-09-28): só os **últimos 12 meses e o ano atual** (1º dia de 11 meses atrás até 31/12 do ano atual; o "ano passado" que o coordenador via saiu) — nada fora disso se vê nem se filtra, em nenhuma tela. Regra única em `api/period_access.py` (`window`, `window_for` = None pro gerente, `check_range`/`check_month` → 403, `in_window`, `allowed_months`), aplicada no backend em: `/parse-db` e `/parse-db-client` (período pedido), `/management/clients-with-hours`, `/management/client-projects`, `/management/projects/{id}/packages`, criar/editar/apagar amostra (o mês novo E o da amostra existente), `send-status`/`kpis/samples`; `/my-hours` corta o histórico de 400 dias no início da janela (série mensal com 12 pontos, dias atípicos e referência só da janela, `comparison` = None quando a janela anterior cai fora — `hours_analytics.day_matched_comparison(not_before=)`); Histórico (`list_reports(competence_from=)` pela `competence_start`, ou `created_at` sem competência; detalhe/versões/arquivos de relatório fora da janela = 404); "Minhas revisões" (`competence_from` em lista, contadores, abrir, salvar, mandar). Frontend só oferece o permitido: `utils/period.ts` (`periodWindow`, `reportYearOptionsFor`, `monthOptionsFor`) no seletor de período do Gerar relatório, `periodOptionsFor(false)` = últimos 12 meses + ano atual. `/management/projects/{id}/all-packages` (popup de Fechados) continua sem corte: só nomes de pacote, fechar é atemporal. Testes em `test_period_window.py`. O filtro de Período do frontend usa `periodOptionsFor(isManager)` (`useManagementStore.ts`), que também volta pra "Últimos 12 meses" quando um coordenador herda na mesma aba um ano que o gerente escolheu.
- Só gerente (`require_manager`): `/management/kpis`, `/management/kpis/check-emails`, `PUT /management/kpis/{month}`, `/analytics/summary`, `POST /analytics/chat`, `/auto-generation/*`. `/my-reviews/*` é de qualquer sessão, mas filtrado pelo login dela (item atribuído a outra pessoa = 404). Gerente ou coordenador (`require_manager_or_coordinator`): `/parse-db-client` e as demais rotas `/management/*` (amostras, projetos, pacotes, Fechados, `send-status`).
- `backend/tests/test_coordinator_access.py` tem uma **matriz de autorização para TODAS as rotas** (`_all_api_routes` achata os `_IncludedRouter` do FastAPI 0.141): cada rota cai numa classe declarada — `session` (padrão), `manager` (`_MANAGER_ONLY`), `manager_or_coordinator` (`/management/*`, `/parse-db-client`, `/my-hours/employees`), `translate` ou `public` (lista explícita). Rota nova com dependência de acesso fora do padrão faz o teste falhar — decida e atualize a lista certa.
- `/translate-activities` exige `require_translate_access`.
- Não exponha distinção entre usuário inexistente e senha incorreta.
- Não habilite Swagger/ReDoc/OpenAPI sem uma decisão explícita de segurança.

### Estado do frontend

- `useReportStore.ts` é a fonte de verdade da guia ativa.
- Pacotes, grupos e atividades são identificados por `id`, nunca por índice persistente.
- **Chat de IA usa `id` estável de grupo/atividade** — `ChatGroup`/`ChatActivity` (`api/routers/chat.py`) exigem `id`; `chat_ops.py` localiza o alvo das operações por `groupId`/`activityId`, nunca por nome/descrição. `add_group`/`add_activity` geram `id` novo no backend (`uuid4()`), que o frontend só precisa aceitar (`applyChatState` casa por `id`, não mais por nome+índice).
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
- **Analytics** (`GET /analytics/summary`) agrega horas/tempo de
  geração/taxa de falha só sobre a VERSÃO ATUAL de cada relatório
  (`report_versions.id = reports.current_version_id`) — nunca soma
  versões substituídas junto com a vigente. Sem fail-open (mesmo
  princípio de `report_queries.py`: função só de leitura, falha vira 502).
  Fica esparso/vazio até acumular meses de uso real — isso é esperado,
  não um bug.

### Chat analítico (`backend/app/analytics/`)

Aba "Chat analítico", só gerente (`POST /analytics/chat`, `POST /analytics/chat/export`). Separado do `/chat` de edição: nunca mexe no relatório aberto.

- **Nunca SQL gerado por IA.** Horas, faturado e status de envio são uma **consulta cruzada** (`crossquery.py`): até 4 medidas × até 2 dimensões, filtros com vários valores, período, top N, ordenação e corte por valor ("menos de 100 h"). Quem monta a consulta (atalho do Jev ou planner do Claude) só escolhe NOMES do catálogo (`catalog.py`) e valores das listas de opções; `crossquery.build_spec` descarta o resto com um aviso em português (nunca em silêncio) e `execute` calcula em Python. Relatórios gerados (`reports_db`) continuam em intents com handler fixo (`query_engine.py`).
- **Três conjuntos de dados** (`catalog.DATASET_DIMENSIONS`, `facts.DataSources`): `hours` (apontamentos CAD+CAE: cliente, projeto, colaborador, pacote, mês, centro de custo, faturável/não faturável por `pExternal`), `billing` (trabalhado x faturado por cliente/projeto/mês — faturado vem de `mgmt_kpi_samples`, que é POR PROJETO: não existe faturado por colaborador nem pacote) e `send_status` (linha a linha de `management.compute_monthly_kpis`, a mesma função do Diagnóstico). Medidas de fontes diferentes não se misturam numa consulta.
- **Mesmas regras do Painel/Diagnóstico, conferidas nos dados reais** (125 células, 0 diferenças; auditoria de 2026-09-24): janela = a do Painel (`DataSources`, mesma chave de cache de `_get_cached_rows`); período vai até o **fim do mês**, não até hoje (o Painel conta apontamento com data futura no mês corrente — medido: 32 h em setembro/2026). Faturado: amostras sem duplicada; ajuste manual do gerente só no total mensal SEM recorte de cliente/projeto. Resultado/performance: faturado x TUDO o que foi trabalhado no mesmo recorte e mês (igual ao Painel filtrado por cliente); mês/recorte sem nenhum relatório recebido fica de fora (não vira -100%), com aviso de quantos. O TOTAL de uma consulta de faturado é sempre o número do Painel pro recorte (célula = mês), mesmo com linhas por projeto/cliente.
- **Jev (TypeSafe AI) só escolhe entre opções**: cada filtro é uma pergunta `choice` com opções montadas a cada chamada (meses, clientes, colaboradores, projetos). Cada intent de horas/faturado/envio é só um ATALHO (`IntentSpec.preset`) pra uma consulta cruzada. Jev fora do ar, sem chave (`TYPESAFE_API_KEY`) ou sem confiança → o Claude classifica com `tool_choice` forçado e enums. Confiança (`router._weakest`): rota e toda escolha de valor precisam de `JEV_MIN_CONFIDENCE` (0,60); "nenhum" precisa só de `JEV_MIN_CONFIDENCE_NONE` (0,40). Desenho calibrado contra o Jev real, não mude sem recalibrar: mês e período relativo são UMA pergunta `period`; a pergunta anterior NÃO vai no `state` da mensagem (ele herdava a métrica anterior) — vai só numa 2ª chamada paralela que decide `follow_up` (`router._ask_jev`); as `criteria` dizem "ONE total" vs "A LIST".
- **Travas determinísticas** (`signals.py`, medidas nas calibrações — não troque por IA): (1) `needs_planner` — pergunta com "por/cada + dimensão" que o atalho não cobre, corte por valor, top N, "x/versus" ou "só faturáveis" vai pro planner (o Jev escolhia o atalho mais parecido e perdia a quebra: "pessoas EM CADA CLIENTE" virava só a contagem); intent vazia numa rota de dados também vai pro planner; (2) `looks_like_follow_up` — continuação só vale se o texto tem cara de continuação ("e ...", "isso/esse/mesmo período" ou ≤ 3 palavras): o Jev e o Claude marcavam pergunta completa como continuação e ela herdava filtro e período; a pergunta anterior só vai pro planner quando é continuação; (3) `mentions_period` — período só vem do TEXTO (ou da anterior, se continuação): o Claude copiava o período da pergunta anterior numa pergunta nova. (4) Nome de projeto pela metade → filtro "nome contém" (`QuerySpec.project_match`, frases resolvidas contra as opções em `build_spec`, sem teto de quantidade; `matched_projects` não vai pro contexto). O Projectile abre UM projeto por mês pro mesmo trabalho ("Legislation Package - Estribo", "... 07.2026"…; "Legislation Package" são 38 projetos): `signals.family_phrases` — as palavras da pergunta que estão no nome do projeto escolhido pelo Jev/planner viram a frase ("estribo 08.2026" continua um só; "projeto"/"de" não contam); `signals.detect_project_phrase` — sem projeto escolhido, trecho da pergunta que aparece SEGUIDO no nome de algum projeto ("horas legislation package" somava os 87): 1 palavra só depois de "projeto" ("horas CAD" é centro de custo, não os 8 projetos com CAD no nome), nunca só vocabulário do chat nem nome de cliente/colaborador. O recorte da resposta diz "projetos com “Estribo” no nome (4)". Com filtro por nome de projeto e sem "por/cada projeto" nem "A x B" na pergunta, a quebra por projeto sai (`_without_unasked_project_split`): o planner às vezes quebrava "nos projetos X, mês a mês" por projeto também, e com um projeto por mês virava um pico por linha. `signals.single_cost_center` / `signals.only_billing_type` — pergunta que cita só CAD ou só CAE, ou pede "só/somente/apenas faturáveis", filtra por isso quando o planner esquece ou devolve valor inválido ("all"); "quanto foi não faturável" é MEDIDA e não vira filtro (daria 100%). (5) Continuação herda também filtro de VÁRIOS valores e a frase de projeto da consulta anterior (`c.inherited`, de `last_spec`): `last_filters` só guarda um valor, e "e durante o ano?" depois do Estribo respondia o time inteiro. Vale também quando o planner copia só um pedaço do recorte sem a pergunta citar o nome; não vale se a pergunta pede o todo (`asks_everyone`: "todos", "geral", "time"). `obviously_follow_up` — até 5 palavras começando com "e"/"agora" é continuação mesmo que o classificador diga que não. Anos também são sem IA (`periods.years_mentioned`, `signals.year_phrases` pra "no ano"/"durante o ano"/"ao longo do ano"/"ano todo"/"ano passado"): ano fora da janela → resposta fixa com a janela, sem consulta; ano sem nenhum nome de mês → o ano inteiro, cortado na janela com aviso — e ele tem prioridade sobre o período relativo que o classificador escolheu (o Jev marcava "último ano" pra "no ano") e sobre o período do planner (os dois caminhos dão o mesmo período). "No último ano" continua sendo os últimos 12 meses. Sem período → últimos 12 meses, com aviso. Se o planner esquece o período que o Jev já tinha achado, vale o do Jev. (6) **"Em relação ao total"** (caso real de 2026-09-28: "horas do Lucca na Mercedes em relação ao total, mês a mês" devolvia só as horas na Mercedes — com os dois filtros aplicados o total dele nunca era calculado): medidas `total_hours` ("Horas no total" = a MESMA consulta sem o filtro `QuerySpec.share_of`) e `share_percent`, calculadas em `crossquery._fill_share` (a base não quebra pela dimensão que saiu dela — senão "CAD por centro de custo" dava 100%). `signals.asks_share`: forte ("em relação ao total", "do total", "participação", "proporção", "representa", e verbo/preposição de comparação + até 4 palavras + total: "comparado às horas totais", "em comparação ao total", "versus o total"; caso real de 2026-09-29, quando só a 1ª forma era reconhecida e a pergunta caía num aviso de "falta recorte" com o recorte presente) — se a frase não bate mas o planner já montou `total_hours`/`share_percent`, vale a comparação dele e `_with_share` escolhe a base; sem nenhum recorte a consulta segue como veio — ou fraco ("percentual das horas…", ignorado se a consulta já tem medida em %, como "% não faturável"); "no total" NÃO conta ("quantas horas no total" = somando tudo). `service._with_share` decide o que sai da base pelo TEXTO — o trecho depois do último "total"/"das horas"/"nas horas" (`signals.share_base_text`) diz o que FICA ("quanto o Lucca representa das horas DA MERCEDES" → sai o colaborador), e isso vence a escolha do planner (que errava esse caso); sem pista, a ordem é projeto > cliente > pacote > centro de custo > tipo > colaborador (o colaborador costuma ser o sujeito). Só as quebras pedidas no texto ficam (o planner quebrava "em projetos da Mercedes" por projeto → 100% em toda linha); se o texto diz que todos os filtros ficam na base ("participação de cada cliente nas horas do Lucca"), vira a coluna "% do total" de sempre. Conferido com dados reais (Jev + Haiku, 2 rodadas iguais): base = exatamente as horas do colaborador sem filtro; 6 perguntas antigas com a mesma rota e números.
- **Rotas:** `simple_data` (atalho → consulta cruzada → texto fixo, **0 Claude**), `simple_with_explanation` (Claude explica o resultado já agregado), `analysis` (planner com UMA ferramenta por análise, `tool_choice: any`: `query` = consulta cruzada inteira; `compare_periods` = uma medida em dois períodos DIFERENTES, variação em Python — mesmo período dos dois lados é rejeitado, ordem invertida é corrigida), `general`, `out_of_scope` (recusa fixa). Comparar itens entre si num período ("Mercedes x Lauer") é `query` com os itens no filtro. Ferramentas separadas: com um formulário único misturando campos, o Haiku se confundia (1 em 5); separado, 30/30.
- **Saída determinística** (`cross_output.py`): a forma do resultado decide o gráfico (sem dimensão → `kpi`; mês → `line`; tipo/centro de custo/status → `donut`; ranking → `horizontal_bar`, agrupada com várias medidas; 2 dimensões com mês → `line` multissérie ou `heatmap` com muitas linhas; 2 categorias → barra empilhada, ou `heatmap` pra medida que não soma). No máximo 5 séries com cor própria + "Outros", mesmo que o resto seja um item só (com 6, a 6ª repetia a cor da 1ª); o renderer também manda índice ≥ 5 pro cinza de "Outros" — a paleta nunca cicla. Tabela cruzada (linhas × colunas + totais) quando há 1 medida e poucas colunas; "Total exibido" quando o top N cortou grupos. Grupos todos zerados não entram (a série mensal é a exceção, contínua com zero).
- **Grounding** (`grounding.py`): texto do Claude com número que não veio dos dados é descartado e vale o texto determinístico (`metadata.claude_text_used = false`). Não afrouxe isso. O Claude recebe as contas que tentaria fazer de cabeça já prontas (participação, acumulado, `top_3`, `others_after_top_3`, total por dimensão — `cross_output.compact_for_claude`): sem isso ele somava percentuais, errava, e o grounding descartava 4 de 4 textos; com elas, 11 de 12.
- **Exportação** (`export.py`, `POST /analytics/chat/export`, só gerente): a tabela JÁ exibida vira .xlsx — não consulta nada. Número continua número no Excel (formato por `column_types`), texto que parece fórmula continua texto (`data_type = "s"`). Não é o caminho de geração de relatório: aqui não há template, `Workbook.save()` é seguro.
- Contexto de conversa sem estado no servidor: o frontend devolve `{conversation_id, last_intent, last_filters, last_spec}` (validado por `schemas.py`, `extra="forbid"`; `last_spec` ainda é revalidado por `build_spec` como se viesse do planner). Toda pergunta vai pro `audit_log` (`action="analytics_chat_query"`), com rota, intent, consulta montada (`spec`), classificador, chamadas e tokens do Claude e latência.
- Falha do Claude nunca derruba uma resposta que já tem dado: cai no texto determinístico. Projectile fora do ar derruba só horas/faturado/envio (502); relatórios seguem. `mgmt_*` fora do ar → 502 de gerência (faturado/envio).
- **Calibração ponta a ponta** (2026-09-24, Jev + Haiku + dados reais): 30 perguntas de cruzamento + 12 inéditas; na 3ª rodada, 42/42 com rota, consulta e números certos. Latência: atalho do Jev ~0,5 s; planner ~3–6 s; 1ª pergunta da janela ~22 s (carga das horas, cache de 15 min).

### Geração automática (`backend/app/auto_generation/`)

Aba "Geração automática", só gerente (`/auto-generation/*`, todas `require_manager` e todas em `_MANAGER_ONLY`). Gera no servidor os rascunhos mensais de **todos os projetos com horas** numa competência, com o que foi ajustado no mês anterior já aplicado, e o gerente revisa no editor de sempre e aprova. Plano em fases: 1 (feita) gerar/abrir/aprovar; 2 (feita, sem o cabeçalho `X-Auto-Report-Id`) envio; 3 (feita) revisão por colaborador ("Minhas revisões"); 4 (feita) agendador; 5 IA. Decisões do usuário (2026-09-28): o **número do relatório o gerente digita** (a memória só sugere); revisão no editor atual; envio é um clique do gerente, separado da aprovação; avisos só no app; **padrão = um relatório por projeto** (`rules.DEFAULTS["mode"] = "projeto"`, sem escopo de pacote); **cada projeto é um bloco próprio na tela, com configuração individual**.

- **Rascunho NÃO vai pro histórico até a aprovação.** A identidade em `reports` é `hash(número, escopo, competência)` e o rascunho nasce sem número — todos os do mês colidiriam num `report` só. Ele vive em `auto_reports.draft_json` (formato do editor: pacotes/grupos/atividades com `id` e `source_key`) e só na aprovação vira relatório do histórico (`report_persistence.begin_generation(..., created_from="auto_approval")`, fail-open como o `/generate`).
- **Envio ao cliente** (fase 2, `service.send_report`, `GET/POST reports/{id}/send`): só de `aprovado` (ou `enviado`, pra mandar de novo). Anexos = `approved_files` (payload **congelado**, o mesmo de "Arquivos"). Sai por `email_ingest.send_report_email` da caixa do e-mail da SESSÃO (nunca do cliente), com a caixa do agente sempre em cópia — agora com listas `to`/`cc_emails` (o `/send-report` continua mandando pra um só). **Envio incerto** (`send.py`): a tentativa (`send_attempt`) é gravada e confirmada ANTES do Graph (sem conseguir gravar, não envia). Desfecho: Graph aceitou → `sent` (falha ao registrar depois disso NÃO vira "não enviado": fica incerto, `SendUncertain` 409 "o e-mail FOI enviado, não envie de novo"); Graph recusou com 4xx → `send_failed` (provadamente não saiu, pode reenviar); timeout/queda/5xx (`EmailIngestError.maybe_delivered`) → incerto. A ÚLTIMA ação entre `send_attempt/sent/send_failed/send_resolved` manda: tentativa sem desfecho = `send_uncertain` no item da lista e todo envio (único ou em lote) é recusado com 409 até o gerente confirmar com `POST reports/{id}/send/resolve` (`{resolution: "sent"|"not_sent"}`; `sent` marca `enviado` sem mandar nada, `not_sent` libera) — na tela, o aviso `UncertainSend` com "Chegou"/"Não chegou". Sem migration (usa a linha do tempo `auto_report_events`). Só vira `enviado` depois que o Graph aceitou; Graph fora → 502 genérico e continua `aprovado`. Um envio por relatório de cada vez (`_sending`, trava em memória — processo único). Destinatários ficam em `auto_memory.recipients` da família (gravados no envio; `memory.extract` os carrega na aprovação seguinte) e abrem preenchidos no mês seguinte. `GET …/send` avisa `counts_in_diagnostics = false` quando o remetente não está em `ALBERTO_EMAIL` (o Diagnóstico não contaria o envio). Lista traz `last_sent` (`{to, cc, actor_name, created_at}`).
- **Aprovados em massa** (decisão do usuário, 2026-09-28): bloco `aprovado`/`enviado` **não mostra "Configuração"** e tem um checkbox no canto inferior direito; com seleção aparece a barra fixa (`.auto-bulk-bar`) com Enviar ao cliente, Ver, Baixar e Reabrir (nessa ordem; no bloco, "Enviar ao cliente" vem antes de "Ver"). Baixar = `GET /auto-generation/files?ids=…` (um ZIP; um não aprovado recusa o lote inteiro, 409). Enviar em lote = `BulkSendModal`, com duas opções: **um e-mail por relatório** (padrão; destinatários do último envio de cada um, assunto/mensagem padrão, um que falha não para os outros) ou **todos num e-mail só** (`POST /auto-generation/send` → `service.send_reports`, que é o mesmo caminho do envio único: destinatários = união dos lembrados de cada projeto, um anexo por arquivo com nome único, tudo-ou-nada — um não aprovado ou sem o formato escolhido recusa o e-mail inteiro antes de chamar o Graph; os destinatários ficam na memória de cada família enviada; o evento `sent` guarda `combined_with`). Reabrir vale pra aprovados e enviados (a confirmação avisa quantos já estão com o cliente). Seleção zera ao trocar de competência.
- **Avisos por e-mail** (fase 4, `notifications.py`): imediatos e fail-open — revisor recebe quando um relatório é atribuído a ele (`assign_reviewer`) ou devolvido com comentário (`return_to_reviewer`); os gerentes recebem quando fica aguardando aprovação (`submit_review`). Destinatário é SEMPRE resolvido no Projectile por login (`fetch_user_emails`), nunca vem da tela; remetente é a caixa de quem agiu (fallback `GRAPH_MAILBOX`). Sem `AZURE_CLIENT_ID` ou com `notify_email=false` no Padrão geral, é no-op. O link (`APP_BASE_URL`) abre a guia certa direto no editor (`App.tsx` lê `?view=&report=` no boot) e o título da aba mostra `(n)` pendências.
- **Revisão por colaborador** (fase 3): o gerente atribui um revisor no bloco (`PUT …/reviewer`); a lista vem de `projectile_db.fetch_engineering_employees` (CAD+CAE com apontamento nos últimos 6 meses, cache de 15 min) e o login vindo da tela é **re-resolvido contra ela** — nome gravado é o do Projectile (`service._resolve_reviewer`, mesmo princípio de `/my-hours`). O login do revisor é `temployee.pLogin`, o da sessão é `auser.rLogin` (o login do app faz o join por eles; conferido nos dados reais: 26 de 26 batem) — comparado sem diferenciar caixa. O revisor usa `/my-reviews/*` (`require_session`, **só os atribuídos a ele; de outra pessoa é 404, não 403**): edita em `em_revisao`/`devolvido` e manda pra aprovação (`submit` → `revisado`, observação opcional). No salvamento do revisor, **número e arquivos ficam os do servidor** (`_keep_manager_fields`) — são do gerente. O gerente aprova (de qualquer estado editável, com ou sem revisor) ou devolve (`return`, comentário obrigatório → `devolvido`). Trocar o revisor de um `revisado` volta pra `em_revisao`; quem saiu perde o acesso na hora. Atribuir/devolver/mandar não mudam `draft_version` (o rascunho não muda). A memória lembra o revisor na aprovação e o rascunho seguinte da família já nasce atribuído. **Mês atual (prévia, sem rascunho):** o revisor escolhido no bloco vai pra regra da família (`reviewer_login`; `set_family_rule` resolve o login na lista e grava o `reviewer_name` do Projectile, ignorando o do cliente) e vale na geração deste mês e dos próximos — prioridade: regra do projeto > revisor lembrado na memória. `preview` devolve `remembered_reviewer` pra tela mostrar o padrão.
- **Agendador da rodada mensal** (fase 4, decisão do usuário, 2026-09-29: **ligado, dia 1, 06:00, America/Sao_Paulo**; `auto_generation/scheduler.py`): gera os rascunhos do **mês que fechou** — e os pedidos personalizados, que `_execute_run` já leva junto — sozinho. **Só gera rascunhos; nunca envia.** `decide(now_local, config, run, pending, state)` é PURA: alvo = mês ANTERIOR ao de agora; vence quando `now_local >= dia D às HH:MM` do mês atual (`schedule_day` 1–28, `schedule_time` "HH:MM", `schedule_enabled` — só no padrão global, `rules.GlobalConfig`, nunca por família; editados no "Padrão geral"); dispara se não há rodada do alvo (`sem_rodada`), se ela terminou `failed` ou está `running` há mais de 30 min (`rodada_falhou`) ou se há pedido personalizado `agendado` do alvo (`pedidos_pendentes` — pedido em `erro` sozinho NÃO retriggera). **Recuperação:** servidor desligado no dia → dispara quando voltar; o alvo é sempre o mês anterior, então um mês perdido não roda sozinho depois que o seguinte começa (o botão continua lá) — atenção ao subir num servidor onde o mês que fechou nunca rodou: ele roda na hora. **Sem martelar:** uma tentativa por hora e no máximo 5 por competência (`auto_settings["scheduler_state"]` = `{competence, attempts, last_attempt_at}`). `tick()` lê o estado, decide, grava a tentativa e chama `service.start_run(alvo, {"login": "sistema"}, background=False)` (que já é idempotente e seguro entre processos: `auto_runs.competence` UNIQUE + `FOR UPDATE`, `RunInProgress` não vira erro); `loop()` acorda a cada 5 min e nunca morre por um ciclo ruim; `main._start_auto_scheduler` guarda a task. Auditoria: `auto_run_scheduled`; `auto_runs.triggered_by = "sistema"` (a tela mostra "Rodada gerada automaticamente"). `GET /auto-generation/config` e `/competences` devolvem `schedule` (`{enabled, day, time, timezone, next_at "…-03:00", target, target_label, last_run}`, `scheduler.schedule_info`); a tela mostra a próxima geração no cabeçalho e o liga/dia/hora no Padrão geral. **`AUTO_GENERATION_ENABLED=false`** (`core/config.Settings`) é a chave de emergência que para o loop por fora; `conftest._no_auto_scheduler` o desliga nos testes. Precisa de `tzdata` (o Windows não traz a base de fusos). Testes em `test_auto_scheduler.py` (a decisão é testada sem relógio nem banco, incluindo a virada de fuso e a de ano).
- **Geração personalizada** (decisão do usuário, 2026-09-29; `auto_generation/custom.py`, migration `0008`): relatório de um RECORTE LIVRE — colaborador, cliente, projeto e pacote de trabalho, misturados — que entra na MESMA esteira (revisor, aprovação, envio, envio em massa, reabrir, histórico). **Configuração do projeto herdada** (decisão do usuário, 2026-09-29; `custom._config_for`): o relatório personalizado usa a MESMA configuração dos mensais por projeto — assinantes, arquivos (XLSX/PDF) e revisor da regra da FAMÍLIA (`auto_rules`, com `auto_families` manual e valendo em vários meses), com o padrão geral onde o projeto não define; revisor = o da regra, senão quem revisou o último aprovado (`auto_memory.reviewer`), e o revisor escolhido no pedido vence os dois. Com projetos de configurações DIFERENTES no mesmo relatório vale o padrão geral, sem revisor, e a prévia/`warnings` avisa ("os projetos deste relatório têm configurações diferentes (…): valeu o padrão geral"); com `split_by = projeto` cada relatório leva a do seu projeto. NÃO herda memória de nomes/performance/descrições nem ignora projeto fechado/desligado (o recorte é escolha explícita do gerente). **Configuração PRÓPRIA do personalizado** (o painel "Configuração", o mesmo dos projetos, no pedido agendado e no relatório gerado que ainda é rascunho; sem "Gerar relatório deste projeto"): `scope.config` (`CustomConfig`: `signer1_name`/`signer1_company`/`signer2_name`/`signer2_company`/`formats`; vazio = herda) vale POR CIMA da do projeto e essa por cima do padrão geral, e o "Relatório" é o `scope.package_unit` (mesmo "um relatório por projeto / por pacote de trabalho" do modal). O que o pedido define não conta como "configurações diferentes". `PUT custom/requests/{id}/config` (vale quando a rodada gerar) e `PUT custom/{report_id}/config` (`{package_unit, config}`; o rascunho NÃO muda sozinho: a tela oferece "Regenerar"; aprovado/enviado 409 "reabra antes", mensal 409); `_public` expõe `label`/`summary`/`package_unit`/`config`/`blocks` (o recorte em si — ids — continua só do gerente). **Cartão do pedido** (`CustomRequestCard`): mostra o pedido inteiro — os recortes em NOMES, um por linha (`blocks` = `custom.describe_blocks`: clientes, projetos ESCOLHIDOS, pacotes, colaboradores; gravado no pedido e em `scope_json.blocks`; pedido de antes do campo é completado uma vez por `_backfill_request_blocks`), período, como separa a lista, relatório por projeto/pacote, revisor, chips da configuração própria, quem agendou e quando será gerado. `blocks` NUNCA vai pro revisor (`_without_blocks` em `my_reviews`/`review_detail`): quem entrou no recorte é do gerente. **Só o MÊS ATUAL e AGENDADA** (decisão do usuário, 2026-09-29): a geração personalizada NÃO cria rascunho na hora — `POST /auto-generation/custom` (`service.schedule_custom`) só confere o recorte (colaborador na engenharia, pacotes com um projeto, revisor na lista) e guarda um **pedido** em `auto_settings`, na chave `custom_requests:AAAA-MM` (lista de `{id, scope, title, reviewer_*, label, summary, status: agendado|erro, error, created_*}`, sem migration); período diferente do mês atual → 400 ("vale só pro mês atual"). Os rascunhos nascem **junto com os projetos da rodada dessa competência**: `_execute_run` chama `generate_custom_requests(competence)` (só na rodada completa — "gerar só estes projetos" não leva os pedidos), que roda `create_custom` por pedido; pedido que deu certo sai da fila (os relatórios aparecem em "Personalizados", `kind = "avulso"`, `competence` = a da rodada), o que falhou (recorte sem horas, revisor que saiu da engenharia…) fica com `status = "erro"` e o motivo, sem derrubar os outros nem a rodada, e a próxima rodada tenta de novo; rodar de novo não duplica. `DELETE /auto-generation/custom/requests/{id}` cancela um pedido que ainda não virou rascunho. `GET /auto-generation/custom` devolve `{items, counts, requests}`. O gatilho do "primeiro dia do mês" é o **agendador** (abaixo): o pedido espera a rodada da competência, que ele roda sozinho (ou o gerente, pelo botão). A prévia (`POST custom/preview`) mostra o que sairia com as horas DE AGORA e é opcional. O backend (`custom.py`) ainda sabe vários meses e a junção por família, mas a tela só oferece o mês atual. Botão "Nova geração personalizada" no cabeçalho da aba (o modal termina em "Agendar geração"); a lista fica na opção **Personalizados**, com os pedidos agendados no topo (`CustomRequestCard`: agendado/erro na rodada, "Cancelar") do seletor (`selected = "custom"`, `CUSTOM_KEY`; a tela reaproveita a da rodada, com um `run` fictício). O recorte é uma lista de **blocos**: dentro de um bloco os filtros (`clients`, `project_ids`, `packages`, `employee_ids`) se CRUZAM ("o Lucca nos projetos da Mercedes"); entre blocos as horas se SOMAM, e a mesma linha de lançamento conta uma vez (união como multiconjunto: só o que outro bloco repete é descartado; dois lançamentos iguais no mesmo bloco continuam dois). Pacotes só valem com exatamente UM projeto no bloco. Dois eixos independentes: `split_by` (`nenhum` = um relatório com tudo, `projeto`, `pacote`, `colaborador`) diz QUANTOS relatórios saem; `package_unit` (`projeto` = cada projeto é um pacote e o pacote de trabalho vira o grupo; `pacote` = cada pacote de trabalho é um pacote e o prefixo da observação vira o grupo, como na busca manual em modo pacote) diz o que vira "pacote" DENTRO de cada um. Mais de 100 relatórios por geração é recusado; período de até 36 meses no backend; gerente sem janela. Fonte das horas: `projectile_db.fetch_custom_hours` (mesmos filtros de `fetch_project_hours` — CAD+CAE, `sysClientId`, `pDeleteFlag` — com `employee_ids`/`project_ids` opcionais e `employee_id`/`person`/`inicio`/`fim` na linha); o `employee_id` da tela nunca é confiado (tem que estar na lista de engenharia) e os nomes vêm do Projectile. **Linha de `auto_reports`:** `kind = "avulso"` (`"mensal"` é o da rodada), `run_id` nulo, `competence` = mês FINAL do período, `project_id`/`family_key` sintéticos `custom:<id>` (não colidem com projeto/família de verdade, e por isso o avulso **não lê nem grava memória de família** — `approve`/`send_reports`/`send_defaults` pulam), `scope_json` = `{scope, part, label, summary}` (o `scope` é o que o "Regenerar" relê; `_public` só expõe `label`/`summary`, o recorte inteiro é do gerente). `store.list_reports(competence)` só devolve `kind = "mensal"`: sem isso o avulso aparecia como "projeto novo" com `hours_now = 0` e "horas mudaram" fixo. `POST /auto-generation/custom/preview` calcula sem gravar (relatórios, horas, avisos) e a tela exige a prévia fresca do MESMO recorte antes de gerar; `POST /auto-generation/custom` cria todos numa transação (ou saem todos, ou nenhum). Rótulo do período (`builder.period_label`): "Agosto/2026", "Julho a Novembro/2026" ou "Dezembro/2025 a Fevereiro/2026" — o mesmo que `generator.parse_period_label` lê de volta (histórico, nome de arquivo, ingestão de e-mail). **Vários meses + unidade projeto:** o Projectile abre um projeto por mês, então as linhas se juntam pela FAMÍLIA (`families.family_key` + `auto_families`) num pacote só; unidade pacote não junta (o `capJob` traz o mês no nome). **`pacote_scope` gravado:** pacote inteiro na unidade pacote → o nome do pacote; projeto inteiro sem filtro → `None`; conteúdo PARCIAL (filtro de colaborador, ou só alguns pacotes na unidade projeto — `custom.covers_whole`) → marcador `"Personalizado"`, que no Diagnóstico deixa o projeto "parcial" e nunca "enviado" (a ingestão manda um anexo por pacote e casa o projeto pelo nome dele). Horas sem descrição: relatório cujo grupo só tem linha sem descrição não gera rascunho (aviso com as horas que ficaram de fora); com `package_unit = "pacote"` observação sem separador válido vira aviso "descrição vazia" no editor, como no modo pacote manual — conferido com dados reais: toda hora vira atividade, aviso visível ou aviso de relatório descartado. **Apagar** (`DELETE /auto-generation/custom/{id}` → `service.delete_custom`, botão "Apagar" com confirmação no bloco): só relatório `avulso` em rascunho (`DELETABLE_CUSTOM`: gerando, erro, em revisão, aguardando aprovação, devolvido, pulado) — remove o relatório e a linha do tempo dele, o revisor perde o acesso na hora (404) e a guia aberta no editor fecha (e o salvamento pendente dela é cancelado). Aprovado/enviado já foi pro histórico e/ou pro cliente: 409 "reabra antes de apagar" (o histórico continua, como em Reabrir). Mensal nunca se apaga por aqui (409): é da rodada. A ação vai pro `audit_log` (`auto_custom_deleted`). Testes em `test_custom_generation.py` e `customScope.test.ts`.
- **Número digitado na prévia do mês atual** (decisão do usuário, 2026-09-29): o bloco da prévia tem o campo "Número do relatório" (`PlannedNumberField`, o mesmo `NumberInput` da lista, com a validação do formato na hora). `PUT /auto-generation/competences/{AAAA-MM}/numbers/{project_id}` (`{number|null}`) guarda em `auto_settings` na chave `planned_numbers:AAAA-MM` (`{project_id: número}`, sem migration) — **por competência, não na regra da família** (o número muda todo mês; na família ele passaria pros meses seguintes). Confere o formato do padrão geral (400 com a mensagem do modelo), que o projeto tem horas na competência (404) e que o número não está reservado pra OUTRO projeto do mês (400); histórico e outras competências continuam sendo barrados só na aprovação. Quando o rascunho é gerado (rodada e "Regenerar") o número entra em `project_code` — **só com UM pacote** (modo projeto, o padrão; com vários pacotes não dá pra saber de qual é, e a tela avisa que o número é digitado depois). `preview` devolve `planned_number`. Testes em `test_auto_generation.py`. "revisado" aparece na tela como "Aguardando aprovação". O campo é o `ReviewerPicker.tsx` (lista com busca por nome/login, sem acento e em qualquer ordem — `filterReviewers` —, setas/Enter/Esc), nos dois blocos (rascunho e prévia). Avisos só no app: `GET /my-reviews/summary` (`to_review`, `assigned`, e `awaiting_approval` só pro gerente), contador no menu com polling de 2 min + foco da janela.
- **Configuração individual do projeto** = regra da FAMÍLIA dele (`auto_rules`, só o que difere do padrão geral: gerar ou não, modo, assinantes, arquivos). Na tela é "a configuração deste projeto"; guardada pela família pra valer nos meses seguintes do mesmo trabalho. `competence_view`/`preview` devolvem `rule` (o que o projeto sobrescreve) e `effective` (o que vale) de cada projeto.
- **Família de projeto** (`families.py`): o Projectile abre UM projeto por mês pro mesmo trabalho ("Legislation Package - Estribo 07.2026", "… 08.2026") — regra (`auto_rules`) e memória (`auto_memory`) são por `cliente|nome sem a data` (normalizado, sem acento/caixa), nunca por `project_id`. `auto_families` guarda a associação manual quando o nome muda. "2025/2026" e códigos de pacote ("1546.7.3-001") não são datas.
- **Memória do mês anterior** (`memory.py`): gravada na APROVAÇÃO e aplicada ao rascunho seguinte da família — nomes de grupo, performance por grupo, descrições, idioma, gráficos, assinantes e o último número (só como `suggested_code`). Casada por `source_key` (texto original do Projectile sem data), nunca por posição. **Horas nunca são copiadas**; assinante da configuração vence o da memória.
- **Builder = busca manual por cliente** (`builder.py`): `fetch_project_hours` → `group_hours_by_project` (modo "projeto", o padrão) ou `group_hours(split_by_package=True)` (modo "pacote", o padrão da busca manual por cliente) → `build_parse_response`, mais os defaults que só existiam no navegador (`FileUpload.applyParseResponse`/`createInitialHeader`: performance 1, "Santo André, dd.mm.aaaa", "Agosto/2026", empresas dos assinantes, `pacote_scope`) — teste de paridade em `test_auto_generation.py`. UMA consulta de horas pra todos os projetos (pool de 5). Projectile e cache do Painel acessados como atributo do módulo (`management._get_cached_rows`, `projectile_db.fetch_*`).
- **Horas sem descrição** (medido em agosto/2026: 8 de 19 projetos; o MBB_OTC tinha 603 h no Painel e 145 h no rascunho): viram `issues` do rascunho → aviso do editor (`currentIssues`, "Adicionar como atividade"), como na busca manual. `source_hours` = total do Projectile na geração; a diferença pro rascunho é o selo "X h sem descrição". "Horas mudaram" compara Projectile agora × `source_hours` — nunca o total do rascunho (dava alarme falso).
- **Rodada** (`service.start_run`): uma por competência (`auto_runs.competence` UNIQUE + `SELECT … FOR UPDATE`), rodando em thread; "Gerar agora" de novo só cria o que falta (idempotente); rodada "running" há mais de 30 min é considerada morta. Cada projeto tem try/except e transação próprios — erro num vira `erro` SÓ nele. Fechados no Diagnóstico e famílias desativadas → `pulado`. **Fechamento depois da geração** (decisão do usuário, 2026-09-30): `common.skip_closed_drafts` pula (`pulado`, motivo "fechado no Diagnóstico", evento `skipped` de "Sistema") os rascunhos EM ABERTO (erro, em revisão, aguardando aprovação, devolvido) de projeto/cliente fechado — roda ao montar a lista da competência e os contadores/lista de "Minhas revisões", fail-open. Aprovado/enviado não muda (já foi pro histórico/cliente); reabrir o fechamento não ressuscita ("Regenerar" vale pra pulado); personalizado fica de fora (o recorte é escolha explícita).
- **Estados** (`service.py`, validados no backend): `gerando → em_revisao → revisado → aprovado → enviado`, com `erro`, `devolvido`, `pulado`. Editável: `em_revisao`/`revisado`/`devolvido`. Aprovado **ou enviado** se reabre (`reopen`: volta pra `em_revisao`, limpa aprovação e `sent_*`; o envio anterior fica na linha do tempo e a nova versão precisa ser aprovada e enviada de novo); regenerar descarta as edições (a tela confirma; mescla por `source_key` é fase 4).
- **Trava otimista** (`draft_version`): salvar/numerar/aprovar com versão velha → 409 com `current_version`. A aprovação exige a versão exata do rascunho salvo e confere que as horas do payload batem com ele.
- **Aprovação** (`service.approve`), só com o relatório aberto no editor (os gráficos vêm do canvas do navegador): número obrigatório (mensagem clara antes do 422), formato configurável como MODELO na tela (`#` = dígito, padrão "SE.##.###"; `rules.model_to_pattern`/`pattern_to_model` convertem pra regex e de volta — a tela nunca mostra regex, só no modo "avançado" quando a regra não cabe num modelo; mensagem de recusa usa o modelo), único na competência, e barrado se já existir no histórico pra OUTRO projeto na mesma competência (outra competência só avisa). Gera cada pacote × formato com o mesmo código do `/generate` (`services/report_files.py`) — arquivo que não gera derruba a aprovação —, **congela o payload** em `approved_payload_json` (o envio da fase 2 monta os anexos dele, não do histórico fail-open) e atualiza a memória. `GET …/files` devolve os arquivos do payload congelado.
- **Persistência** (`services/auto_generation_store.py`, migrations `0007_auto_generation` e `0008_auto_custom_reports` — `kind`/`scope_json` em `auto_reports`, `run_id` opcional): dado primário, **sem fail-open** (`AutoGenerationStoreError` é um `ManagementStoreError` → 502). Escrita só em `write_session()` (lock na linha `lock` de `auto_settings`). **Nunca leia pelo store DENTRO de uma `write_session`**: é outra conexão, e no SQLite dos testes (mesma conexão física) fechá-la desfazia a transação — bug real, pego pelo teste da aprovação.
- **Rascunhos manuais são do login que os criou** (`useReportTabsStore`): a chave de guias no `localStorage` é uma só por navegador, então há um marcador de dono (`relatorio-horas:tabs:owner:v1`). Entrar com OUTRO login descarta as guias (`resetAll`); sair de propósito (`useAuthStore.loggedOut`) apaga tudo; sessão expirada mantém (volta o mesmo usuário); guia antiga sem dono fica com quem entrar primeiro. O servidor não guarda rascunho manual — só o da geração automática.
- **Frontend**: a guia aberta pela geração automática (`ReportTabMeta.auto`) **nunca vai pro `localStorage`** (a chave de guias é uma só por navegador, não por login) — F5 fecha a guia, o rascunho continua no servidor; troca de login fecha todas (`closeAutoTabs`). O salvamento no servidor é automático (`useAutoGenerationStore`, debounce de 2,5 s, ignora carga de guia via `isLoadingTabBundle`), com indicador separado do autosave local; 409 → "Recarregar do servidor", nunca sobrescreve calado. Nessas guias a `AutoReportBar` substitui `GenerateFooter`, o card de importação e "Alterar dados". Número digitado na lista só com o relatório FECHADO no editor (senão o próximo salvamento da guia sobrescreveria). `utils/generatePayload.ts` é o mesmo payload do "Gerar" e do "Aprovar".
- **Medido com dados reais** (2026-09-28, agosto/2026): 19 rascunhos em ~21 s (a maior parte é a carga das horas), 0 com total diferente do Painel, 0 alarme falso, 0 erro; segunda rodada não duplicou; lista com cache em 0,02 s. XLSX/PDF saem do rascunho.

## Arquitetura do frontend

`App.tsx` controla sete views sem React Router:

```ts
type AppView = "report" | "dashboard" | "management" | "diagnostics" | "history" | "analytics" | "analytics-chat" | "auto-generation" | "my-reviews";
```

- `Sidebar.tsx`: logo, navegação, guias abertas, tema, usuário e logout. É recolhível no desktop e drawer no mobile. Recolhida, cada ícone tem tooltip instantâneo (`SidebarTooltip.tsx`: `data-tip` + um elemento só em portal, porque a sidebar tem `overflow` escondido e cortaria um tooltip interno; `aria-label` no lugar do `title`, que dava o nome acessível). Ordem do menu: Gerar relatório, Dashboard, Painel de gerência, Diagnóstico, Analytics relatórios, Histórico, Chat analítico, Geração automática, Minhas revisões (só aparece com `summary.assigned > 0`). Itens com pendência mostram um contador (recolhida: um ponto no ícone; o número vai no tooltip e no `aria-label`).
- `PageHeader.tsx`: cabeçalhos internos reutilizáveis.
- `FileUpload.tsx`: fluxo de fonte, escopo, organização, período e seleção de cliente/projetos.
- `RadioCard.tsx` e `StepCard.tsx`: controles visuais do fluxo de importação.
- `Preview/`: revisão do relatório.
- `GenerateFooter.tsx`: formatos, nome, performance, download e abertura do modal de envio.
- `MyHoursDashboard.tsx`: dashboard pessoal.
- `ManagementPanel.tsx`: KPIs e gráficos gerenciais.
- `DiagnosticsPanel.tsx`: "Relatórios enviados" (`SendStatusCard.tsx`, status de envio por projeto/mês + popup de Fechados — saiu do Painel de Gerência), amostras, duplicidades e mensagens ignoradas. Marcar/desmarcar "Enviado" cria/apaga uma amostra manual, por isso o card chama `onChanged` pra recarregar a tabela de Amostras.
- `HistoryPanel.tsx`: histórico de relatórios (`reports_db`) — lista, versões, gerações, artifacts e auditoria. Visível pra todo mundo (não só gerente); backend filtra pra só os próprios relatórios de quem não é gerente.
- `AnalyticsPanel.tsx`: métricas agregadas sobre `reports_db` (horas por competência/grupo/projeto, taxa de falha, relatórios por mês, responsáveis) + o bloco "Saúde do sistema" (`GET /analytics/health`: geração dos últimos 30 dias com p95 e última falha, artefatos em disco, última rodada automática, mensagens ignoradas; falha da chamada vira mensagem própria e não derruba o resto) — só gerente (`access: "manager"` em `Sidebar.tsx` + `require_manager` no backend). Cada bloco é um `AnalyticsSection` com no máximo 8 linhas visíveis (`.analytics-scroll-8`: altura de linha fixa em 31px e cabeçalho grudado; mudou o padding da célula, recalcule o `max-height`). Datas/sizes usam `utils/historyFormat.ts` (`formatDateTime`/`formatFileSize`).
- `AutoGenerationPanel.tsx`: geração automática (só gerente) — seletor de competência (mês passado, mês atual em prévia calculada na hora, anteriores), faixa de etapas com contagem, **um bloco (`ProjectCard`) por projeto, um por linha e horizontal** (identificação | dados | status e ações, empilhando em tela estreita — decisão do usuário, não voltar pra grade) com status, selos, horas, número de cada pacote (editável ali), ações por estado e a **configuração individual** (`ProjectConfig`, campo vazio = padrão), "projetos novos desde a geração" e o modal do padrão geral. Os componentes moram em `frontend/src/components/auto/` (`ProjectCard`, `ProjectConfig`, `CustomRequestCard`, `AutoSettingsModal`, `fields` — ReviewerField/Number* —, `StatusPill`, `format` — rótulos/formatadores; o painel reexporta `StatusPill`/`competenceLabel`/`periodLabelOf` pra quem já importava daqui). A opção **Personalizados** do seletor lista a geração personalizada (selo "personalizado", período e resumo do recorte, "recorte parcial"; sem "Configuração", que é de família) e o botão "Nova geração personalizada" abre `AutoCustomModal.tsx` (período, blocos de recorte com busca — clientes/projetos/pacotes/colaboradores pelas rotas da busca manual e de `/my-hours/employees` —, como as horas viram relatórios, título e revisor, prévia obrigatória); a montagem/validação do pedido é pura, em `utils/customScope.ts`. `AutoReportBar.tsx` é a barra da guia aberta a partir dela (ver "Geração automática"): com `auto.role = "reviewer"` mostra "Mandar pra aprovação" e esconde arquivos/performance; do gerente, "Aprovar" e "Devolver".
- `MyReviewsPanel.tsx`: "Minhas revisões" (qualquer papel) — pra revisar, aguardando o gerente e os últimos aprovados; abre no editor com `openInEditor(id, "reviewer")`.
- `AnalyticsChatPanel.tsx`: chat analítico (só gerente) — texto + visualizações (`analytics/VisualizationRenderer.tsx`, contrato de `backend/app/analytics/cross_output.py`/`visualization.py`: `kpi` (vários = `KpiGrid`), `bar`, `horizontal_bar` (agrupada ou `stacked`), `line` multissérie, `donut`, `heatmap`) + tabela com ordenação por coluna, linha de total e "Baixar Excel" (`POST /analytics/chat/export`), com fonte e período. Cor das séries por posição (`--achat-s0..s4`, `--achat-tail` pra "Outros"; paleta validada ≥ 3:1 nos dois temas). Linha e barra vertical têm eixo Y com marcas redondas (`niceTicks`: passo 1/2/2,5/5 × 10ⁿ, sempre incluindo o zero, inteiro pra contagem) e grade; barra vertical tem base no zero (negativo desce, em vermelho). Barra horizontal fica sem eixo: o valor já vai escrito em cada barra. O renderer só desenha dados; nunca recebe HTML/SVG do servidor.
- Menu por papel: `NAV_ITEMS` em `Sidebar.tsx` tem `access: "all" | "coordinator" | "manager"`; `hasCoordinatorAccess(user)` (`useAuthStore.ts`) = gerente ou coordenador. Isso só esconde tela — quem barra de verdade é o backend.
- `useManagementStore.load()` busca `/management/kpis` pra gerente e `/management/send-status` pra coordenador (`fromSendStatus` preenche os números com zero/nulo — só o Painel os mostraria, e ele não aparece pro coordenador). A store descarta os dados quando o login muda (`_loadedForLogin`): ela sobrevive ao logout, e sem isso um coordenador herdaria na memória os KPIs de um gerente que usou o mesmo navegador.

- **Controles próprios, nunca os nativos** (decisão do usuário, 2026-09-29): escolha de UMA opção é `Select.tsx` (mesmo visual dos filtros `.month-dropdown*`, caixa de busca no topo da lista — `utils/search.matchesQuery`: sem acento, várias palavras em qualquer ordem —, setas/Enter/Esc, abre pra cima quando não cabe) — nada de `<select>` novo, cuja lista abre com o visual do sistema; vários valores/filtros, `FilterDropdown.tsx` (`SingleSelectDropdown`/`MultiSelectDropdown`, sempre com busca; `hint` é o ícone de ajuda do rótulo); confirmação é `confirmDialog` (`ConfirmDialog.tsx`, montado uma vez em `main.tsx`), nunca `window.confirm`; dica que aparece na hora é `InstantTip.tsx`. **Tooltip de dropdown/filtro** (decisão do usuário, 2026-09-30): `HintHost.tsx`, montado uma vez em `main.tsx`, mostra na hora (mesmo visual do tooltip da sidebar recolhida, `.hint-tip`) o texto de qualquer elemento com `data-hint` — por delegação, num portal, no hover e no foco; some ao clicar/rolar/Esc e não aparece com a lista do controle aberta (`aria-expanded`). `data-hint-side="right"` (itens de lista) põe ao lado e só aparece quando o texto está cortado com reticências. O texto é `utils/hint.hintText(rótulo, valores, vazio)` ("Período: Agosto/2026"; filtro de vários lista todos os valores). Todo dropdown/filtro novo leva `data-hint` no botão e nas opções, no lugar de `title` (o nativo demora e tem o visual do sistema). O `<input type="time">` do Padrão geral continua nativo (o seletor dele é do navegador).

Não reintroduza o antigo `Header.tsx` nem o stepper vertical; ambos foram substituídos pela sidebar e pelos blocos horizontais.

### Fluxo de importação

- `importSource = "db"`: buscar no Projectile.
- `importSource = "file"`: arquivo local.
- Busca do próprio usuário suporta `single` (consolidado) e `multi` (por pacote).
- Busca por cliente aparece somente para gerente e suporta `projeto` ou `pacote`, com múltiplos projetos.
- Período pode ser mês único ou intervalo. No intervalo a tela tem QUATRO campos (mês inicial, ano inicial, mês final, ano final), então cruza ano ("Dezembro/2025 a Fevereiro/2026"); `utils/period.normalizeRange` ajusta cada mês ao ano dele (janela de quem não é gerente) e o fim nunca fica antes do início.
- As opções de ano vêm de `getReportYearOptions()` e cobrem de 2008 ao ano corrente, em ordem decrescente.
- Use `frontend/src/utils/period.ts` para montar/interpretar labels. O backend usa `parse_month_label`/`parse_period_label`.
- Ao alterar fonte, modo, cliente, projeto ou período, invalide apenas os dados dependentes necessários.

### Tema e layout

- Tokens globais ficam em `frontend/src/styles/index.css`.
- Barra de rolagem: há um estilo global (`::-webkit-scrollbar*` + fallback `scrollbar-width`/`scrollbar-color` no Firefox via `@supports not selector(...)`). Área rolável nova não precisa de CSS próprio de barra; só defina se quiser algo diferente.
- `.page-header` não tem margem embaixo: telas com contêiner flex usam `gap` (Gerência, Diagnóstico, Chat analítico); Histórico e Analytics, que empilham `.card` em fluxo normal, dão `margin-bottom: 22px` ao cabeçalho. Tela nova: use um dos dois, senão o fio do cabeçalho cola no primeiro card.
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
| `useReportStore.ts` | relatório ativo, header, importação, edição, undo, drag e split — tipos/helpers puros (snapshot, bundles de guia, merge) vivem em `reportState.ts` e são reexportados |
| `useReportTabsStore.ts` | múltiplas guias e persistência local |
| `useMyHoursStore.ts` | dashboard de horas, filtros e o colaborador escolhido (`employeeId`, `null` = o próprio; seletor `MyHours/EmployeePicker.tsx`, só gerente/coordenador). Descarta os dados quando o login muda (`_loadedForLogin`) e respostas de uma seleção que já mudou |
| `useManagementStore.ts` | KPIs, filtros, fechados e status de envio |
| `useDiagnosticsStore.ts` | amostras e projetos do diagnóstico |
| `useHistoryStore.ts` | lista/paginação/busca geral (`filters.search` → `?q=`) de `GET /reports`, detalhe do relatório selecionado (versões, gerações, artifacts, auditoria) e detalhe de uma versão |
| `useAnalyticsStore.ts` | `GET /analytics/summary` — resumo único (sem paginação/filtro), `loading`/`error` |
| `useAutoGenerationStore.ts` | aba Geração automática (competências, lista, prévia, configurações) e o salvamento no servidor da guia automática aberta; descarta tudo quando o login muda (`_loadedForLogin`) |
| `useMyReviewsStore.ts` | "Minhas revisões" e os contadores do menu (`/my-reviews/summary`); descarta tudo quando o login muda |
| `useAnalyticsChatStore.ts` | mensagens do chat analítico e o contexto curto devolvido pelo backend; descarta tudo quando o login muda (`ensureUser`) |

## Backend

### Módulos

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | monta o `FastAPI`, middlewares, `include_router` de cada domínio e static mount — **não tem endpoint nenhum**, ver "API — routers" abaixo |
| `auth.py` | login Projectile, rate limit e sessões — store memória (default) ou Redis (`SESSIONS_BACKEND`, ver `core/redis_client.py`; `reset_store_for_tests` injeta fakeredis) |
| `worker.py` | processo de background dos containers: `email_polling_loop` + `scheduler_loop` (o `main.py` reusa os mesmos loops quando `PROCESS_ROLE` permite; `python -m backend.app.worker`) |
| `db_credentials.py` | leitura da senha no Windows Credential Manager/keyring |
| `projectile_db.py` | pool de conexões (`DBUtils.PooledDB`), queries e agrupamento |
| `parser.py` | parser do export XLSX e `RowIssue` |
| `generator.py` | geração XLSX (copia o template e altera ZIP/XML) — reexporta `holidays.py` |
| `holidays.py` | feriados (nacionais/móveis, SP, Santo André) e dias úteis — extraído do `generator.py`, que reexporta |
| `pdf_generator.py` | PDF A4 e metadados |
| `hours_analytics.py` | contrato, baseline, lacunas, outliers e séries |
| `management.py` | KPIs, cache, amostras e fechados (regra de negócio; persistência em `services/management_store.py`) |
| `email_ingest.py` | Graph, anexos, matching, leitura e envio de e-mail |
| `notifications.py` | avisos por e-mail da geração automática (fase 4): revisor atribuído/devolvido e aguardando aprovação; destinatário resolvido no Projectile (`fetch_user_emails`), opt-out no Padrão geral (`notify_email`), links com `APP_BASE_URL`, fail-open |
| `chatbot.py` | chamadas Anthropic |
| `chat_ops.py` | schema/aplicação das operações do chat |
| `translate_ops.py` | contrato de tradução |
| `core/config.py` | `Settings` (pydantic-settings) — `reports_db_*`, `projectile_sys_client_id`, `projectile_db_pool_size`, as do chat analítico (`typesafe_api_key`, `jev_*`, `analytics_chat_*`) e as de observabilidade (`log_format`, `slow_request_ms`, `sentry_dsn`, `sentry_environment`); não todas as env vars (as de Projectile, allowlists, Anthropic e Graph ainda são lidas por `os.environ`) |
| `core/redis_client.py` | cliente Redis compartilhado (sessões/rate-limit e trava de envio) — `None` sem `REDIS_URL`; timeouts curtos |
| `core/logging.py` | logging estruturado (`LOG_FORMAT=text\|json`), request-id por requisição (header `X-Request-Id`, sanitizado) e Sentry/GlitchTip opcional via `SENTRY_DSN`; `configure_logging()` roda no import de `main.py` |
| `core/authz.py` | autorização central: `parse_logins` + sets (`MANAGEMENT_PANEL_LOGINS`/`COORDINATOR_LOGINS`/`TRANSLATE_ALLOWED_LOGINS`, de `Settings`) e `is_manager`/`is_coordinator`/`is_translate_allowed`/`roles_for` — consumidores chamam funções, nunca importam os sets |
| `analytics/` | chat analítico — ver a seção "Chat analítico" acima e a linha em "Onde mexer" |
| `integrations/jev.py` | cliente HTTP do Jev; endereço fixo da API oficial da TypeSafe, nunca configurável |
| `repositories/` | leituras do chat analítico: `engineering_hours_repository.py` (horas CAD+CAE, mesma carga/cache do Painel) e `report_analytics_repository.py` (relatórios gerados no `reports_db`) |
| `db/reports_db.py` | engine SQLAlchemy do `reports_db` (pool de verdade, `connect_timeout` curto) |
| `db/reports_schema.py` | `Table`/`MetaData` das 7 tabelas do histórico (SQLAlchemy Core, não ORM); alvo do `alembic revision --autogenerate` |
| `services/snapshot.py` | funções puras: canonical JSON, hash de dado/identidade, parse de competência |
| `services/report_persistence.py` | `begin_generation`/`finish_generation_success`/`finish_generation_failure`/`reconcile_orphaned_generations`, `GenerationGuard` — sempre fail-open |
| `services/audit.py` | `record_event()` — trilha de auditoria em `audit_log`, sempre fail-open |
| `services/management_store.py` | persistência de Gerência/Diagnóstico nas tabelas `mgmt_*` — `load_document`, `write_session` (lock), `import_document`. **Não** é fail-open |
| `tools/import_management_json.py` | importação única do antigo `management_kpi.json` (`python -m backend.app.tools.import_management_json [--replace-existing]`) |
| `services/report_files.py` | payloads de geração (`GeneratePayload`…) e a montagem do XLSX/PDF — compartilhado por `/generate`, `/send-report` e a aprovação da geração automática (mesmo arquivo pro mesmo conteúdo) |
| `services/auto_generation_store.py` | persistência da geração automática nas tabelas `auto_*` — `write_session` (lock), trava otimista (`VersionConflict`). **Não** é fail-open |
| `auto_generation/` | geração automática — ver a seção acima |
| `services/report_queries.py` | leituras pro histórico (`GET /reports/*`) e agregações do Analytics (`get_analytics_summary`, `GET /analytics/summary`) — **não** é fail-open: falha vira 502 (a única função do endpoint é ler) |

### API — routers

`main.py` só monta o app; toda rota vive em `api/routers/*.py`, uma por domínio:

| Router | Rotas | Modelos Pydantic |
|---|---|---|
| `api/routers/auth.py` | `/auth/login`, `/auth/me`, `/auth/logout` | `LoginRequest` |
| `api/routers/health.py` | `/health` (público, sem login — resposta minimalista `{status: ok\|degraded}`, 200/503), `/health/details` (só gerente — check por check com latência, motivo e heartbeat do agendador). Checa `reports_db`, pool do Projectile e `scheduler.last_tick_at`; check que falha vira `{ok: false}` e não derruba o endpoint | — |
| `api/routers/parsing.py` | `/parse`, `/parse-db`, `/parse-db-client` | `ParseDbRequest`, `ParseDbClientRequest`; hardening de upload (`_stream_upload_to_tempfile`, `_reject_if_oversized_uncompressed`) |
| `api/routers/my_hours.py` | `/my-hours` | — |
| `api/routers/management.py` | `/management/*` (15 rotas) | `ManualSampleCreatePayload`, `SampleUpdatePayload`, `ManualEntryPayload`. **Nome igual ao módulo `backend/app/management.py`** (regra de negócio) de propósito — são caminhos de import diferentes (`api.routers.management` vs `management`), sempre importe com alias quando os dois aparecem juntos (`main.py` faz `from .api.routers import management as management_router`) |
| `api/routers/generation.py` | `/generate`, `/send-report` | `HeaderPayload`, `GroupPayload`, `ActivityPayload`, `ReportPackagePayload`, `GeneratePayload`, `SendReportPayload` — `OUTPUT_DIR` também vive aqui |
| `api/routers/history.py` | `/reports/*`, `/artifacts/{id}/download` | — |
| `api/routers/chat.py` | `/chat`, `/translate-activities` | `ChatState`, `ChatGroup`, `ChatActivity`, `ChatPackage`, `ChatRequest`, `ChatResponse`, `TranslatePayload` |
| `api/routers/analytics.py` | `/analytics/summary` e `/analytics/health` (só gerente, `require_manager`; o health compõe geração/artefatos de `report_queries`, última rodada de `auto_generation_store` e mensagens ignoradas de `management` em `services/system_health.py`) | — |
| `api/routers/auto_generation.py` | `/auto-generation/*` (só gerente) | modelos em `auto_generation/schemas.py` |
| `api/routers/my_reviews.py` | `/my-reviews/*` (qualquer sessão, só os atribuídos a ela) | reaproveita `auto_generation._call` e os schemas |
| `api/routers/analytics_chat.py` | `POST /analytics/chat`, `POST /analytics/chat/export` (só gerente) | `AnalyticsChatRequest`, `ExportRequest` (em `analytics/schemas.py`) |

Compartilhado entre routers: `api/dependencies.py` (`require_session`/`require_manager`/`require_manager_or_coordinator`/`require_translate_access`/`SESSION_COOKIE`), `api/errors.py` (`log_and_generic_error`/`GENERIC_*_ERROR`), `api/shared.py` (`resolve_month_range`, `build_parse_response`).

**Autorização central (`core/authz.py`)**: as allowlists (`MANAGEMENT_PANEL_LOGINS`/`COORDINATOR_LOGINS`/`TRANSLATE_ALLOWED_LOGINS`, lidas de `core.config.Settings` no import) e as checagens (`is_manager`/`is_coordinator`/`is_translate_allowed`/`roles_for`) moram em UM lugar. Consumidores (`api/dependencies.py`, `api/routers/auth.py`, `api/routers/history.py`) chamam as funções — nunca importam os sets. Isso aposentou o gotcha antigo: um `from import` congelava a cópia e o `monkeypatch.setattr(management, ...)` dos testes não surtia efeito; hoje o padrão é `monkeypatch.setattr(authz, "MANAGEMENT_PANEL_LOGINS", ...)` e vale pra todo mundo (teste em `test_authz.py`). A mesma categoria de bug (binding copiado no import) segue valendo pra `get_engine` em `report_persistence.py`/`report_queries.py`/`audit.py`: estado "testável por monkeypatch" continua devendo ser referenciado via atributo do módulo definidor.

**Adicionar uma rota nova**: crie/edite o router do domínio certo em `api/routers/`, nunca em `main.py` diretamente. Se o domínio for novo, crie o arquivo, defina `router = APIRouter()`, e adicione `app.include_router(seu_router.router)` em `main.py`.

### Banco do Projectile

- Importe o backend como `backend.app.*`; use imports relativos dentro do pacote.
- `projectile_db._get_connection()` empresta uma conexão de um pool de verdade (`DBUtils.PooledDB`, `autocommit=True`, `ping=1` reconecta sozinho ao pegar do cache); tamanho fixo em `Settings.projectile_db_pool_size` (padrão 5 — pequeno de propósito, sem staging pra medir `max_connections` real do MySQL legado).
- Toda função `fetch_*` usa `_borrowed_connection(conn)`: se `conn` foi passada pelo chamador (reaproveitar em várias queries do mesmo request), NÃO devolve ao pool — quem abriu é dono. Se `conn` é `None`, empresta e devolve sozinha ao final (`finally: borrowed.close()`).
- `open_connection()` (usada por `auth.verify_projectile_login` e `management.compute_monthly_kpis` pra reaproveitar uma conexão em várias queries) empresta do pool sem devolver — o CHAMADOR é responsável por `conn.close()` num `try/finally` (devolve ao pool, não fecha de verdade).
- **Conexão nova é cara neste servidor** (medido em 2026-09-30): o MySQL do Projectile (5.5.53) segura o pacote de boas-vindas por ~20,0 s em TODA conexão nova — resolução reversa de DNS do IP do cliente no servidor; TCP leva ~10 ms e a consulta em conexão aberta 10–170 ms. Por isso `projectile_db.warm_pool` abre `WARM_CONNECTIONS` (3) conexões em paralelo, em segundo plano, no boot (`main._warm_projectile_pool`; `PROJECTILE_DB_WARMUP=false` desliga, e o `conftest` desliga nos testes). Sem isso o 1º usuário depois de cada restart esperava ~20 s no Dashboard de horas. A correção de verdade é no servidor do Projectile (`skip-name-resolve` no `my.cnf` ou um registro PTR do IP do backend no DNS) — fora do código e fora do escopo deste repositório. Conexão derrubada e reaberta pelo `ping=1` paga os 20 s de novo.
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

- Tabelas `mgmt_*` no `reports_db` (`db/reports_schema.py`, migration 0006), uma por seção do antigo `backend/data/management_kpi.json`. `services/management_store.py` só persiste; a regra continua em `management.py`, e `management_store.load_document()` devolve o MESMO formato de dict que o JSON tinha.
- **Sem fail-open, decisão deliberada**: é dado primário (entradas manuais, amostras corrigidas à mão). Banco fora do ar → `ManagementStoreError` → handler em `main.py` responde 502 com mensagem genérica em qualquer rota. Nunca cair em silêncio pra um arquivo local (os dois divergiriam).
- Toda escrita passa por `management_store.write_session()`, que trava a linha `samples_lock` de `mgmt_meta` (`SELECT ... FOR UPDATE`) — substitui o antigo `threading.RLock` e também serializa entre processos. Não grave nas tabelas `mgmt_*` fora de uma `write_session`.
- Colunas de id (`message_id`, `sample_id`, `project_id`, `client`) usam `utf8mb4_bin` (`_exact_string`): o collation padrão ignora caixa e ids do Graph diferenciam.
- `mgmt_kpi_samples.seq` preserva a ordem de inserção — é o desempate de `_recompute_duplicate_flags` quando duas amostras têm o mesmo `received_at`. Leia sempre ordenado por `seq`.
- `email_ingest.py` deixa `ManagementStoreError` subir (não vira "anexo inválido"): falha de banco não pode marcar o e-mail como processado, senão a amostra se perde.
- Importação única do JSON antigo: `python -m backend.app.tools.import_management_json` (passo 5/6 do `atualizar-servidor.bat`). Idempotente (registro em `mgmt_meta`), renomeia o JSON pra `.migrated-<data>` (backup, nunca apagado). **Recusa** se o banco já tiver dado de gerência sem registro de importação — acontece se o backend novo subir antes da importação e o polling reprocessar os e-mails, recriando as amostras SEM as correções manuais (`edited=True`) que só o JSON tem. Aconteceu de verdade na migração de dev. Saída deliberada: `--replace-existing` (descarta o do banco, guarda cópia em `mgmt_meta`).
- Cache de horas gerenciais: 15 minutos por intervalo.
- `pacote_scope = None` significa projeto inteiro; lista significa pacotes específicos.
- Amostras automáticas duplicadas não entram duas vezes no faturado; amostras manuais têm regras próprias.
- Fechamento de cliente/projeto é permanente e prevalece sobre status calculado.

### E-mail

- O polling inicia no startup do processo com jobs (`PROCESS_ROLE=all\|worker`) e só trabalha quando `AZURE_CLIENT_ID` está configurado.
- Idempotência é por `message_id`.
- Anexos aceitos: `.xlsx` e `.pdf`, até 25 MB e 200 MB descomprimidos para XLSX.
- Quando XLSX e PDF têm o mesmo stem, prefira XLSX para não contar duas vezes.
- `/send-report` envia como o e-mail do usuário autenticado e inclui a caixa do agente conforme configuração Graph.
- Não registre tokens Graph, anexos ou credenciais em logs.

## Contratos de API

Não altere nomes/casing sem migração coordenada.

- `/health` (público, sem login): `{status: "ok"|"degraded"}`, 200/503, sem detalhe — só `reports_db` e Projectile. `/health/details` (gerente): `{status, checks: {reports_db, projectile, scheduler}}`, cada check com `ok`/`latency_ms` (e `error` quando falha); nunca 502/500 por causa de um check.
- `/parse`: multipart `file`, `mode=single|multi` → `{packages, issues}`.
- `/parse-db`: `{month_label, mode}` → mesmo formato de `/parse`; identidade da sessão.
- `/parse-db-client`: `{project_ids, month_label, mode=projeto|pacote}`; gerente ou coordenador.
- `/my-hours?period=current_month|last_3|last_6|last_12[&employee_id=]` → inclui `employee: {employee_id, name}` (de quem são os dados). `employee_id` de outra pessoa: ver "Identidade e autorização".
- `GET /my-hours/employees` (gerente ou coordenador) → `{employees: [{employee_id, name, cost_center}]}`.
- `/generate`: `GeneratePayload` em snake_case; arquivo direto para 1 pacote/1 formato, ZIP nos demais casos. Headers `X-Report-Id`/`X-Report-Version-Id`/`X-Report-Version-Number` (caso único) ou `X-Report-Ids` (zip, `report_id:version_id` separados por vírgula) são **aditivos** — ausentes se a persistência em `reports_db` falhou (fail-open) ou está desligada; nunca confie na presença deles.
- `/send-report`: mesmos pacotes + destinatário/assunto/mensagem/formatos; nunca ZIPa anexos. Mesma persistência fail-open de `/generate` (`created_from="send_report_endpoint"`), sem headers extra na resposta (que é só `{"ok": true}`).
- `/chat`: `ChatState` em camelCase e histórico `{role,text}`; aplica operações atomicamente.
- `/translate-activities`: `{items:[{id,text}], target_language: en|de}`.
- `/management/kpis`: filtros repetíveis `cost_centers`, `clients`, `projects`, `packages`, `selected_months`, `persons`. Só gerente.
- `/management/send-status`: mesmos filtros de `/management/kpis`; devolve só `months` (`[{month}]`), `project_send_status` e as opções de filtro (`available_*`, `project_codes`, `project_clients`). Gerente ou coordenador.
- `/auth/login` e `/auth/me`: `{name, login, email, is_manager, is_coordinator, is_translate_allowed}`.
- `/management/kpis/samples`: CRUD de amostras; PATCH usa `exclude_unset` para distinguir `pacote_scope` ausente de `None`.
- `GET /reports`, `/reports/{id}`, `/reports/{id}/versions[/{version_id}]`, `/reports/{id}/generations`, `/reports/{id}/artifacts`, `/reports/{id}/audit`, `GET /artifacts/{id}/download`: histórico de `reports_db`. Autorização (`history._require_report_access`, mesmo princípio de `/parse-db`/`/my-hours`): **gerente vê tudo; quem não é gerente só vê o que ELE gerou** — o `report` é a identidade compartilhada (número + escopo + competência), mas acesso, versões, snapshots, gerações, arquivos, auditoria e lista filtram por `report_versions.created_by` / `report_generation.requested_by` / `audit_log.actor_id` (param `viewer` de `report_queries`; `None` = gerente). Dois usuários que geram o mesmo relatório viram versões do mesmo `report`, cada um vendo só as suas (a "versão atual" de quem não é gerente é a mais recente DELE; a lista mostra ele mesmo como criador). Vale também pro histórico antigo, sem backfill nem migration: a versão 1 já guarda o `created_by`. O download confere `requested_by` do arquivo e a janela de período. Testes: `test_history_isolation.py` (SQLite). Paginação `page`/`page_size` (máx. 100) em `{items, page, page_size, total}`. `GET /reports?q=` é a busca geral da tela (`report_queries._search_condition`): cada palavra precisa aparecer em alguma de Número, Projeto, Competência/escopo ou Criado por (nome/login), sem diferenciar maiúscula e com `%`/`_` literais; pra quem não é gerente roda dentro dos próprios relatórios. É no backend porque a lista é paginada; a tela busca 300 ms depois da última tecla e descarta resposta de busca antiga (`latestReportsRequest`). Download registra `artifact_downloaded` em `audit_log`. **Ordenação:** `GET /reports?sort=numero|projeto|competencia|versao|criado_por|atualizado&order=asc|desc` (validada, 422 fora da lista; padrão = atualizado desc; `versao` ordena pela versão atual de quem vê; sempre desempata por `id`). **Apagar** (só gerente, decisão do usuário de 2026-09-30): `DELETE /reports` (`{ids}`, 1 a 200) apaga DE VERDADE numa transação (artefatos, gerações, atividades, grupos, versões, snapshots e o relatório — `services/report_admin.py`, fail-closed) e depois remove os arquivos do disco (só dentro de `ARTIFACTS_DIR`; falha de arquivo vira aviso, não desfaz). A trilha `audit_log` fica e ganha `report_deleted` por relatório. `GET /reports/ids` (só gerente, mesmos filtros de busca) devolve os ids do filtro inteiro (até 1000, `truncated`) pro "selecionar todos". Na tela (`HistoryPanel`, só gerente): checkbox por linha e na página (meio marcado), "Selecionar todos os N resultados", barra com Apagar e confirmação; cabeçalhos clicáveis (1º clique cresce, 2º decresce, 3º volta ao padrão, `aria-sort`). Testes: `test_history_delete_and_sort.py`, `useHistoryStore.test.ts`.
- `/auto-generation/*` (só gerente): `GET/PUT config`, `PUT/DELETE rules/{family_key}`, `PUT families/{project_id}`, `GET competences`, `GET competences/{AAAA-MM}` (`{run, items, counts, new_projects}`), `GET …/preview`, `POST …/run` (`{project_ids?}` → 202), `GET reports/{id}` (com `draft` e `events`), `PUT reports/{id}/draft` (`{draft, draft_version}`), `PATCH reports/{id}/numbers`, `POST reports/{id}/approve` (`{payload: GeneratePayload, draft_version}`), `POST reports/{id}/skip|reopen|regenerate`, `GET reports/{id}/files`, `GET reviewers` (`{reviewers: [{login, name}]}`), `PUT reports/{id}/reviewer` (`{login|null}` → `{status, reviewer_login, reviewer_name}`), `POST reports/{id}/return` (`{comment}` obrigatório), `PUT competences/{AAAA-MM}/numbers/{project_id}` (`{number|null}` → `{number}`, número da prévia), `GET files?ids=…` (ZIP em lote, até 100), `POST send` (`{report_ids, to, cc?, subject, message?, formats?}`, vários num e-mail só), `GET reports/{id}/send` (`{to, cc, subject, message, files, sender, counts_in_diagnostics}`), `POST reports/{id}/send/resolve` (`{resolution: "sent"|"not_sent"}` → confirma um envio incerto; 409 sem envio pendente), `POST reports/{id}/send` (`{to: [..], cc?: [..], subject, message?, formats?: ["xlsx"|"pdf"]}` — `formats` escolhe quais dos aprovados vão anexados, ausente = todos, nenhum aprovado no formato = 400 → `{status: "enviado", sent_at}`; 400 e-mail inválido, 409 não aprovado/envio em andamento, 502 Graph). Itens da lista trazem `last_comment` (`{action: submitted|returned, comment, actor_name, created_at}`). **Personalizados:** `GET custom` (`{items, counts}`, todos os avulsos, mais novos primeiro), `DELETE custom/{id}` (apaga um personalizado em rascunho; aprovado/enviado 409, mensal 409, inexistente 404), `DELETE custom/requests/{id}` (cancela um pedido agendado; 404 se não existe), `POST custom/preview` e `POST custom` — que AGENDA, não cria rascunho (`{period: {start, end} "AAAA-MM" = o mês atual, senão 400, blocks: [{clients, project_ids, packages, employee_ids}], split_by: nenhum|projeto|pacote|colaborador, package_unit: projeto|pacote, title?, reviewer_login?}` → preview `{period_label, summary, reports: [{key, title, client, hours, packages, partial, issues, projects}], total_hours, warnings}`; agendar → 201 `{request: {id, competence, label, summary, title, split_by, package_unit, reviewer_name, status, error, created_*}}`; 400 mês diferente do atual/recorte inválido/colaborador fora da engenharia). Quando a rodada gera o pedido, o relatório usa as rotas por `report_id` de sempre.
- `/my-reviews/*` (qualquer sessão, só atribuídos a ela, senão 404): `GET /my-reviews` (`{to_review, awaiting_approval, done}`, `done` com os 20 últimos), `GET /my-reviews/summary` (`{to_review, assigned, awaiting_approval|null}`), `GET /my-reviews/{id}` (mesmo formato do detalhe do gerente), `PUT /my-reviews/{id}/draft` (`{draft, draft_version}`), `POST /my-reviews/{id}/submit` (`{comment?}` → `{status: "revisado"}`). 404 inexistente, 409 estado/versão (`{message, current_version}`), 400 aprovação (`{message, errors: [...]}`).
- `POST /analytics/chat` (só gerente): `{message, context?}` → `{conversation_id, route, intent, reply, visualizations, tables: [{title, columns, column_types, rows, totals, truncated}], metadata: {source, source_label, period_*, classifier, claude_calls, claude_text_used, latency_ms}, context: {conversation_id, last_intent, last_filters, last_spec}}`. `POST /analytics/chat/export` (só gerente): `{title, columns, column_types?, rows, totals?}` → .xlsx.
- `GET /analytics/summary` (só gerente): `{totals: {reports, versions, artifacts}, hours_by_competence, hours_by_group, hours_by_project, generation: {total, failed, failure_rate, avg_duration_ms, by_format}, reports_over_time, top_creators}` — sem paginação, resumo único; horas contam só a versão atual de cada relatório.
- `GET /analytics/health` (só gerente): `{generation: {window_days, total, failed, failure_rate, avg_duration_ms, p95_duration_ms, last_failure}, artifacts: {count, bytes} (disco, via `report_persistence.ARTIFACTS_DIR`), auto_generation: {competence, status, triggered_by, started_at, finished_at, error}|null, skipped_messages: {count, last_received_at, last_reason}, checked_at}`; sem fail-open (banco fora → 502, mesmo contrato de `/analytics/summary`).

`Field(..., allow_inf_nan=False)` e `_sanitize_nonfinite` evitam `NaN`/`Infinity`. Preserve esse comportamento em novos campos numéricos.

## Variáveis de ambiente

Fonte: `.env.example`.

- Projectile: `PROJECTILE_DB_HOST`, `PROJECTILE_DB_PORT`, `PROJECTILE_DB_USER`, `PROJECTILE_DB_NAME`; senha no keyring `projectile_mysql`. `PROJECTILE_SYS_CLIENT_ID` (default `"0"`) e `PROJECTILE_DB_POOL_SIZE` (default `5`, tamanho do pool de conexões — ver `projectile_db.py`) vêm de `core/config.Settings`.
- reports_db: `REPORTS_DB_HOST`, `REPORTS_DB_PORT`, `REPORTS_DB_USER`, `REPORTS_DB_NAME`; senha no keyring `reports_mysql`. `REPORTS_DB_ENABLED` (default `true`) desliga a persistência sem reverter código. `REPORTS_MYSQL_ROOT_PASSWORD`/`REPORTS_MYSQL_APP_PASSWORD` são só bootstrap do `docker-compose.yml` (primeira subida do container) — nunca lidos em runtime pela aplicação.
- Permissões: `MANAGEMENT_PANEL_LOGINS` (gerente; fallback `dherrera`), `COORDINATOR_LOGINS` (coordenador; **sem fallback** — vazia = nenhum), `TRANSLATE_ALLOWED_LOGINS` (fallback `dherrera`) — lidas por `core/authz.py` (via `Settings`) no import; mudou o `.env`, reinicie o backend.
- Anthropic: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (chat de edição/tradução). O chat analítico usa `ANALYTICS_CHAT_MODEL` (padrão `claude-haiku-4-5-20251001`, sem extended thinking).
- Geração automática: `AUTO_GENERATION_ENABLED` (padrão `true`) — chave de emergência do agendador da rodada mensal; o liga/desliga, o dia e a hora do dia a dia ficam no "Padrão geral" da aba.
- Jev (chat analítico): `TYPESAFE_API_KEY` (API oficial da TypeSafe; o OpenRouter foi removido em 2026-09-30); sem chave, o Claude classifica. Endereços fixos em `integrations/jev.py`, nunca configuráveis, `JEV_MODEL` (padrão `jev-latest`); limiares e guardrails em `core/config.Settings` (`JEV_MIN_CONFIDENCE`, `JEV_MIN_CONFIDENCE_NONE`, `ANALYTICS_CHAT_MAX_ROWS`, `ANALYTICS_CHAT_MAX_MONTHS` — padrão 12, a janela do Painel, decisão do usuário —, `ANALYTICS_CHAT_MAX_CLAUDE_PAYLOAD_BYTES`). Com chave, a pergunta e as listas de clientes/colaboradores vão pro OpenRouter e/ou pra TypeSafe AI.
- Graph: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `GRAPH_MAILBOX`, `ALBERTO_EMAIL`, `EMAIL_POLL_INTERVAL_SECONDS`.
- Containers/topologia: `SESSIONS_BACKEND` (`memory`\|`redis`), `REDIS_URL`, `PROCESS_ROLE` (`all`\|`web`\|`worker`) e as senhas por ambiente `PROJECTILE_DB_PASSWORD`/`REPORTS_DB_PASSWORD` (têm prioridade sobre o keyring — é o caminho dos containers; ver `db_credentials.py`).
- Observabilidade: `LOG_FORMAT` (`text`/`json`), `SLOW_REQUEST_MS`, `SENTRY_DSN`/`SENTRY_ENVIRONMENT` (Sentry/GlitchTip self-hosted — sem DSN, nada é enviado, `send_default_pii=False`) — ver `core/logging.py`.
- `APP_BASE_URL` (padrão `http://localhost:8011`): base dos links dos avisos por e-mail (`notifications.py`) — em produção, o endereço real do app.
- Arquivo: `REPORT_PROTECTION_PASSWORD`.

`load_dotenv()` precisa continuar antes dos imports de módulos que leem env no import (`management.py`). Reinicie o backend depois de mudar allowlists. `backend/alembic/env.py` roda como processo separado e chama `load_dotenv()` por conta própria.

## Comandos obrigatórios

```bash
# instalar
pip install -r backend/requirements-dev.txt
npm --prefix frontend install

# reports_db (uma vez, ou depois de recriar o volume Docker)
docker compose up -d reports-mysql
# opcional em dev: sessões sobrevivem a restart do backend (.env: SESSIONS_BACKEND=redis, REDIS_URL=redis://127.0.0.1:6379/0)
docker compose up -d redis
alembic upgrade head
python -c "import getpass, keyring; keyring.set_password('reports_mysql', 'reports_app', getpass.getpass())"

# backend
python -m pytest backend/tests -v

# qualidade do backend (rodar de backend/; config em backend/pyproject.toml)
cd backend
ruff check app tests
ruff format --check app tests   # --write pra formatar
mypy                            # só os módulos listados em [tool.mypy].files

# frontend
npm --prefix frontend test
npm --prefix frontend run lint          # tsc --noEmit
npm --prefix frontend run format:check  # prettier (npm run format pra escrever)
npm --prefix frontend run build

# execução
python -m uvicorn backend.app.main:app --reload --port 8011
npm --prefix frontend run dev
python -m backend.app.worker   # só os loops de background (topologia worker)
```

O `frontend:lint` executa `tsc --noEmit`; a formatação é do Prettier
(`.prettierrc`) e o backend tem ruff (lint + format) e mypy — os três rodam
no CI (`backend-lint` e o passo "Formatação" do `frontend-build`). O mypy é
incremental por módulo: `[tool.mypy].files` começa no `app/core` e só cresce
quando um pacote é limpo, porque o mypy reporta erro de TODO módulo
alcançado pelo grafo de imports, não só dos listados.

Testes marcados `@pytest.mark.reports_db` (persistência em `reports_db`)
pulam automaticamente (`pytest.skip`) se `REPORTS_DB_HOST` não estiver
setado — a suíte local roda sem exigir Docker por padrão; rodam de verdade
só com o container de pé (schema de teste separado, `reports_db_test`, ver
`backend/tests/conftest.py:reports_db_engine`).

### Baseline atual de testes

Em 2026-09-29:

- backend: 781 testes coletados em 2026-09-30 (757 passam + 24 pulados sem `REPORTS_DB_HOST`); a composição abaixo é de 2026-09-29, quando eram 718 (28 do agendador em `test_auto_scheduler.py`; 86 da geração personalizada em `test_custom_generation.py`; 9 da janela de período de quem não é gerente em `test_period_window.py`; 41 da geração automática — 5 da revisão, 3 do envio por colaborador — em `test_auto_generation.py` (SQLite) e `test_auto_generation_mysql.py` (MySQL, `reports_db`); 161 do chat analítico, em `test_analytics_chat.py`/`test_analytics_chat_units.py`/`test_analytics_crossquery.py`, com Jev e Claude sempre falsos; 211 + 64 de `reports_db`/snapshot/histórico (2 da busca geral)/auditoria/upload/chat + 6 do pool de conexões do Projectile + 3 de analytics + 9 do painel de Saúde em `test_analytics_health.py` + 12 de persistência de gerência em `test_management_store.py` + 16 do papel de coordenador (inclusive o período do Diagnóstico) em `test_coordinator_access.py` + 9 do seletor de colaborador em `test_my_hours_employee_selection.py` + 8 de logging/request-id em `test_logging.py` + 9 de `/health` em `test_health.py` + 7 de authz em `test_authz.py` + 3 de política de falha em `test_failure_policies.py` + 10 de sessões/Redis em `test_sessions_redis.py` + 9 do papel do processo/worker em `test_worker.py` + 4 de credenciais por env em `test_db_credentials.py` + 9 de notificações em `test_notifications.py` − 1 teste antigo de concorrência por arquivo, 1 skip pré-existente). `test_management.py` (regra de negócio) roda em SQLite na memória (fixture `management_db`), sem Docker; o que depende do MySQL real (lock entre conexões, collation) é marcado `reports_db`;
- `conftest.py:_drop_stale_tables`: `metadata.create_all` não altera tabela que já existe, então o schema `reports_db_test` criado antes de uma migration ficava sem a coluna nova ("Unknown column" só localmente — no CI o banco nasce limpo); o fixture `reports_db_engine` apaga, uma vez por sessão, a tabela de teste cujas colunas divergem do modelo;
- `conftest.py:_no_real_email_polling` (autouse) desliga o loop de polling nos testes — com `AZURE_CLIENT_ID` no `.env`, `with TestClient(app)` chamava o Graph e o Projectile de verdade no startup;
- frontend: 223 testes em 21 arquivos;
- build: `tsc -b && vite build`.

Em 2026-09-30 (revisão técnica): backend 781 coletados (757 passam + 24 pulados sem `REPORTS_DB_HOST`), frontend 223. Convenções novas: rota que faz I/O bloqueante (banco, arquivo, Graph) é `def` comum (o FastAPI a roda em thread) — `async def` só com `await` de verdade, e aí o trabalho bloqueante vai por `run_in_threadpool` (`test_blocking_routes.py`); payload de geração tem tetos de tamanho/quantidade e a imagem do gráfico é validada (PNG/JPEG, base64, ≤ 4 MB) em `services/report_files.py` (`test_payload_limits.py`); texto do usuário no PDF passa por `pdf_generator._text` (o `Paragraph` do ReportLab lê mini-HTML).

Não atualize esses números sem executar as suítes. Falha `spawn EPERM` de Vitest/Vite no sandbox Windows indica bloqueio ao subprocesso do esbuild; repita fora do sandbox antes de classificar como falha do código.

## Vite, static files e cache

- `frontend/vite.config.ts` não define `root`; execute comandos a partir de `frontend/` ou use `npm --prefix frontend`.
- Proxy: `/auth`, `/parse` (cobre `/parse-db*`), `/generate`, `/send-report`, `/chat`, `/translate-activities`, `/reports`, `/artifacts`, `/analytics`, `/auto-generation`, `/my-reviews`, `/my-hours`, `/management`, `/health` → `:8011`. Rota nova de API entra aqui, senão o dev server dá 404.
- Logos e assets públicos devem ficar em `frontend/public/`.
- `NoCacheStaticFiles`: `assets/*` recebe cache immutable de um ano; demais arquivos recebem `no-store`.
- `frontend/dist` é gerado e ignorado pelo Git.

## CI e deploy

- `.github/workflows/ci.yml` roda em todo push para qualquer branch e em PR para `main`.
- Backend: sobe um serviço `mysql` (schema `reports_db_test`, usuário `reports_app`), instala `requirements-dev.txt`, roda `alembic upgrade head` (senha via `REPORTS_DB_TEST_PASSWORD`, não keyring — CI não tem Windows Credential Manager) e roda pytest.
- Frontend: Node 20, `npm ci`, Vitest e build.
- Não há deploy automático.
- `scripts/atualizar-servidor.bat` atualiza `main`, instala dependências, sobe `reports-mysql` via Docker + `alembic upgrade head` (nunca reinicia o backend se a migration falhar), builda, importa o JSON de gerência (`import_management_json`, último passo antes do restart de propósito — até o restart o backend antigo ainda grava no JSON) e reinicia via NSSM quando configurado.
- Containers (`docker-compose.prod.yml`, decisão de 2026-09-29): mesma imagem (`backend/Dockerfile`, multi-stage com o build do frontend) roda `web` (`PROCESS_ROLE=web`) e `worker` (`PROCESS_ROLE=worker`, `python -m backend.app.worker`) + `reports-mysql` + `redis`; sessões/rate-limit/trava de envio no Redis (`SESSIONS_BACKEND=redis`); senhas por env (`PROJECTILE_DB_PASSWORD`/`REPORTS_DB_PASSWORD`, ver `db_credentials.py`). Atualização: `scripts/atualizar-servidor-docker.bat` (tag `IMAGE_TAG` por data/hora; rollback com a tag de `.last_image_tag.bak`; migration antes do `up -d`). Staging na mesma máquina: `-p relatorio-staging --env-file .env.staging`. NSSM continua como caminho de transição.

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
| KPIs gerenciais | `ManagementPanel.tsx`, `useManagementStore.ts`, `management.py` (regra), `api/routers/management.py` (rota), `services/management_store.py` (persistência) |
| Diagnóstico | `DiagnosticsPanel.tsx`, `useDiagnosticsStore.ts` |
| Tabelas de gerência (`mgmt_*`) | `db/reports_schema.py` + migration em `backend/alembic/versions/`; importação do JSON em `tools/import_management_json.py` |
| Parser XLSX | `backend/app/parser.py` |
| Queries Projectile | `backend/app/projectile_db.py` |
| E-mail | `backend/app/email_ingest.py`, `SendReportModal.tsx`, `api/routers/management.py` (`/management/kpis/check-emails`) |
| Chat/tradução (IDs estáveis de grupo/atividade) | `api/routers/chat.py`, `chatbot.py`, `chat_ops.py`, `translate_ops.py`, `Chat.tsx`, `useReportStore.applyChatState` |
| Proxy dev | `frontend/vite.config.ts` |
| Documentação de uso | `README.md` |
| Persistência de relatórios (histórico/versão) | `backend/app/services/report_persistence.py`, integração em `api/routers/generation.py` (`generate_endpoint`/`send_report_endpoint`) |
| Tela de histórico | `frontend/src/components/HistoryPanel.tsx`, `useHistoryStore.ts`, `utils/historyFormat.ts` |
| Revisão por colaborador | `auto_generation/service.py` (seção "revisão por colaborador"), `api/routers/my_reviews.py`; `MyReviewsPanel.tsx`, `useMyReviewsStore.ts`, `AutoReportBar.tsx` |
| Geração automática | `backend/app/auto_generation/` (famílias `families.py`, memória `memory.py`, rascunho `builder.py`, regras `rules.py`, fluxo no pacote `service/`: `common.py`, `config.py`, `run.py`, `views.py`, `drafts.py`, `custom_flow.py`, `reviews.py`, `send.py`, `approval.py` — a fachada `__init__.py` reexporta a API da antiga `service.py`, e `config`/`custom_flow` importam `reviews` localmente pra não fechar ciclo), `services/auto_generation_store.py`, `api/routers/auto_generation.py`; `frontend/src/components/AutoGenerationPanel.tsx`, `AutoReportBar.tsx`, `useAutoGenerationStore.ts`, `utils/autoDraft.ts` |
| Geração personalizada (recorte livre) | `backend/app/auto_generation/custom.py` (recorte, união, partição, escopo parcial), `builder.build_custom_draft`/`period_label`, `projectile_db.fetch_custom_hours`, `service.create_custom`/`preview_custom`/`custom_view`, migration `0008`; `frontend/src/components/AutoCustomModal.tsx`, `utils/customScope.ts`, `CUSTOM_KEY` em `useAutoGenerationStore.ts` |
| Chat analítico | `backend/app/analytics/`: medidas/dimensões em `catalog.py`, motor em `crossquery.py`, dados em `facts.py`, gráficos/tabelas/texto em `cross_output.py`, travas em `signals.py`, atalhos do Jev em `intents.py`, fluxo em `service.py`, Excel em `export.py`; `integrations/jev.py`, `repositories/`, `api/routers/analytics_chat.py`; `frontend/src/components/AnalyticsChatPanel.tsx`, `analytics/VisualizationRenderer.tsx`, `useAnalyticsChatStore.ts` |
| Métricas agregadas (Analytics) | `backend/app/services/report_queries.py` (`get_analytics_summary`, `get_generation_health`, `get_artifacts_on_disk`), `services/system_health.py` (`get_system_health`), `api/routers/analytics.py`; `frontend/src/components/AnalyticsPanel.tsx`, `useAnalyticsStore.ts` |
| Schema do `reports_db` | `backend/app/db/reports_schema.py` + nova migration em `backend/alembic/versions/` |
| Config central (`reports_db`/`sysClientId`/chat analítico) | `backend/app/core/config.py` |
| Adicionar rota API nova | `backend/app/api/routers/<domínio>.py` (nunca `main.py` diretamente) — ver "API — routers" |
| Autenticação/sessão | `backend/app/auth.py` (regra), `api/routers/auth.py` (rota), `api/dependencies.py` (`require_session`/`require_manager`) |

## Checklist antes de concluir

- O comportamento solicitado funciona nas oito telas (e com os três papéis: gerente, coordenador, colaborador)?
- Estado de uma guia não vazou para outra?
- Tema claro e escuro continuam legíveis?
- Sidebar expandida, recolhida e mobile continuam utilizáveis?
- Não foi alterado contrato API sem atualizar frontend, testes, README e este arquivo?
- XLSX e PDF mantêm os mesmos totais?
- Testes relevantes, typecheck e build passaram?
- Nenhum segredo ou dado real entrou no diff?
