"""Conceitos de negócio do chat analítico, sem expor o schema do banco pros
modelos: rótulos de dimensões e unidades das métricas. Usado pelo formatter,
pela visualização e como contexto pro Claude."""
from __future__ import annotations

DIMENSIONS = {
    "client": "Cliente",
    "project": "Projeto",
    "employee": "Colaborador",
    "package": "Pacote de trabalho",
    "competence": "Competência",
    "month": "Mês",
    "format": "Formato",
}

UNITS = {
    "hours": "h",
    "count": "",
    "ms": "ms",
    "percent": "%",
}

SOURCES = {
    "reports_db": "Histórico de relatórios gerados",
    "projectile": "Horas apontadas no Projectile (engenharia CAD+CAE)",
}


def fmt_number(value: float | int | None, decimals: int = 1) -> str:
    """Número no formato brasileiro (1.234,5) — usado nos textos sem LLM."""
    if value is None:
        return "—"
    if float(value).is_integer():
        text = f"{int(value):,}"
    else:
        text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_hours(value: float | None) -> str:
    return f"{fmt_number(value)} h"
