"""Geração personalizada: relatório de um recorte LIVRE — colaborador, cliente,
projeto e pacote de trabalho, misturados, num período qualquer.

O recorte é uma lista de BLOCOS. Dentro de um bloco os filtros se cruzam (E:
"o Lucca nos projetos da Mercedes"); entre blocos as horas se somam (OU), sem
contar a mesma linha duas vezes. Dois eixos independentes dizem o que sai:

- `split_by` — QUANTOS relatórios: "nenhum" (um só com tudo), "projeto",
  "pacote" ou "colaborador";
- `package_unit` — o que vira "pacote" DENTRO de cada relatório: "projeto"
  (o pacote de trabalho vira o grupo) ou "pacote" (o prefixo da observação
  vira o grupo, como na busca manual em modo pacote).

Nada aqui grava: `collect`/`build_reports` só calculam; quem persiste é
`service.create_custom` (e `service.preview_custom` devolve o mesmo cálculo
sem gravar). Projectile sempre acessado como atributo do módulo
(`projectile_db.fetch_*`), pro `monkeypatch` dos testes alcançar."""

from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from .. import projectile_db
from ..services import auto_generation_store as store
from . import builder, families, rules

# marcador do `pacote_scope` de um relatório que NÃO cobre o projeto/pacote
# inteiro (filtrou colaborador ou só alguns pacotes). O Diagnóstico só marca
# "Enviado" quando o escopo cobre tudo; um texto que não é nome de pacote
# nenhum faz o projeto ficar "parcial", nunca "enviado" (ver
# `management.compute_monthly_kpis`).
PARTIAL_SCOPE = "Personalizado"
MAX_REPORTS = 100
MAX_MONTHS = 36
SPLIT_BY = ("nenhum", "projeto", "pacote", "colaborador")
PACKAGE_UNITS = ("projeto", "pacote")

_EMPLOYEES_TTL_SECONDS = 15 * 60
_EMPLOYEES_LOOKBACK_DAYS = 400
_employees_cache: dict = {"since": None, "at": 0.0, "items": None}


class InvalidScope(ValueError):
    """Recorte inválido (bloco vazio, colaborador fora da engenharia, período
    ao contrário, relatórios demais) — o serviço vira 400 com a mensagem."""


@dataclass
class Block:
    """Um bloco já resolvido. `project_ids` = None quer dizer "todos os
    projetos" (só vale com colaborador)."""

    project_ids: set[str] | None
    packages: set[str]
    employee_ids: list[str]
    clients: list[str]


@dataclass
class Resolved:
    start_competence: str
    end_competence: str
    start_date: str
    end_date: str
    label: str
    blocks: list[Block]
    split_by: str
    package_unit: str
    title: str
    # configuração PRÓPRIA do pedido (assinantes, empresas, arquivos): vale por cima da do projeto
    config: dict
    employees: dict[str, str]  # id → nome, só os pedidos
    warnings: list[str] = field(default_factory=list)


@dataclass
class CustomReport:
    key: str
    title: str
    client: str
    hours: float
    draft: dict
    partial: bool
    project_names: list[str]
    # revisor herdado da configuração do projeto (ou do que revisou o último aprovado)
    reviewer_login: str | None = None
    reviewer_name: str | None = None
    # avisos deste relatório (ex.: projetos com configurações diferentes)
    notes: list[str] = field(default_factory=list)


# --- validação e resolução do recorte -------------------------------------------


def _norm(text: str | None) -> str:
    return html.unescape(str(text or "")).strip().casefold()


def pacote_name(row: dict) -> str:
    """Nome do pacote de trabalho como `group_hours*` o enxergam (entidades
    HTML desfeitas, vazio = "Geral")."""
    return html.unescape(str(row.get("pacote") or "")).strip() or "Geral"


def _engineering_employees(since: str) -> list[dict]:
    cached = _employees_cache["items"]
    if cached is not None and _employees_cache["since"] == since and time.time() - _employees_cache["at"] < _EMPLOYEES_TTL_SECONDS:
        return cached
    items = projectile_db.fetch_engineering_employees(since, date.today().isoformat())
    _employees_cache.update(since=since, at=time.time(), items=items)
    return items


def _validate_period(scope: dict) -> tuple[str, str, str, str]:
    period = scope.get("period") or {}
    start, end = period.get("start", ""), period.get("end", "")
    try:
        (start_year, start_month), (end_year, end_month) = builder.parse_competence(start), builder.parse_competence(end)
    except builder.InvalidCompetence as e:
        raise InvalidScope("Período inválido — use mês/ano.") from e
    if (start_year, start_month) > (end_year, end_month):
        raise InvalidScope("O mês final vem antes do inicial.")
    months = (end_year - start_year) * 12 + end_month - start_month + 1
    if months > MAX_MONTHS:
        raise InvalidScope(f"O período tem {months} meses; o máximo é {MAX_MONTHS}.")
    return start, end, builder.competence_range(start)[0], builder.competence_range(end)[1]


def resolve(scope: dict) -> Resolved:
    """Confere o recorte contra o Projectile. O id de colaborador e o cliente
    que vêm da tela nunca são confiados: colaborador tem que estar na lista de
    engenharia (CAD/CAE), e os nomes que vão pro relatório vêm do Projectile."""
    start, end, start_date, end_date = _validate_period(scope)
    split_by, unit = scope.get("split_by", "nenhum"), scope.get("package_unit", "projeto")
    if split_by not in SPLIT_BY or unit not in PACKAGE_UNITS:
        raise InvalidScope("Organização do relatório inválida.")
    raw_blocks = scope.get("blocks") or []
    if not raw_blocks:
        raise InvalidScope("Adicione pelo menos um recorte.")

    wanted_employees = {str(e) for b in raw_blocks for e in (b.get("employee_ids") or [])}
    employees: dict[str, str] = {}
    if wanted_employees:
        since = min(start_date, (date.today() - timedelta(days=_EMPLOYEES_LOOKBACK_DAYS)).isoformat())
        known = {str(e["employee_id"]): e["name"] for e in _engineering_employees(since)}
        unknown = sorted(wanted_employees - set(known))
        if unknown:
            raise InvalidScope("Colaborador não encontrado na engenharia (CAD/CAE).")
        employees = {eid: known[eid] for eid in wanted_employees}

    blocks: list[Block] = []
    warnings: list[str] = []
    for number, raw in enumerate(raw_blocks, start=1):
        clients = [c for c in (raw.get("clients") or []) if str(c).strip()]
        explicit = [str(p) for p in (raw.get("project_ids") or []) if str(p).strip()]
        packages = {_norm(p) for p in (raw.get("packages") or []) if str(p).strip()}
        employee_ids = [str(e) for e in (raw.get("employee_ids") or [])]
        if not (clients or explicit or packages or employee_ids):
            raise InvalidScope(f"O recorte {number} está vazio — escolha cliente, projeto ou colaborador.")
        if packages and len(explicit) != 1:
            raise InvalidScope(f"No recorte {number}, pacotes só valem com exatamente um projeto escolhido.")
        project_ids: set[str] | None
        if clients:
            of_clients = {str(p) for p in projectile_db.fetch_project_ids_for_clients(clients)}
            project_ids = of_clients & set(explicit) if explicit else of_clients
            if not project_ids:
                warnings.append(f"O recorte {number} não encontrou projetos desse cliente.")
        elif explicit:
            project_ids = set(explicit)
        else:
            project_ids = None
        if packages and not (project_ids or set()):
            packages = set()
        blocks.append(Block(project_ids, packages, employee_ids, clients))

    return Resolved(
        start_competence=start,
        end_competence=end,
        start_date=start_date,
        end_date=end_date,
        label=builder.period_label(start, end),
        blocks=blocks,
        split_by=split_by,
        package_unit=unit,
        title=str(scope.get("title") or "").strip()[:200],
        config=clean_config(scope.get("config")),
        employees=employees,
        warnings=warnings,
    )


CONFIG_FIELDS = ("signer1_name", "signer1_company", "signer2_name", "signer2_company", "formats")


def clean_config(config: dict | None) -> dict:
    """Só os campos conhecidos e preenchidos: vazio/`None` é "herda"."""
    out: dict = {}
    for key in CONFIG_FIELDS:
        value = (config or {}).get(key)
        if isinstance(value, str):
            value = value.strip()
        if value:
            out[key] = value
    return out


# --- coleta das horas --------------------------------------------------------------


def _row_key(row: dict) -> tuple:
    return (
        str(row.get("data")),
        str(row.get("project_id")),
        str(row.get("employee_id")),
        row.get("pacote"),
        row.get("observacao"),
        float(row.get("horas") or 0),
        row.get("inicio"),
        row.get("fim"),
    )


def collect(resolved: Resolved) -> tuple[list[dict], list[str]]:
    """Uma consulta por bloco e a UNIÃO das linhas. Se dois blocos pegam o
    mesmo lançamento ele conta uma vez — como multiconjunto (dois lançamentos
    idênticos no MESMO bloco continuam sendo dois; só o que o outro bloco
    repete é descartado). Devolve as linhas e os avisos (bloco sem horas,
    linhas repetidas entre blocos)."""
    merged: dict[tuple, list[dict]] = {}
    warnings: list[str] = []
    repeated = 0
    for number, block in enumerate(resolved.blocks, start=1):
        rows = (
            projectile_db.fetch_custom_hours(
                resolved.start_date, resolved.end_date, sorted(block.project_ids) if block.project_ids is not None else None, block.employee_ids or None
            )
            if (block.project_ids is None or block.project_ids)
            else []
        )
        if block.packages:
            rows = [r for r in rows if _norm(pacote_name(r)) in block.packages]
        if not rows:
            warnings.append(f"O recorte {number} não tem horas no período.")
            continue
        for key, group in _group_by(rows, _row_key).items():
            have = merged.setdefault(key, [])
            if len(group) > len(have):
                have.extend(group[len(have) :])
            else:
                repeated += len(group)
    if repeated:
        warnings.append(f"{repeated} lançamento(s) apareciam em mais de um recorte e foram contados uma vez.")
    rows = [row for group in merged.values() for row in group]
    rows.sort(key=lambda r: (str(r.get("data")), str(r.get("inicio") or ""), str(r.get("project_id"))))
    return rows, warnings


def _group_by(rows: list[dict], key) -> dict:
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(key(row), []).append(row)
    return grouped


# --- o que cada relatório cobre ------------------------------------------------------


def covers_whole(blocks: list[Block], project_id: str, pacote: str | None, unit: str) -> bool:
    """O relatório cobre TODO esse projeto (e pacote, na unidade "pacote")?
    Só se algum bloco pega o projeto sem filtrar colaborador — e, na unidade
    projeto, sem filtrar pacotes (na unidade pacote, o pacote tem que estar
    entre os do bloco ou o bloco não filtrar pacote)."""
    for block in blocks:
        if block.employee_ids or block.project_ids is None or project_id not in block.project_ids:
            continue
        if unit == "projeto":
            if not block.packages:
                return True
        elif not block.packages or _norm(pacote) in block.packages:
            return True
    return False


# --- montagem dos relatórios ------------------------------------------------------------


def _project_infos(rows: list[dict]) -> dict[str, dict]:
    ids = sorted({str(r.get("project_id")) for r in rows if r.get("project_id")})
    details = projectile_db.fetch_project_details(ids) if ids else {}
    return {
        pid: {
            "name": families.clean((details.get(pid) or {}).get("name")) or pid,
            "client": families.clean((details.get(pid) or {}).get("client")) or "Sem cliente",
        }
        for pid in ids
    }


def _person(row: dict, employees: dict[str, str]) -> str:
    return employees.get(str(row.get("employee_id"))) or families.clean(row.get("person")) or "Sem colaborador"


def _title(resolved: Resolved, part: str | None, rows: list[dict], infos: dict[str, dict]) -> str:
    """Título do relatório na lista. Digitado pelo gerente: ele, e a parte
    (projeto/pacote/pessoa) quando a geração se divide. Senão o que o recorte
    tem em comum: o projeto, o cliente ou a pessoa quando é um só."""
    if resolved.title:
        return f"{resolved.title} — {part}" if part else resolved.title
    if part:
        return part
    projects = {infos[str(r["project_id"])]["name"] for r in rows if str(r.get("project_id")) in infos}
    clients = {infos[str(r["project_id"])]["client"] for r in rows if str(r.get("project_id")) in infos}
    people = {_person(r, resolved.employees) for r in rows}
    if len(projects) == 1:
        base = next(iter(projects))
    elif len(clients) == 1:
        base = next(iter(clients))
    elif len(people) == 1:
        base = next(iter(people))
    else:
        base = "Personalizado"
    return base


# o que o relatório personalizado herda da configuração do PROJETO (a mesma dos
# relatórios mensais, `auto_rules` por família): assinantes, arquivos e revisor
_INHERITED = (
    ("signer1_name", "assinante Schwaben"),
    ("signer1_company", "empresa Schwaben"),
    ("signer2_name", "assinante do cliente"),
    ("signer2_company", "empresa do cliente"),
    ("formats", "arquivos"),
)


def _reviewer_of(family_key: str, effective: dict, memories: dict[str, dict]) -> tuple[str, str] | None:
    """Revisor do projeto: o da configuração dele; sem ele, quem revisou o último
    relatório aprovado da família (mesma prioridade da rodada mensal)."""
    if effective.get("reviewer_login"):
        return effective["reviewer_login"], effective.get("reviewer_name") or effective["reviewer_login"]
    remembered = (memories.get(family_key) or {}).get("reviewer") or {}
    if remembered.get("login"):
        return remembered["login"], remembered.get("name") or remembered["login"]
    return None


def _config_for(
    group: list[dict],
    infos: dict[str, dict],
    overrides: dict[str, str],
    global_config: dict,
    family_rules: dict[str, dict],
    memories: dict[str, dict],
    own: dict | None = None,
) -> tuple[dict, tuple[str, str] | None, list[str]]:
    """Configuração de UM relatório: a do projeto (família) quando o relatório
    tem um projeto só — ou vários com a MESMA configuração; com projetos de
    configurações diferentes vale o padrão geral e o relatório leva um aviso."""
    own = own or {}
    default = {**rules.effective(global_config, None), **own}
    keys = sorted(
        {
            overrides.get(pid) or families.family_key(infos[pid]["client"], infos[pid]["name"])
            for pid in (str(r.get("project_id") or "") for r in group)
            if pid in infos
        }
    )
    if not keys:
        return default, None, []
    effective = {key: {**rules.effective(global_config, family_rules.get(key)), **own} for key in keys}
    reviewers = {key: _reviewer_of(key, effective[key], memories) for key in keys}
    first = keys[0]
    # o que o pedido define ele mesmo vale pra todos os projetos: não é diferença
    differing = [label for field_name, label in _INHERITED if field_name not in own and len({repr(effective[k].get(field_name)) for k in keys}) > 1]
    if len({reviewers[k] for k in keys}) > 1:
        differing.append("revisor")
    if not differing:
        return effective[first], reviewers[first], []
    return default, None, [f"os projetos deste relatório têm configurações diferentes ({', '.join(differing)}): valeu o padrão geral."]


def build_reports(resolved: Resolved, rows: list[dict], global_config: dict, today: date) -> list[CustomReport]:
    """Divide as linhas por `split_by` e monta o rascunho de cada relatório.
    `global_config` é a configuração GUARDADA do padrão geral (`auto_settings`);
    a de cada projeto (assinantes, arquivos, revisor) vem das regras da família."""
    if not rows:
        raise InvalidScope("Nenhuma hora encontrada nesse recorte e período.")
    infos = _project_infos(rows)
    multi_month = resolved.start_competence != resolved.end_competence
    overrides = _family_overrides()
    family_rules = store.get_rules()
    all_keys = sorted({overrides.get(pid) or families.family_key(info["client"], info["name"]) for pid, info in infos.items()})
    memories = store.get_memories(all_keys) if all_keys else {}

    def project_key(row: dict) -> str:
        """Chave do "projeto" do relatório: o `project_id`, ou a FAMÍLIA em
        período de vários meses (o Projectile abre um projeto por mês pro
        mesmo trabalho — sem juntar, cada mês viraria um pacote)."""
        pid = str(row.get("project_id") or "")
        info = infos.get(pid)
        if not multi_month or not info:
            return pid
        return overrides.get(pid) or families.family_key(info["client"], info["name"])

    def project_label(row: dict) -> str:
        info = infos.get(str(row.get("project_id") or ""), {})
        name = info.get("name") or str(row.get("project_id") or "")
        return families.family_label(name) if multi_month else name

    if resolved.split_by == "projeto":
        groups = _group_by(rows, project_key)
        labels = {k: project_label(g[0]) for k, g in groups.items()}
    elif resolved.split_by == "pacote":
        groups = _group_by(rows, lambda r: (project_key(r), pacote_name(r)))
        labels = {k: k[1] for k in groups}
    elif resolved.split_by == "colaborador":
        groups = _group_by(rows, lambda r: str(r.get("employee_id")))
        labels = {k: _person(g[0], resolved.employees) for k, g in groups.items()}
    else:
        groups = {"": rows}
        labels = {"": None}
    if len(groups) > MAX_REPORTS:
        raise InvalidScope(f"Esse recorte gera {len(groups)} relatórios; o máximo por geração é {MAX_REPORTS}. Reduza o recorte.")

    reports: list[CustomReport] = []
    for key, group in groups.items():
        # unidade projeto junta vários projetos do mesmo relatório: re-chaveia
        # as linhas pela chave do projeto (família em vários meses)
        keyed = [{**r, "project_id": project_key(r)} for r in group]
        names = {project_key(r): project_label(r) for r in group}
        config, reviewer, config_notes = _config_for(group, infos, overrides, global_config, family_rules, memories, resolved.config)
        draft = builder.build_custom_draft(keyed, names, resolved.label, resolved.package_unit, config, today)
        partial_keys = _partial_keys(resolved, group, keyed)
        for package in draft["packages"]:
            if package["key"] in partial_keys:
                package["pacote_scope"] = PARTIAL_SCOPE
        clients = sorted({infos[str(r["project_id"])]["client"] for r in group if str(r.get("project_id")) in infos})
        part = labels[key]
        reports.append(
            CustomReport(
                key=str(key),
                title=_title(resolved, part, group, infos)[:255],
                client=(clients[0] if len(clients) == 1 else "Vários clientes" if clients else "")[:255],
                hours=round(sum(float(r.get("horas") or 0) for r in group if float(r.get("horas") or 0) > 0), 2),
                draft=draft,
                partial=bool(partial_keys),
                project_names=sorted({names[k] for k in names}),
                reviewer_login=reviewer[0] if reviewer else None,
                reviewer_name=reviewer[1] if reviewer else None,
                notes=config_notes,
            )
        )
    reports.sort(key=lambda r: r.title.casefold())
    return reports


def _partial_keys(resolved: Resolved, group: list[dict], keyed: list[dict]) -> set[str]:
    """Chaves (dos pacotes do rascunho) cujo conteúdo NÃO é o projeto/pacote
    inteiro: alguma linha veio de um recorte com filtro de colaborador ou de
    pacote."""
    partial: set[str] = set()
    for original, row in zip(group, keyed, strict=False):
        pacote = pacote_name(original)
        key = row["project_id"] if resolved.package_unit == "projeto" else pacote
        if key in partial:
            continue
        if not covers_whole(resolved.blocks, str(original.get("project_id")), pacote, resolved.package_unit):
            partial.add(key)
    return partial


def _family_overrides() -> dict[str, str]:
    return store.get_family_overrides()


def summarize(resolved: Resolved, reports: list[CustomReport]) -> list[dict]:
    """O que a prévia mostra por relatório."""
    return [
        {
            "key": r.key,
            "title": r.title,
            "client": r.client,
            "hours": r.hours,
            "packages": len(r.draft["packages"]),
            "partial": r.partial,
            "issues": len(r.draft.get("issues", [])),
            "projects": r.project_names,
        }
        for r in reports
    ]


def describe_blocks(scope: dict, employees: dict[str, str]) -> list[dict]:
    """Os recortes do pedido em NOMES (o que a tela mostra): clientes, projetos
    escolhidos, pacotes e colaboradores. Só o que foi escolhido de fato — um
    bloco só com o cliente não lista os projetos dele."""
    raw = scope.get("blocks") or []
    ids = sorted({str(p) for block in raw for p in (block.get("project_ids") or [])})
    details = projectile_db.fetch_project_details(ids) if ids else {}
    return [
        {
            "clients": [str(c) for c in block.get("clients") or []],
            "projects": [families.clean((details.get(str(p)) or {}).get("name")) or str(p) for p in block.get("project_ids") or []],
            "packages": [str(p) for p in block.get("packages") or []],
            "employees": [employees.get(str(e), str(e)) for e in block.get("employee_ids") or []],
        }
        for block in raw
    ]


def scope_summary(resolved: Resolved) -> str:
    """Uma frase do recorte pra lista ("2 recortes · Mercedes · Lucca")."""
    parts: list[str] = []
    for block in resolved.blocks:
        bits = list(block.clients)
        if block.project_ids and not block.clients:
            bits.append(f"{len(block.project_ids)} projeto(s)")
        if block.packages:
            bits.append(f"{len(block.packages)} pacote(s)")
        bits += [resolved.employees.get(e, e) for e in block.employee_ids]
        parts.append(" · ".join(bits))
    return " + ".join(p for p in parts if p)
