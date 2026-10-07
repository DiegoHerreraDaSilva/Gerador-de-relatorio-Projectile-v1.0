# Automação de Relatório de Horas

Aplicação web interna da Schwaben Engineering para transformar apontamentos do Projectile em relatórios de horas padronizados para a Mercedes-Benz. Os dados podem vir de um export `.xlsx` ou diretamente do MySQL do Projectile, ser revisados no navegador e gerar arquivos `.xlsx`, `.pdf` ou `.zip` sem reconstruir manualmente o relatório a cada mês.

Além do gerador, a aplicação reúne:

- dashboard de horas (pessoal, ou de qualquer colaborador de engenharia pra gerente/coordenador);
- painel gerencial de KPIs;
- diagnóstico: status de envio dos relatórios e correção das amostras usadas nos KPIs;
- histórico de relatórios gerados, com versões e auditoria;
- analytics e chat analítico (perguntas em português sobre horas, faturado e envio);
- geração automática dos rascunhos mensais de todos os projetos, com revisão e aprovação;
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
- o arquivo final (XLSX/PDF) nunca mostra bruto/performance — a performance entra só no cálculo das horas;
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

### Meu time

Tela só do gerente: por pessoa de engenharia (CAD+CAE com apontamento nos últimos dois meses), as horas do mês, os dias com apontamento, os **dias úteis já encerrados sem nenhuma hora** (quem tem mais fica no topo; passar o mouse no número mostra as datas), a média de horas por dia e quantos dias passaram de 10 h. "Ver dashboard" abre o Dashboard de horas naquela pessoa. Usa o mesmo calendário do Dashboard pessoal (feriados nacionais, SP e o municipal da filial). Limite conhecido: o sistema não tem fonte de férias/afastamento, então quem está fora o mês inteiro aparece com todos os dias sem apontamento.

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

### Resumo do mês (Painel de Gerência)

O botão "Resumo do mês" do Painel gera um texto pronto pra copiar (horas, faturado, resultado, relatórios enviados e pendências do mês). Os números vêm sempre de `management.compute_monthly_kpis` — os mesmos do Painel. O texto é automático por padrão; com "Redigir com IA" o Claude escreve a partir desses fatos e, se citar qualquer número que não esteja neles, o texto da IA é descartado e vale o automático. Nenhum nome de cliente vai para a IA. Só gerente.

### Diagnóstico de relatórios

Gerente e coordenador. O gerente vê todos os períodos; o coordenador, só os **últimos 12 meses e o ano atual** (o backend responde 403 pra outro período e só devolve amostras desses meses). O coordenador também não vê horas, faturado nem performance: a tela dele usa `/management/send-status`. Permite:

- acompanhar a situação de envio por projeto e mês (`enviado`, `parcial`, `não enviado`, `fechado`), com marcação manual de envio;
- manter o registro permanente de clientes/projetos fechados (popup **Fechados**);
- consultar amostras automáticas e manuais;
- corrigir projeto, competência, horas faturadas e dias úteis;
- definir se a amostra cobre o projeto inteiro ou pacotes específicos;
- identificar duplicidades;
- excluir amostras incorretas;
- consultar mensagens ignoradas pela automação;
- cadastrar manualmente uma amostra.

### Geração automática

Só gerentes. Gera, de uma vez, os **rascunhos de todos os projetos com horas** numa competência — o mesmo conteúdo da busca por cliente, sem precisar buscar projeto por projeto — e o que foi ajustado no último relatório aprovado de cada projeto já vem aplicado (nomes de grupo, performance, descrições, assinantes e o número do mês anterior como sugestão).

- Cada projeto aparece num **bloco próprio**, com status, horas, número do relatório e as ações. **Mês passado** mostra os rascunhos da competência, com o status de cada um (em revisão, aprovado, pulado, erro) e selos como "horas mudaram" (o Projectile mudou depois da geração) e "X h sem descrição" (lançamentos sem descrição viram aviso no editor, como na busca manual). **Mês atual** é uma prévia: quais projetos têm horas até agora e o que vai acontecer com cada um — nada é gravado.
- **Gerar rascunhos** cria o que falta (rodar de novo não duplica); projetos que ganharam horas depois aparecem em "projetos com horas depois da geração", com botão pra gerar só eles. Projetos fechados no Diagnóstico e famílias desativadas nas configurações ficam de fora.
- **Abrir no editor** abre o rascunho numa guia do editor de sempre (preview, chat, EN/DE). As edições são salvas sozinhas no servidor (indicador "Salvo no servidor"); a guia não fica no navegador — F5 fecha, o rascunho continua salvo.
- **Aprovar** exige o número do relatório (digitado na lista ou no editor) e os assinantes; barra número fora do formato, repetido no mês ou já usado por outro projeto no histórico. A aprovação grava no histórico e guarda os arquivos que vão pro cliente ("Arquivos").
- **Aprovados em massa**: cada bloco aprovado tem uma caixa de seleção no canto inferior direito. Com um ou mais marcados, aparece a barra com **Enviar ao cliente** (um e-mail por projeto, cada um com os seus destinatários, ou todos num e-mail só), **Ver** (abre todos no editor), **Baixar** (um ZIP com os arquivos aprovados) e **Reabrir**. Aprovados não mostram mais "Configuração".
- **Enviar ao cliente** (nos aprovados): abre o e-mail já preenchido — destinatários do último envio deste projeto, assunto e mensagem padrão — com os arquivos aprovados em anexo — dá pra escolher Excel, PDF ou os dois (só aparecem os formatos que foram aprovados). Sai da sua caixa, com a caixa da automação em cópia, e o bloco passa a "Enviado", mostrando quando e pra quem. Dá pra enviar de novo. Se o seu e-mail não estiver em `ALBERTO_EMAIL`, o modal avisa que o envio não vai contar no Diagnóstico.
- **Número do relatório já na prévia do mês atual:** o bloco de cada projeto do mês em andamento tem o campo do número (`SE.##.###`, com o formato conferido na hora). Ele fica guardado pra esse mês e vai direto pro rascunho quando ele for gerado. Vale pra um relatório por projeto (o padrão); com um relatório por pacote os números são digitados depois de gerar. Número já reservado pra outro projeto do mês é recusado.
- **Revisor** (campo no bloco): atribui o relatório a um colaborador da engenharia. Ele vê o relatório em **Minhas revisões** (item do menu que aparece pra quem tem relatório atribuído, com contador), abre no editor, ajusta o conteúdo e clica **Mandar pra aprovação** — com uma observação opcional. O número do relatório, os arquivos e a aprovação continuam com o gerente. O bloco passa a "Aguardando aprovação"; o gerente **aprova** ou **devolve** dizendo o que mudar (o revisor vê o pedido na lista e no editor). Sem revisor, o gerente revisa e aprova direto. Quem revisou um mês já fica atribuído no rascunho do mês seguinte do mesmo trabalho. No **mês atual**, que ainda não tem rascunho, o revisor escolhido no bloco fica guardado na configuração do projeto: o rascunho já nasce atribuído a ele, neste mês e nos próximos.
- **Configuração de cada projeto** (botão no bloco): gerar ou não, um relatório pro projeto (padrão) ou um por pacote, assinantes, arquivos e performance — só o que for diferente do **padrão geral**. Vale também nos próximos meses do mesmo trabalho, porque o Projectile abre um projeto novo por mês ("… Estribo 07.2026", "… 08.2026") e a configuração acompanha a família.

- **Geração personalizada** (botão **Nova geração personalizada**): relatórios fora do padrão mensal — de um colaborador, de um cliente, ou de uma mistura de projetos e pacotes de trabalho. Vale **só para o mês atual** e **não gera nada na hora**: o botão **Agendar geração** guarda o pedido (aparece em **Personalizados**, em "Agendados", com botão para cancelar) e os relatórios são gerados **junto com os automáticos**, quando você roda "Gerar rascunhos" do mês que fechou. Se o recorte não tiver horas nessa hora, o pedido fica com o motivo e a próxima rodada tenta de novo. Você monta **recortes** (cliente, projeto, pacote e colaborador; dentro de um recorte os filtros se cruzam, como "o Lucca nos projetos da Mercedes", e recortes diferentes se somam, sem contar a mesma hora duas vezes) e escolhe como as horas viram relatórios: **um relatório com tudo**, **um por projeto**, **um por pacote de trabalho** ou **um por colaborador**, e o que vira pacote dentro de cada um (um por projeto ou um por pacote de trabalho). A **prévia** (opcional) mostra o que sairia com as horas de agora. Cada relatório usa a **configuração do projeto** (assinantes, arquivos e revisor), a mesma dos relatórios mensais; se juntar projetos com configurações diferentes, vale o padrão geral e a prévia avisa. O botão **Configuração** do pedido (agendado ou já gerado) abre o mesmo painel dos projetos — Relatório, Arquivos, assinantes e empresas — para definir a configuração daquele personalizado; campo em branco herda a do projeto e, sem ela, a padrão. Num personalizado já gerado, salve e use **Regenerar** para aplicar. Depois de gerados, os rascunhos aparecem na opção **Personalizados** e seguem o mesmo caminho dos automáticos: revisor, aprovação, envio ao cliente (sem destinatários lembrados, porque não há projeto fixo), envio em massa e reabrir. Um personalizado em rascunho pode ser **apagado** (botão **Apagar**, com confirmação — não dá pra desfazer); aprovado ou enviado precisa ser reaberto antes, e os relatórios mensais não se apagam. Relatório que não cobre o projeto inteiro (filtrou colaborador ou só alguns pacotes) recebe o selo **recorte parcial** e, no Diagnóstico, nunca marca o projeto como enviado.

- **Geração automática do mês:** no **dia 1, às 06:00** (horário de São Paulo), o sistema gera sozinho os rascunhos do mês que fechou — e os pedidos da geração personalizada — sem você precisar clicar. **Só gera rascunhos: nunca envia nada.** O cabeçalho da aba mostra a próxima geração, e o "Padrão geral" tem o interruptor, o dia (1 a 28) e a hora. Se o servidor estiver desligado no horário, a geração roda quando ele voltar; se o Projectile estiver fora do ar, o sistema tenta de novo de hora em hora (até 5 vezes). Rodar pelo botão continua funcionando, e o que já existe nunca é duplicado. `AUTO_GENERATION_ENABLED=false` no `.env` para tudo por fora.

- **Avisos por e-mail:** o revisor recebe um e-mail quando um relatório é atribuído a ele ou devolvido com comentário; os gerentes recebem quando um relatório fica aguardando aprovação. O destinatário vem do cadastro do Projectile e o link abre direto o relatório no editor; o título da aba mostra `(n)` pendências. Dá para desligar em "Padrão geral" → "Avisar por e-mail" (ver `APP_BASE_URL` e a seção Microsoft Graph).

Próxima etapa: preferências de IA.

### Chat analítico

Só gerentes. Perguntas em português sobre os **últimos 12 meses** (a mesma janela do Painel de Gerência), respondidas com texto, gráfico e tabela, sempre com a fonte e o período usados. Cruza:

- **horas apontadas** (engenharia CAD+CAE) por cliente, projeto, colaborador, pacote, mês, centro de custo e faturável/não faturável — com contagem de pessoas, projetos e dias com apontamento, média por colaborador e % não faturável;
- **faturado x trabalhado** e performance por cliente, projeto e mês (mesma regra do Painel; não existe faturado por colaborador);
- **status de envio** dos relatórios por cliente, projeto e mês (mesma regra do Diagnóstico);
- **relatórios gerados** (histórico do `reports_db`);
- **quem está sem apontamento**: "quem não tem horas apontadas nesse mês" lista a engenharia ativa (a mesma do "Meu time") que não apontou nenhuma hora no período, sem passar pela consulta cruzada; sem período vale o mês atual.

Exemplos: "horas de cada colaborador por projeto no mês passado", "colaboradores com menos de 100 h em agosto", "top 5 projetos da Mercedes em 2026", "faturado x trabalhado por projeto em agosto", "quais projetos não tiveram relatório enviado em agosto?", "compare as horas por projeto de julho e agosto", "e em julho?" (continua a pergunta anterior).

Toda tabela tem ordenação por coluna, linha de total e botão **Baixar Excel**. O chat nunca executa consulta livre: a IA só escolhe entre medidas, dimensões e valores de um catálogo fixo, e todo número é calculado pelo backend — texto do Claude com número que não veio dos dados é descartado.

Pergunta sem período usa os últimos 12 meses, com aviso. Ano fora da janela recebe uma resposta fixa, sem consulta. Faturado só existe nos meses em que chegaram relatórios de faturamento; nos outros, o chat avisa em vez de calcular performance. O Jev (API oficial da TypeSafe) classifica a pergunta; sem chave, ou sem confiança, o Claude classifica.

## Histórico de relatórios (reports_db)

A cada `POST /generate` ou `POST /send-report`, a aplicação grava um snapshot imutável do relatório gerado (cabeçalho, grupos e atividades exatamente como recebidos), cria uma nova versão numerada do relatório correspondente e registra o resultado da geração — num segundo banco MySQL próprio, `reports_db`, totalmente separado do Projectile (roda como container Docker, ver [Começando](#começando)).

Pontos importantes:

- **Nunca bloqueia a geração do arquivo.** Se `reports_db` estiver fora do ar, com `REPORTS_DB_ENABLED=false`, ou qualquer chamada de persistência falhar, o `.xlsx`/`.pdf` é gerado e entregue normalmente — só fica sem registro no histórico dessa vez. A funcionalidade central do app nunca depende dessa infraestrutura secundária.
- O snapshot é **o payload exatamente como chegou em `/generate`** (já revisado/editado na tela, possivelmente via chat de IA) — não uma nova consulta ao Projectile.
- Duas gerações consecutivas do mesmo relatório (mesmo `project_code` + escopo de pacote + competência) viram versões sucessivas do mesmo `report`, nunca registros duplicados — protegido contra corrida em geração concorrente.
- O arquivo gerado é copiado pra `backend/data/report_artifacts/` (fora do Git), já que o caminho temporário original é apagado logo após o download.
- A resposta de `/generate` inclui os headers `X-Report-Id`/`X-Report-Version-Id`/`X-Report-Version-Number` (ou `X-Report-Ids` no caso `.zip`) quando a persistência funcionou — são **aditivos**, nunca assuma que vão estar presentes.
- **Lixeira**: apagar relatório no Histórico (com seleção múltipla) move pra Lixeira, onde fica restaurável por 30 dias (`reports.deleted_at`, migration `0009`); depois disso, ou com "Apagar de vez", sai do banco e os arquivos saem do disco. A purga dos vencidos roda uma vez por dia no agendador. O aviso da exclusão tem "Desfazer".
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
  | Coordenador | `COORDINATOR_LOGINS` | Gerar relatório (inclusive busca por cliente/projeto), Dashboard de horas (as próprias ou de qualquer colaborador de engenharia), o próprio Histórico e Diagnóstico de relatórios (sem horas/faturado/performance) — como o colaborador, só os últimos 12 meses e o ano atual em tudo |
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
| IA | Anthropic SDK 0.125 e truststore 0.10.4; Jev (TypeSafe AI, API oficial) no chat analítico, por HTTP com `requests` |
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
        auto_generation.py    # /auto-generation/* (só gerente)
        my_reviews.py         # /my-reviews/* (quem foi atribuído como revisor)
    analytics/             # chat analítico: catálogo, consulta cruzada, travas, gráficos, Excel
    auto_generation/       # geração automática: família, memória, rascunho, regras, fluxo
    integrations/
      jev.py               # cliente HTTP do Jev (API oficial da TypeSafe)
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
      auto_generation_store.py  # persistência da geração automática (tabelas auto_*, não fail-open)
      report_files.py       # montagem do XLSX/PDF, compartilhada por /generate e pela aprovação
      audit.py              # trilha de auditoria, fail-open
    tools/
      import_management_json.py  # importação única do antigo management_kpi.json
  templates/
    relatorio_final_template.xlsx
  tests/                  # suíte pytest
frontend/
  public/                 # logos da aplicação/e-mail
  src/
    App.tsx               # shell e troca das oito views
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
      AutoGenerationPanel.tsx  # aba Geração automática
      AutoCustomModal.tsx      # Nova geração personalizada (recorte livre)
      AutoReportBar.tsx        # barra da guia aberta a partir dela (gerente ou revisor)
      MyReviewsPanel.tsx       # Minhas revisões
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
      useAutoGenerationStore.ts
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
```

## Começando

### Pré-requisitos

- Python 3.11+
- Node.js 20+
- Docker (pro container `reports-mysql` do histórico de relatórios)
- Windows para usar o Credential Manager no ambiente real
- acesso de rede ao MySQL do Projectile
- chave Anthropic somente para chat de edição, tradução e chat analítico
- chave da TypeSafe (opcional) para o Jev no chat analítico
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

> O proxy do Vite cobre `/auth`, `/parse`, `/parse-db*`, `/generate`, `/send-report`, `/chat`, `/translate-activities`, `/reports`, `/artifacts`, `/analytics`, `/auto-generation`, `/my-reviews`, `/my-hours`, `/management` e `/health`. Rota nova de API precisa entrar em `frontend/vite.config.ts`, senão o dev server devolve 404 (o build servido pelo FastAPI não tem esse problema).

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
| `PROJECTILE_DB_WARMUP` | abre as conexões do pool em segundo plano no start (a conexão nova no Projectile leva ~20 s; com isso a primeira tela não paga isso) | `true` |
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
| `TYPESAFE_API_KEY` | Jev pela API oficial da TypeSafe (`api.typesafe.ai/v1/systemone`) | sem default; sem chave o Claude classifica (1 chamada a mais por pergunta). Com chave, a pergunta e as listas de clientes/colaboradores/projetos vão pra TypeSafe AI |
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
| `SESSIONS_BACKEND` | sessões/rate-limit | `memory` (default) ou `redis` (containers; exige `REDIS_URL`) |
| `REDIS_URL` | Redis das sessões/trava de envio | sem default; obrigatória com `SESSIONS_BACKEND=redis` |
| `PROCESS_ROLE` | topologia de processos | `all` (default, NSSM), `web` (só HTTP) ou `worker` (só background) |
| `APP_BASE_URL` | links dos avisos por e-mail | `http://localhost:8011` |
| `PROJECTILE_DB_PASSWORD` / `REPORTS_DB_PASSWORD` | senhas em container | prioridade sobre o Credential Manager (containers não têm keyring) |
| `PIP_EXTRA_ARGS` / `NPM_CI_ARGS` | build da imagem em rede com proxy SSL | vazios; ver "Produção em containers" |

O app registration do Azure precisa de permissões de aplicação `Mail.Read` e `Mail.Send` com consentimento administrativo. Restrinja o escopo com Exchange Application Access Policy no ambiente real.

## Comandos

| Comando | O que faz |
|---|---|
| `python -m pytest backend/tests -v` | executa os testes do backend (testes de `reports_db` pulam sem Docker) |
| `cd backend && ruff check app tests` | lint do backend (config em `backend/pyproject.toml`) |
| `cd backend && ruff format --check app tests` | checagem de formatação do backend |
| `cd backend && mypy` | typecheck dos módulos cobertos (ver `[tool.mypy].files`) |
| `docker compose up -d reports-mysql` | sobe o container do histórico de relatórios |
| `alembic upgrade head` | aplica as migrations pendentes do `reports_db` |
| `alembic revision --autogenerate -m "..."` | gera uma nova migration a partir de `reports_schema.py` |
| `npm --prefix frontend test` | executa os testes Vitest |
| `npm --prefix frontend run lint` | checa tipos com `tsc --noEmit` |
| `npm --prefix frontend run format:check` | checagem de formatação (Prettier; `npm run format` escreve) |
| `npm --prefix frontend run build` | checa tipos e gera `frontend/dist` |
| `npm --prefix frontend run dev` | inicia Vite com HMR |
| `npm --prefix frontend run preview` | serve o build do Vite em `:5173` |
| `python -m backend.app.worker` | roda só os loops de background (topologia worker) |

Backend: ruff (lint + format) e mypy rodam no CI (job `backend-lint`); frontend: `tsc`, Prettier e build no `frontend-build`.

## API

Todas as rotas abaixo exigem cookie de sessão, exceto `POST /auth/login` e `GET /health`.

### Autenticação

| Método e rota | Função |
|---|---|
| `POST /auth/login` | autentica no Projectile e cria sessão |
| `GET /auth/me` | recupera a sessão atual |
| `POST /auth/logout` | encerra a sessão |

### Saúde do sistema

| Método e rota | Função |
|---|---|
| `GET /health` | público, sem login: `{status: "ok"\|"degraded"}` com 200/503, sem detalhe — pro monitor externo alertar quando `reports_db` ou o Projectile caem |
| `GET /health/details` | só gerente: check por check (`reports_db`, `projectile`, `scheduler`) com latência e motivo da falha, pra investigar |

### Relatórios e dashboard pessoal

| Método e rota | Função |
|---|---|
| `POST /parse` | lê um XLSX (`file`, `mode=single|multi`) |
| `POST /parse-db` | busca o usuário logado por mês/período |
| `POST /parse-db-client` | busca projetos selecionados; requer gerente ou coordenador |
| `GET /my-hours` | dashboard de horas (`current_month`, `last_3`, `last_6`, `last_12`); `employee_id` opcional pra gerente/coordenador ver alguém de engenharia (CAD+CAE) |
| `GET /my-hours/team` | visão "Meu time" do mês (`?month=AAAA-MM`); só gerente |
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
| `DELETE /reports` | move relatórios pra Lixeira (`{ids}`); `GET /reports?trash=true` lista a Lixeira |
| `POST /reports/restore` | restaura da Lixeira (`{ids}`) |
| `DELETE /reports/trash` | apaga de vez o que está na Lixeira (`{ids}`) |
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
| `GET /analytics/health` | saúde do sistema: geração dos últimos 30 dias (tentativas, falhas, tempo médio/p95, última falha), artefatos em disco, última rodada automática e mensagens ignoradas pelo polling |
| `POST /analytics/chat` | chat analítico: pergunta em português → `{reply, visualizations, tables, metadata, context}`. Consulta cruzada sobre um catálogo fixo (nunca SQL gerado por IA); Jev classifica e o Claude só planeja/explica |
| `POST /analytics/chat/export` | tabela já exibida no chat → `.xlsx` (não consulta nada) |
| `GET/PUT /auto-generation/config`, `PUT/DELETE /auto-generation/rules/{family_key}`, `PUT /auto-generation/families/{project_id}` | configuração da geração automática (padrão e por família de projeto) |
| `GET /auto-generation/competences[/{AAAA-MM}[/preview]]`, `POST /auto-generation/competences/{AAAA-MM}/run` | rascunhos de uma competência, prévia do mês atual e "gerar agora" |
| `GET/PUT/PATCH/POST /auto-generation/reports/{id}[/draft\|numbers\|approve\|skip\|reopen\|regenerate\|files]` | um rascunho: detalhe, salvar (trava por versão), números, aprovar, pular, reabrir, regenerar, arquivos aprovados |
| `GET /auto-generation/files?ids=…` | download em lote dos arquivos aprovados (ZIP) |
| `GET/POST /auto-generation/custom`, `DELETE /auto-generation/custom/{id}`, `POST /auto-generation/custom/preview` | geração personalizada: lista, criação, exclusão (só rascunho) e prévia (sem gravar) de relatórios de um recorte livre de colaborador/cliente/projeto/pacote |
| `POST /auto-generation/send` | vários aprovados num e-mail só |
| `GET/POST /auto-generation/reports/{id}/send` | envio ao cliente: o que o e-mail abre preenchido / enviar os arquivos aprovados |
| `GET /auto-generation/reviewers`, `PUT /auto-generation/reports/{id}/reviewer`, `POST /auto-generation/reports/{id}/return` | revisão (gerente): quem pode revisar, atribuir/tirar revisor, devolver com comentário |
| `GET /my-reviews[/summary]`, `GET /my-reviews/{id}`, `PUT /my-reviews/{id}/draft`, `POST /my-reviews/{id}/submit` | Minhas revisões (qualquer usuário, só os atribuídos a ele): lista, contadores do menu, abrir, salvar, mandar pra aprovação |

**Gerente ou coordenador** (`test_coordinator_access.py` exige que toda rota nova desses routers esteja classificada numa das duas listas):

| Método e rota | Função |
|---|---|
| `GET /management/send-status` | status de envio por projeto/mês e opções de filtro, sem números de KPI; coordenador só nos últimos 12 meses ou no ano atual |
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

## Produção em containers (Docker)

Topologia recomendada a partir de 2026-09-29 (`docker-compose.prod.yml`): a mesma imagem roda dois processos — **web** (HTTP, `PROCESS_ROLE=web`) e **worker** (agendador da geração automática + polling de e-mail, `PROCESS_ROLE=worker`) — ao lado do **reports-mysql** e do **redis**.

- **Sessões/rate-limit e a trava de envio** ficam no Redis (`SESSIONS_BACKEND=redis`): reiniciar o backend não desloga ninguém e os dois processos enxergam o mesmo estado. Sem `REDIS_URL` o backend falha alto — não há queda silenciosa pra memória em produção.
- **Segredos:** não existe Windows Credential Manager dentro do container. Defina `PROJECTILE_DB_PASSWORD` e `REPORTS_DB_PASSWORD` no `.env` do servidor (têm prioridade sobre o keyring, ver `backend/app/db_credentials.py`).
- **Primeira subida** (uma vez):
  ```powershell
  docker compose -f docker-compose.prod.yml up -d --build
  docker compose -f docker-compose.prod.yml run --rm --no-deps web alembic upgrade head
  ```
- **Atualizações** (mantém a regra de ouro: nunca sobe com migration falhando):
  ```powershell
  .\scripts\atualizar-servidor-docker.bat
  ```
  O script faz `git pull`, builda com tag de data/hora (`IMAGE_TAG`), sobe banco + Redis, aplica `alembic upgrade head`, sobe web + worker e espera o web responder em `/health` (até 90 s; qualquer resposta HTTP conta, o 503 de um Projectile lento não reverte). **Se o web não responder, volta sozinho para a tag anterior** — mas a migration não é desfeita: confira se o código antigo é compatível com o schema novo. A tag anterior fica em `.last_image_tag.bak`.
- **Rollback manual:** `set IMAGE_TAG=<tag anterior>` e `docker compose -f docker-compose.prod.yml up -d` (sem rebuild).
- **Arquivos de relatório:** o volume `backend_data` (montado em `/app/backend/data` no web E no worker) guarda `report_artifacts/`; sem ele cada update apagaria os arquivos e o download do Histórico quebraria. O worker tem healthcheck (`python -m backend.app.worker --check`): o agendador grava um heartbeat no Redis a cada ciclo e o check falha se ele parar.
- **Staging na mesma máquina:** crie um `.env.staging` (mesmas chaves, portas diferentes — ex. `8011` do compose é a única porta publicada) e rode com projeto/volumes separados:
  ```powershell
  docker compose -f docker-compose.prod.yml -p relatorio-staging --env-file .env.staging up -d --build
  ```
- **Monitoração:** o `web` tem healthcheck no `/health`; um monitor externo (Uptime Kuma etc.) pode apontar pro mesmo endereço. Erros vão pro Sentry/GlitchTip self-hosted — ver "Observabilidade (logs e erros)".
- **Redes com inspeção de SSL (proxy corporativo):** o `pip` e o `npm` de dentro do container não conhecem a CA da empresa e o build falha com `CERTIFICATE_VERIFY_FAILED`/`SELF_SIGNED_CERT_IN_CHAIN`. Duas saídas: injetar a CA corporativa na imagem (ideal) ou, para destravar, apontar no `.env` do build:
  ```powershell
  $env:PIP_EXTRA_ARGS="--trusted-host pypi.org --trusted-host files.pythonhosted.org"
  $env:NPM_CI_ARGS="--strict-ssl=false"
  ```
  O `docker-compose.prod.yml` repassa as duas como build args (vazias por padrão — nada inseguro é fixado na imagem).

O fluxo antigo (Python nativo + NSSM, `atualizar-servidor.bat`) continua funcionando durante a transição; migre quando o servidor tiver Docker rodando os quatro serviços.

## Observabilidade (logs e erros)

- **Request-id:** toda resposta leva `X-Request-Id` (o cliente pode mandar o próprio — só ids simples de até 64 caracteres são aceitos; qualquer coisa estranha vira um id novo). O mesmo id aparece em toda linha de log daquela requisição, então um erro reportado pelo usuário (com o id no header) é rastreável no log.
- **Formato do log:** `LOG_FORMAT=text` (padrão, legível) ou `LOG_FORMAT=json` (uma linha JSON por evento, pra coletor de log). `SLOW_REQUEST_MS` (padrão 3000) gera um aviso `Requisição lenta` acima do limiar; `0` loga toda requisição (depuração) e negativo desliga.
- **Erro não tratado:** vira `500` JSON genérico com o request-id no header — o detalhe real (stack, mensagem) fica só no log e, se configurado, no Sentry. Nada de credencial ou dado pessoal é registrado.
- **Sentry/GlitchTip self-hosted:** com `SENTRY_DSN` preenchido no `.env`, erros não tratados são enviados (o GlitchTip usa o mesmo protocolo do Sentry; `send_default_pii=False`, sem tracing de performance). Sem DSN, nada sai do servidor. Para testar: suba o GlitchTip, crie um projeto, copie o DSN pro `.env`, reinicie o backend e provoque um erro — o evento aparece com a tag `request_id`.

Esboço do GlitchTip no mesmo host (stack em compose próprio, separado do compose do app; siga a documentação oficial para atualizações):

```yaml
# docker-compose.glitchtip.yml — suba com: docker compose -f docker-compose.glitchtip.yml up -d
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: glitchtip
      POSTGRES_PASSWORD: troque-esta-senha
      POSTGRES_DB: glitchtip
    volumes: ["glitchtip_pg:/var/lib/postgresql/data"]
    restart: unless-stopped
  redis:
    image: redis:7-alpine
    restart: unless-stopped
  web:
    image: glitchtip/glitchtip
    depends_on: [postgres, redis]
    ports: ["8080:8080"]
    environment: &glitchtip_env
      DATABASE_URL: postgres://glitchtip:troque-esta-senha@postgres:5432/glitchtip
      SECRET_KEY: troque-esta-chave
      PORT: 8080
      EMAIL_URL: consolemail://
      GLITCHTIP_DOMAIN: http://localhost:8080
      DEFAULT_FROM_EMAIL: glitchtip@localhost
      CELERY_BROKER_URL: redis://redis:6379/0
    volumes: ["glitchtip_uploads:/code/uploads"]
    restart: unless-stopped
  worker:
    image: glitchtip/glitchtip
    command: ./bin/run-celery-with-beat.sh
    depends_on: [postgres, redis]
    environment: *glitchtip_env
    volumes: ["glitchtip_uploads:/code/uploads"]
    restart: unless-stopped
volumes:
  glitchtip_pg:
  glitchtip_uploads:
```

## Troubleshooting

- **Login ou dados não conectam:** confira variáveis `PROJECTILE_DB_*`, senha no Credential Manager e acesso à rede interna.
- **403 em páginas gerenciais:** o login não está em `MANAGEMENT_PANEL_LOGINS` (ou em `COORDINATOR_LOGINS`, pro Diagnóstico); reinicie o backend após alterar `.env`.
- **403 "Fora do período permitido" (coordenador ou colaborador):** quem não é gerente só vê e filtra os últimos 12 meses e o ano atual — na busca do Gerar relatório, no Diagnóstico, no Dashboard de horas, no Histórico e em Minhas revisões. A tela só oferece esses meses; o 403 aparece quando a chamada vai direto na API (ou numa guia antiga com um mês de fora).
- **Chat analítico lento na 1ª pergunta (~20 s):** é a carga das horas da janela de 12 meses; as seguintes usam o cache de 15 minutos.
- **Chat analítico sempre com `classifier: claude`:** falta `TYPESAFE_API_KEY`, ou o Jev está fora do ar ou sem confiança. Funciona igual, com uma chamada a mais ao Claude.
- **403 na tradução:** o login não está em `TRANSLATE_ALLOWED_LOGINS`.
- **Chat/tradução 500:** `ANTHROPIC_API_KEY` ausente ou modelo inválido.
- **E-mail 400/502:** confira variáveis Azure/Graph, permissões e Application Access Policy.
- **Vite retorna 404 em uma tela interna:** a rota da API provavelmente falta no proxy de `frontend/vite.config.ts` (seção Desenvolvimento).
- **Logo ausente no build:** confirme os arquivos em `frontend/public/` antes de compilar.
- **Template perde logo/desenhos:** não use `openpyxl.save()` na geração.
- **`/generate` funciona mas nunca aparece `X-Report-Id` na resposta:** `reports-mysql` está fora do ar, `REPORTS_DB_ENABLED=false`, ou falta senha no keyring `reports_mysql` — isso é esperado ser silencioso (fail-open), não um erro; confira os logs do backend pra ver a causa.
- **Painel de Gerência/Diagnóstico responde 502:** esses dados vivem no `reports_db` e, diferente do histórico, não têm fail-open — confira se o container `reports-mysql` está de pé (`docker compose ps`) e a senha no keyring `reports_mysql`.
- **Algo caiu e não se sabe o quê:** `GET /health` (público) diz se o sistema está `ok` ou `degraded`; `GET /health/details` (gerente) mostra qual dependência falhou (reports_db, Projectile ou agendador), com latência e motivo. Use isso antes de abrir o log.
- **Importação do JSON de gerência recusa com "já tem dados de gerência sem registro de importação":** o backend novo subiu antes da importação e o polling de e-mail recriou as amostras a partir dos e-mails — **sem** as correções manuais feitas no Diagnóstico, que só o JSON tem. Rode `python -m backend.app.tools.import_management_json --replace-existing`: o JSON prevalece e o que estava no banco fica guardado em `mgmt_meta`.
- **`alembic upgrade head` falha com "tabela já existe":** o schema já tem tabelas de uma tentativa anterior sem `alembic_version` atualizada — confira `SELECT * FROM alembic_version` no `reports_db` antes de rodar de novo.
