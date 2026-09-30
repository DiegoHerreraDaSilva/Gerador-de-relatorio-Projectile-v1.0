"""Memória do mês anterior: o que foi ajustado no último relatório APROVADO
da família e que deve nascer pronto no mês seguinte.

Casada por `source_key` (o texto original do Projectile, sem data, sem acento
e sem caixa — ver `families.normalize_key`), nunca pela posição: o mês
seguinte pode ter grupos novos, a menos ou em outra ordem.

Guarda nomes de grupo, performance por grupo, descrições de atividade,
idioma, gráficos, assinantes, o revisor e o último número (só como SUGESTÃO —
o gerente confirma). Horas nunca: elas vêm sempre do Projectile."""

from __future__ import annotations

_SIGNER_FIELDS = ("signer1_name", "signer1_company", "signer2_name", "signer2_company")


def extract(draft: dict, previous: dict | None = None, reviewer: dict | None = None) -> dict:
    """Memória nova a partir do rascunho aprovado, somada à anterior
    (pacote que não apareceu neste mês continua lembrado). `reviewer`
    (`{login, name}`) = quem revisou este mês; sem revisor, fica o anterior."""
    memory = {
        "signers": {k: draft.get("header", {}).get(k, "") for k in _SIGNER_FIELDS},
        "include_performance": bool(draft.get("include_performance")),
        "packages": dict((previous or {}).get("packages", {})),
    }
    # destinatários são gravados no ENVIO (`service.send_report`), não aqui
    if (previous or {}).get("recipients"):
        memory["recipients"] = previous["recipients"]
    remembered_reviewer = reviewer if reviewer and reviewer.get("login") else (previous or {}).get("reviewer")
    if remembered_reviewer:
        memory["reviewer"] = {"login": remembered_reviewer["login"], "name": remembered_reviewer.get("name") or ""}
    for pkg in draft.get("packages", []):
        key = pkg.get("source_key")
        if not key:
            continue
        memory["packages"][key] = {
            "project_code": pkg.get("project_code", ""),
            "language": pkg.get("language", "pt"),
            "chart_bar": bool(pkg.get("chart_bar")),
            "chart_pie": bool(pkg.get("chart_pie")),
            "groups": {
                g["source_key"]: {"name": g.get("name", ""), "performance": g.get("performance", 1)} for g in pkg.get("groups", []) if g.get("source_key")
            },
            "activities": {a["source_key"]: a.get("description", "") for g in pkg.get("groups", []) for a in g.get("activities", []) if a.get("source_key")},
        }
    return memory


def apply(draft: dict, memory: dict | None) -> bool:
    """Aplica a memória no rascunho recém-montado (in place). Devolve se
    alguma coisa foi aplicada. Assinantes da memória só preenchem o que a
    configuração deixou vazio — regra explícita do gerente vence."""
    if not memory:
        return False
    applied = False
    header = draft.setdefault("header", {})
    for field, value in (memory.get("signers") or {}).items():
        if field in _SIGNER_FIELDS and value and not header.get(field):
            header[field] = value
            applied = True
    for pkg in draft.get("packages", []):
        mem = (memory.get("packages") or {}).get(pkg.get("source_key"))
        if not mem:
            continue
        applied = True
        pkg["suggested_code"] = mem.get("project_code") or ""
        pkg["language"] = mem.get("language") or pkg.get("language", "pt")
        pkg["chart_bar"] = bool(mem.get("chart_bar"))
        pkg["chart_pie"] = bool(mem.get("chart_pie"))
        groups_mem = mem.get("groups") or {}
        activities_mem = mem.get("activities") or {}
        for group in pkg.get("groups", []):
            remembered = groups_mem.get(group.get("source_key"))
            if remembered:
                group["name"] = remembered.get("name") or group["name"]
                performance = remembered.get("performance")
                if isinstance(performance, (int, float)) and performance >= 0:
                    group["performance"] = performance
            for activity in group.get("activities", []):
                description = activities_mem.get(activity.get("source_key"))
                if description:
                    activity["description"] = description
    return applied
