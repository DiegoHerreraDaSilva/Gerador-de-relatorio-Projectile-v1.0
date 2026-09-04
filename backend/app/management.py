"""Painel de gerência — KPIs de engenharia (horas trabalhadas, faturadas e não
faturáveis), reconstruindo dentro do app um relatório que hoje só existe num
Power BI separado. Ver `backend/app/projectile_db.py:fetch_engineering_hours`
pra fonte dos dados automáticos (banco do Projectile).

Fórmulas confirmadas com o usuário e validadas batendo os números de um
relatório Power BI de referência:
- Trabalhadas = soma de horas dos centros de custo CAD+CAE no mês (banco).
- Faturadas = input manual do gerente (não existe no Projectile).
- Perf. H = Faturadas - Trabalhadas (calculado).
- KPI % (performance) = Perf. H / Trabalhadas.
- Horas NãoFat = soma de horas cujo pacote de trabalho tem `tjob.pExternal =
  '0'`. Chegou a existir uma lista manual de nomes de pacote (ex:
  "Treinamento") pra essa classificação, mas uma auditoria estatística nesta
  sessão mostrou que `pExternal` bate de forma consistente pros pacotes que
  importam de verdade (ativos hoje e com apontamento nos últimos 12 meses —
  0 inconsistência nos dois recortes testados); o campo só é confuso no
  histórico antigo/fechado, fora do que qualquer período do painel consulta
  na prática. `pExternal` é mais confiável que qualquer lista mantida à mão
  e não precisa de manutenção.
- KPI % (não faturável) = Horas NãoFat / Trabalhadas.
- Elaboração dos relatórios (dias) = automática por padrão (ver
  `email_ingest.py`), com override manual por mês continuando disponível.

Persistência: os valores manuais precisam sobreviver a reinícios do backend,
diferente do resto do app (que só usa `tempfile`, sem nada persistente).
Guarda isso num único JSON simples em `backend/data/management_kpi.json` —
não é um banco, só um arquivo, no mesmo nível de simplicidade do resto do
projeto.

Faturadas (`billed_hours`) e KPI (Dias) (`elaboration_days`) por mês têm duas
fontes possíveis:
- `manual_entries[mês]`: override manual do gerente (via `ExtraHoursInput` na
  tela), sempre que existir tem prioridade — comportamento idêntico ao de
  antes desta automação existir.
- `project_kpi_samples`: uma amostra por e-mail processado por
  `email_ingest.py` (relatório do Alberto pro cliente, com a caixa
  agente.reunioes@schwaben.com.br em cópia) — cada amostra guarda de qual
  e-mail veio (auditável), o projeto (fuzzy match contra `tproject`), o mês
  do relatório, as horas faturadas lidas da célula "Total de horas Mês/Ano:"
  e os dias úteis entre o fechamento do mês e o envio. Sem entrada manual pro
  mês, o valor exibido é o agregado dessas amostras: soma de `billed_hours`,
  média de `business_days`, ambos recortados pelo mesmo filtro de
  Cliente/Projeto já usado pro resto do painel. Guardar amostra a amostra
  (em vez de já manter soma/média corrente) é o que permite auditar e, se um
  match de projeto sair errado, remover só aquela amostra sem precisar
  "desfazer" um agregado.
"""
from __future__ import annotations

import calendar
import html
import json
import os
import time
from datetime import date, datetime, timezone
from uuid import uuid4

from .projectile_db import (
    extract_project_code,
    fetch_clients_for_projects,
    fetch_engineering_hours,
    fetch_project_details,
    fetch_project_ids_for_clients,
    fetch_project_ids_for_names,
    fetch_project_names_for_ids,
    open_connection,
)

def _load_management_panel_logins() -> set[str]:
    """Allowlist de logins com acesso ao Painel de Gerência, via
    MANAGEMENT_PANEL_LOGINS (logins separados por vírgula). Fallback pra
    {"dherrera"} se a env var estiver ausente/vazia — muda quem tem acesso
    sem precisar de commit + redeploy."""
    raw = os.environ.get("MANAGEMENT_PANEL_LOGINS", "")
    logins = {login.strip() for login in raw.split(",") if login.strip()}
    return logins or {"dherrera"}


MANAGEMENT_PANEL_LOGINS = _load_management_panel_logins()

# times/centros de custo de engenharia disponíveis pro filtro — o usuário
# confirmou que "CAD + CAE juntos" é a equipe (não existe um valor literal
# "Engenharia" no Projectile, ver investigação de schema desta sessão).
ENGINEERING_COST_CENTERS = ["CAD", "CAE"]

# sentinela pra "esse envio cobre o projeto inteiro" (amostra com
# pacote_scope=None) — usado como membro de um set junto com nomes de
# pacote de verdade, ver compute_monthly_kpis.
_PACOTE_SCOPE_ALL = "__ALL__"

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DATA_FILE = os.path.join(_DATA_DIR, "management_kpi.json")

_DEFAULT_DATA = {
    "manual_entries": {},
    "project_kpi_samples": [],
    "processed_message_ids": [],
    "skipped_messages": [],
}

# cache em memória das linhas cruas de `fetch_engineering_hours` por
# intervalo de datas — essa query é o gargalo real do painel (~50s neste
# MySQL legado, nenhuma tabela do join usa índice no lado certo). Sem esse
# cache, cada troca de filtro (Centro de Custo/Cliente/Projeto/Competência)
# refazia a mesma busca lenta; com ele, só a primeira busca de um período
# paga esse custo — o resto é filtrado em Python, na hora.
_HOURS_CACHE: dict[tuple[str, str], dict] = {}
_CACHE_TTL_SECONDS = 15 * 60


def _get_cached_rows(start_date: str, end_date: str, force_refresh: bool = False, conn=None) -> list[dict]:
    key = (start_date, end_date)
    entry = _HOURS_CACHE.get(key)
    if not force_refresh and entry and (time.time() - entry["fetched_at"]) < _CACHE_TTL_SECONDS:
        return entry["rows"]
    rows = fetch_engineering_hours(start_date, end_date, conn=conn)
    _HOURS_CACHE[key] = {"fetched_at": time.time(), "rows": rows}
    return rows


def _load_data() -> dict:
    if not os.path.exists(_DATA_FILE):
        return {
            "manual_entries": {},
            "project_kpi_samples": [],
            "processed_message_ids": [],
            "skipped_messages": [],
        }
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("manual_entries", {})
    data.setdefault("project_kpi_samples", [])
    data.setdefault("processed_message_ids", [])
    data.setdefault("skipped_messages", [])

    # migração retroativa: amostras gravadas antes da tela de Diagnóstico
    # existir não têm `sample_id`/`source`/`edited` — sem um id estável não
    # dá pra editar/apagar uma amostra específica (email_message_id não é
    # único quando um e-mail tem vários anexos). Salva de volta só se algo
    # mudou, pra não reescrever o arquivo à toa a cada leitura.
    migrated = False
    for sample in data["project_kpi_samples"]:
        if "sample_id" not in sample:
            sample["sample_id"] = uuid4().hex
            migrated = True
        if "source" not in sample:
            sample["source"] = "email"
            migrated = True
        if "edited" not in sample:
            sample["edited"] = False
            migrated = True
        if "pacote_scope" not in sample:
            # amostras antigas (antes do modo "por pacote de trabalho")
            # sempre cobriam o projeto inteiro — None preserva esse
            # comportamento em vez de marcar dado antigo como "parcial".
            sample["pacote_scope"] = None
            migrated = True
    if migrated:
        _save_data(data)
    return data


def _save_data(data: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_manual_entry(month: str, billed_hours: float | None, elaboration_days: float | None) -> None:
    data = _load_data()
    data["manual_entries"][month] = {"billed_hours": billed_hours, "elaboration_days": elaboration_days}
    _save_data(data)


def is_message_processed(message_id: str) -> bool:
    """Consultado por `email_ingest.py` antes de baixar/processar um e-mail —
    garante idempotência mesmo com pollings sobrepostos ou reinícios do
    backend (`--reload`) no meio de um ciclo."""
    data = _load_data()
    return message_id in data["processed_message_ids"]


def append_project_kpi_sample(sample: dict) -> None:
    """Registra uma amostra vinda de um e-mail processado com sucesso
    (`email_ingest.process_new_emails`) e marca o e-mail como processado, na
    mesma escrita — evita reprocessar o mesmo e-mail numa chamada futura. Um
    e-mail com vários anexos (vários projetos) chama isso uma vez por anexo,
    todas com o mesmo `email_message_id` — só adiciona o id à lista de
    processados na primeira vez, pra não duplicar."""
    data = _load_data()
    data["project_kpi_samples"].append(sample)
    if sample["email_message_id"] not in data["processed_message_ids"]:
        data["processed_message_ids"].append(sample["email_message_id"])
    _save_data(data)


def append_skipped_message(message_id: str, received_at: str, reason: str) -> None:
    """Registra um e-mail (ou um anexo específico dele, quando outros anexos
    do mesmo e-mail já geraram amostra com sucesso) que não gerou amostra
    (sem anexo .xlsx reconhecível, "Total de horas" não encontrado, etc) e
    marca o e-mail como processado — não fica tentando de novo a cada
    polling, mas fica visível no diagnóstico."""
    data = _load_data()
    data["skipped_messages"].append({
        "message_id": message_id, "received_at": received_at, "reason": reason,
    })
    if message_id not in data["processed_message_ids"]:
        data["processed_message_ids"].append(message_id)
    _save_data(data)


def list_samples(month: str | None = None) -> dict:
    """Usado pela tela de Diagnóstico (`GET /management/kpis/samples`) —
    mostra de onde vieram os números automáticos (e manuais) de cada
    (projeto, mês), e o que foi pulado, já que o match de projeto é
    automático e sem revisão humana. `month=None` lista tudo (aba "Todos" da
    tela); com `month`, filtra só aquele mês, mesmo comportamento de antes."""
    data = _load_data()
    samples = data["project_kpi_samples"]
    skipped = data["skipped_messages"]
    if month is not None:
        samples = [s for s in samples if s.get("month") == month]
        skipped = [s for s in skipped if str(s.get("received_at") or "")[:7] == month]
    samples = sorted(samples, key=lambda s: s.get("received_at") or "", reverse=True)
    skipped = sorted(skipped, key=lambda s: s.get("received_at") or "", reverse=True)
    return {"samples": samples, "skipped_messages": skipped}


def update_project_kpi_sample(sample_id: str, patch: dict) -> bool:
    """Corrige uma amostra existente (projeto/mês/horas/dias) — usado pela
    tela de Diagnóstico quando o match automático ou a leitura de horas
    erraram. Marca `edited=True` se a amostra era de e-mail (`source=
    "email"`), preservando a distinção entre dado automático corrigido e
    dado 100% manual. Devolve `False` se `sample_id` não existir (o endpoint
    responde 404 nesse caso)."""
    data = _load_data()
    for sample in data["project_kpi_samples"]:
        if sample.get("sample_id") != sample_id:
            continue
        allowed_fields = {"project_id", "project_name", "month", "billed_hours", "business_days"}
        for key, value in patch.items():
            if key in allowed_fields:
                sample[key] = value
        if sample.get("source") == "email":
            sample["edited"] = True
        _save_data(data)
        return True
    return False


def delete_project_kpi_sample(sample_id: str) -> bool:
    """Remove uma amostra — usado pela tela de Diagnóstico pra tirar um
    match errado do cálculo. Não mexe em `processed_message_ids`: o e-mail
    original continua marcado como processado e não volta a ser reprocessado
    no próximo polling (decisão confirmada com o usuário)."""
    data = _load_data()
    samples = data["project_kpi_samples"]
    remaining = [s for s in samples if s.get("sample_id") != sample_id]
    if len(remaining) == len(samples):
        return False
    data["project_kpi_samples"] = remaining
    _save_data(data)
    return True


def create_manual_project_kpi_sample(
    project_id: str, project_name: str, month: str, billed_hours: float, business_days: float
) -> dict:
    """Cadastro manual — usado pela tela de Diagnóstico quando um relatório
    foi enviado fora do fluxo de e-mail, ou o match automático nunca achou o
    projeto certo. `email_message_id` sintético (`manual-<uuid>`) só pra
    caber no mesmo mecanismo de idempotência de `append_project_kpi_sample`
    (nunca colide com um id real do Graph). `match_score=1.0` porque não
    passou por fuzzy match — foi escolhido direto pelo gerente."""
    sample = {
        "email_message_id": f"manual-{uuid4().hex}",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "sender": "manual",
        "report_project_text": project_name,
        "project_id": project_id,
        "project_name": project_name,
        "match_score": 1.0,
        "month": month,
        "billed_hours": billed_hours,
        "business_days": business_days,
        "sample_id": uuid4().hex,
        "source": "manual",
        "edited": False,
        # cadastro manual sempre representa o projeto inteiro — não tem
        # seletor de pacote de trabalho no formulário de Diagnóstico.
        "pacote_scope": None,
    }
    append_project_kpi_sample(sample)
    return sample


def _add_months(base: date, delta: int) -> date:
    month_index = base.month - 1 + delta
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _resolve_period(months: int, year: int | None) -> tuple[date, date, list[str]]:
    """Resolve o período de consulta: "ano" fechado (Jan-Dez de um ano
    específico, quando `year` é passado) ou os últimos `months` meses
    corridos a partir de hoje (padrão). Retorna (range_start, range_end,
    month_keys) — `month_keys` em ordem decrescente ("YYYY-MM")."""
    if year is not None:
        range_start = date(year, 1, 1)
        range_end = date(year, 12, 31)
        month_keys = sorted({date(year, m, 1).strftime("%Y-%m") for m in range(1, 13)}, reverse=True)
    else:
        today = date.today()
        range_start = _add_months(date(today.year, today.month, 1), -(months - 1))
        range_end_day = calendar.monthrange(today.year, today.month)[1]
        range_end = date(today.year, today.month, range_end_day)
        month_keys = sorted({_add_months(range_start, i).strftime("%Y-%m") for i in range(months)}, reverse=True)
    return range_start, range_end, month_keys


def _build_month_row(month_key: str, bucket: dict | None, manual: dict, auto: dict | None) -> dict:
    """Monta a linha de resultado de um mês a partir do bucket agregado do
    banco (worked_hours/nonbillable_hours), do override manual do gerente e
    da amostra automática (`project_kpi_samples`) — mesma regra de
    precedência de sempre: manual > auto > None."""
    bucket = bucket or {"worked_hours": 0.0, "nonbillable_hours": 0.0}
    worked_hours = round(bucket["worked_hours"], 2)
    nonbillable_hours = round(bucket["nonbillable_hours"], 2)

    if manual.get("billed_hours") is not None:
        billed_hours = manual.get("billed_hours")
        billed_hours_source = "manual"
    elif auto:
        billed_hours = round(auto["billed_hours"], 2)
        billed_hours_source = "auto"
    else:
        billed_hours = None
        billed_hours_source = None

    if manual.get("elaboration_days") is not None:
        elaboration_days = manual.get("elaboration_days")
        elaboration_days_source = "manual"
    elif auto and auto["days"]:
        elaboration_days = round(sum(auto["days"]) / len(auto["days"]), 2)
        elaboration_days_source = "auto"
    else:
        elaboration_days = None
        elaboration_days_source = None

    perf_hours = round(billed_hours - worked_hours, 2) if billed_hours is not None else None
    perf_kpi_pct = (perf_hours / worked_hours) if perf_hours is not None and worked_hours > 0 else None
    nonbillable_kpi_pct = (nonbillable_hours / worked_hours) if worked_hours > 0 else None

    return {
        "month": month_key,
        "worked_hours": worked_hours,
        "billed_hours": billed_hours,
        "billed_hours_source": billed_hours_source,
        "perf_hours": perf_hours,
        "perf_kpi_pct": perf_kpi_pct,
        "elaboration_days": elaboration_days,
        "elaboration_days_source": elaboration_days_source,
        "nonbillable_hours": nonbillable_hours,
        "nonbillable_kpi_pct": nonbillable_kpi_pct,
    }


def compute_monthly_kpis(
    months: int,
    year: int | None = None,
    cost_centers: list[str] | None = None,
    clients: list[str] | None = None,
    projects: list[str] | None = None,
    packages: list[str] | None = None,
    force_refresh: bool = False,
) -> dict:
    data = _load_data()
    manual_entries: dict = data["manual_entries"]

    active_cost_centers = cost_centers or ENGINEERING_COST_CENTERS

    # dois modos de período: "ano" fechado (Jan-Dez de um ano específico) ou
    # os últimos N meses corridos a partir de hoje (padrão).
    range_start, range_end, month_keys = _resolve_period(months, year)

    # uma única conexão pras 4 consultas pequenas + a busca cara (quando não
    # está em cache) — a conexão em si é persistente/reaproveitada entre
    # requisições (ver `projectile_db._get_connection`), então isso só deixa
    # explícito que essas chamadas usam a mesma conexão do início ao fim
    # deste request, sem reabrir uma pra cada lookup.
    conn = open_connection()

    # Cliente e Projeto resolvem pro mesmo mecanismo de filtro
    # (tj.pProject IN (...), ver fetch_engineering_hours) — com os dois
    # ativos ao mesmo tempo, só entra quem atende AMBOS (interseção dos
    # IDs de projeto).
    client_project_ids = fetch_project_ids_for_clients(clients, conn=conn) if clients else None
    project_name_ids = fetch_project_ids_for_names(projects, conn=conn) if projects else None
    if client_project_ids is not None and project_name_ids is not None:
        project_ids = sorted(set(client_project_ids) & set(project_name_ids))
    else:
        project_ids = client_project_ids if client_project_ids is not None else project_name_ids
    allowed_project_ids = set(project_ids) if project_ids is not None else None
    allowed_packages = set(packages) if packages else None
    cost_center_keywords = [cc.casefold() for cc in active_cost_centers]

    # a busca cara já vem com TODO o CAD+CAE do período, cacheada por
    # intervalo de datas — Centro de Custo/Cliente/Projeto são recortes
    # em Python sobre esse mesmo resultado, sem voltar no banco.
    all_rows = _get_cached_rows(range_start.isoformat(), range_end.isoformat(), force_refresh, conn=conn)

    buckets: dict[str, dict] = {}
    available_project_ids: set[str] = set()
    # (mês, nome do pacote) -> horas não faturáveis — pra alimentar a seção de
    # "Pacotes não faturáveis" abaixo dos gráficos, com o mesmo recorte de
    # filtros (Centro de Custo/Cliente/Projeto) já aplicado aqui; Competência
    # é filtrada depois, no frontend, junto com o resto da tela.
    package_buckets: dict[tuple[str, str], float] = {}
    # (mês, project_id) -> horas trabalhadas — pra alimentar a tabela
    # "Relatórios enviados" (um projeto só aparece num mês se de fato teve
    # apontamento nele, mesmo critério dos outros recortes desta função).
    project_month_hours: dict[tuple[str, str], float] = {}
    # (mês, project_id) -> pacotes de trabalho (texto bruto) com hora naquele
    # mês — usado pra decidir "enviado"/"parcial"/"não enviado" por projeto
    # (ver sent_scopes_by_project_month mais abaixo): um projeto só é
    # "enviado" de verdade se TODOS os pacotes com hora foram cobertos por
    # algum relatório mandado, não só qualquer um.
    project_month_pacotes: dict[tuple[str, str], set[str]] = {}
    # project_id -> "código do projeto" (prefixo do pacote de trabalho, ver
    # `extract_project_code`) — só pra exibição (prefixo nos dropdowns de
    # filtro do frontend), nunca usado como identificador de verdade.
    project_codes_by_id: dict[str, str] = {}
    # pacotes de trabalho disponíveis pro filtro — recorte de Centro de
    # Custo/Cliente/Projeto já aplicado, mas ANTES do filtro de Pacote em si
    # (senão escolher um pacote faria os outros sumirem do dropdown).
    available_packages: set[str] = set()
    for row in all_rows:
        row_cost_center = (row.get("cost_center") or "").casefold()
        if not any(kw in row_cost_center for kw in cost_center_keywords):
            continue
        project_id = row.get("project_id")
        if allowed_project_ids is not None and project_id not in allowed_project_ids:
            continue
        row_package = html.unescape(str(row.get("pacote") or "")).strip() or "Sem nome"
        available_packages.add(row_package)
        if allowed_packages is not None and row_package not in allowed_packages:
            continue
        row_date = row.get("data")
        month_key = row_date.strftime("%Y-%m") if hasattr(row_date, "strftime") else str(row_date)[:7]
        hours = round(float(row.get("horas") or 0), 3)
        if project_id:
            available_project_ids.add(project_id)
            pm_key = (month_key, project_id)
            project_month_hours[pm_key] = project_month_hours.get(pm_key, 0.0) + hours
            project_month_pacotes.setdefault(pm_key, set()).add(row_package)
            if project_id not in project_codes_by_id:
                code = extract_project_code(row.get("pacote"))
                if code:
                    project_codes_by_id[project_id] = code
        bucket = buckets.setdefault(month_key, {"worked_hours": 0.0, "nonbillable_hours": 0.0})
        bucket["worked_hours"] += hours
        if row.get("external") == "0":
            bucket["nonbillable_hours"] += hours
            package_key = (month_key, row_package)
            package_buckets[package_key] = package_buckets.get(package_key, 0.0) + hours

    available_projects = fetch_project_names_for_ids(sorted(available_project_ids), conn=conn)
    available_clients = fetch_clients_for_projects(sorted(available_project_ids), conn=conn)
    project_details = fetch_project_details(sorted(available_project_ids), conn=conn)
    # nome -> código, pro frontend prefixar a opção no dropdown de Projeto
    # sem mudar o valor usado no filtro (que continua sendo o nome).
    project_codes = {
        info["name"]: project_codes_by_id[pid]
        for pid, info in project_details.items()
        if pid in project_codes_by_id
    }
    # nome do projeto -> cliente, pro frontend só listar no dropdown de
    # Projeto quem pertence ao(s) cliente(s) já marcado(s) no filtro de
    # Cliente (os dois dropdowns hoje eram independentes).
    project_clients = {info["name"]: info["client"] or "Sem cliente" for info in project_details.values()}

    # billed_hours/elaboration_days automáticos: uma amostra por e-mail
    # processado por email_ingest.py, agregada por mês e recortada pelo mesmo
    # allowed_project_ids usado acima pra worked_hours/nonbillable_hours —
    # billed_hours é soma (vai "somando a cada e-mail recebido"),
    # elaboration_days é média das amostras do(s) projeto(s) filtrado(s).
    auto_by_month: dict[str, dict] = {}
    for sample in data.get("project_kpi_samples", []):
        if allowed_project_ids is not None and sample.get("project_id") not in allowed_project_ids:
            continue
        sample_month = sample.get("month")
        if not sample_month:
            continue
        auto_bucket = auto_by_month.setdefault(sample_month, {"billed_hours": 0.0, "days": []})
        auto_bucket["billed_hours"] += float(sample.get("billed_hours") or 0)
        days = sample.get("business_days")
        if days is not None:
            auto_bucket["days"].append(days)

    result_months = [
        _build_month_row(
            month_key,
            buckets.get(month_key),
            manual_entries.get(month_key) or {},
            auto_by_month.get(month_key),
        )
        for month_key in month_keys
    ]

    nonbillable_breakdown = [
        {"month": month_key, "package": package, "hours": round(hours, 2)}
        for (month_key, package), hours in package_buckets.items()
    ]

    # status por (projeto, mês) a partir das amostras de e-mail
    # (project_kpi_samples) — não é editável manualmente na tela, é marcado
    # quando a caixa agente.reunioes@ recebe o relatório daquele projeto (ver
    # email_ingest.py). Cada amostra carrega `pacote_scope`: None significa
    # "esse envio cobria o projeto inteiro" (_PACOTE_SCOPE_ALL), um texto
    # significa "só esse pacote de trabalho" — um projeto só é "enviado" de
    # verdade se TODOS os pacotes com hora naquele mês foram cobertos por
    # algum envio, não só qualquer um (era o bug: mandar 1 pacote marcava o
    # projeto inteiro como enviado).
    sent_scopes_by_project_month: dict[tuple[str, str], set[str]] = {}
    for sample in data.get("project_kpi_samples", []):
        sample_month = sample.get("month")
        sample_project_id = sample.get("project_id")
        if not sample_month or not sample_project_id:
            continue
        scope = sample.get("pacote_scope") or _PACOTE_SCOPE_ALL
        sent_scopes_by_project_month.setdefault((sample_month, sample_project_id), set()).add(scope)

    project_send_status = []
    for (month_key, project_id), hours in project_month_hours.items():
        if hours <= 0:
            continue
        details = project_details.get(project_id)
        if not details:
            continue
        sent_scopes = sent_scopes_by_project_month.get((month_key, project_id), set())
        all_pacotes = project_month_pacotes.get((month_key, project_id), set())
        if _PACOTE_SCOPE_ALL in sent_scopes or (all_pacotes and all_pacotes.issubset(sent_scopes)):
            status = "sent"
            missing_pacotes: list[str] = []
        elif sent_scopes:
            status = "partial"
            missing_pacotes = sorted(all_pacotes - sent_scopes)
        else:
            status = "none"
            missing_pacotes = []
        project_send_status.append({
            "month": month_key,
            "project_id": project_id,
            "project_name": details["name"] or "Sem nome",
            "client": details["client"] or "Sem cliente",
            "status": status,
            "missing_pacotes": missing_pacotes,
        })

    return {
        "months": result_months,
        "cost_centers": ENGINEERING_COST_CENTERS,
        "available_projects": available_projects,
        "available_clients": available_clients,
        "available_packages": sorted(available_packages, key=lambda p: p.casefold()),
        "project_codes": project_codes,
        "project_clients": project_clients,
        "nonbillable_breakdown": nonbillable_breakdown,
        "project_send_status": project_send_status,
    }
