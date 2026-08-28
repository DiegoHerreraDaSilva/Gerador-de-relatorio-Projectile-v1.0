"""Busca horas apontadas direto no banco MySQL do Projectile — alternativa ao
export manual em .xlsx (ver backend/app/parser.py). Mesma regra de agrupamento
(Observação dividida em "Prefixo - Descrição", horas somadas por prefixo), mas
a fonte é uma query em vez de uma planilha.

Mapeamento de tabelas confirmado manualmente via MySQL Workbench:
- `ttimebit`: um lançamento de horas por linha (pDate, pStart/pEnd, pTime = Hs,
  pNote = Observação, capJob = nome do pacote de trabalho/projeto).
- `tjob`: um "job" por linha (pJob é a chave, igual ao `ttimebit.pJob`),
  `capEmployee`/`pEmployee` identificam o funcionário dono do job — não existe
  coluna de funcionário direto em `ttimebit`.
"""
from __future__ import annotations

import html
import os
import re

import pymysql
import pymysql.cursors

from .db_credentials import get_projectile_db_password
from .parser import Activity, Group, RowIssue, WorkPackage


class ProjectileDbError(RuntimeError):
    """Falha ao conectar/consultar o MySQL do Projectile — configuração
    ausente ou erro de rede/credencial, nunca erro do usuário."""


def _get_connection() -> pymysql.connections.Connection:
    host = os.environ.get("PROJECTILE_DB_HOST")
    user = os.environ.get("PROJECTILE_DB_USER")
    database = os.environ.get("PROJECTILE_DB_NAME", "projectile")
    port = int(os.environ.get("PROJECTILE_DB_PORT", "3306"))
    if not host or not user:
        raise ProjectileDbError(
            "Configuração do banco do Projectile ausente. Defina PROJECTILE_DB_HOST e "
            "PROJECTILE_DB_USER no .env (veja .env.example)."
        )
    password = get_projectile_db_password(user)
    try:
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=8,
        )
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao conectar no banco do Projectile: {e}") from e


def fetch_employee_hours(employee_name: str, start_date: str, end_date: str) -> list[dict]:
    """Busca por nome (parcial, sem diferenciar maiúscula/minúscula) — o Projectile
    guarda o funcionário no "job" (`tjob.capEmployee`), não no lançamento em si."""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tb.pDate AS data, tb.pNote AS observacao, tb.pTime AS horas,
                       tb.capJob AS pacote, tj.capEmployee AS funcionario
                FROM ttimebit tb
                JOIN tjob tj ON tj.pJob = tb.pJob
                WHERE tj.capEmployee LIKE %s
                  AND tb.pDate BETWEEN %s AND %s
                  AND (tb.pDeleteFlag IS NULL OR tb.pDeleteFlag = '')
                ORDER BY tb.pDate, tb.pStart
                """,
                (f"%{employee_name}%", start_date, end_date),
            )
            return cur.fetchall()
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar horas do Projectile: {e}") from e
    finally:
        conn.close()


def group_hours(rows: list[dict], split_by_package: bool) -> tuple[list[WorkPackage], list[RowIssue]]:
    """Agrupa as linhas retornadas pelo banco em WorkPackage/Group/Activity.

    Mais simples que `parser.parse_projectile_export`: o dado já vem limpo do
    banco (sem linha de rodapé/assinatura, sem Hs de texto livre), então não
    precisa das heurísticas de "linha incompleta" da planilha — só a separação
    de Observação em Prefixo/Descrição é reaproveitada, por ser a mesma regra
    de negócio dos dois formatos.
    """
    SINGLE_PACKAGE_KEY = "__single__"
    packages: dict[str, WorkPackage] = {}
    package_order: list[str] = []
    groups_by_package: dict[str, dict[str, Group]] = {}
    group_order_by_package: dict[str, list[str]] = {}
    issues: list[RowIssue] = []

    for i, row in enumerate(rows, start=1):
        # o Projectile guarda alguns campos de texto com entidades HTML (ex:
        # "relat&#243;rio" em vez de "relatório") — provavelmente de como a
        # interface deles salva o texto. Decodifica antes de usar.
        obs_value = html.unescape(str(row.get("observacao") or "")).strip()
        if not obs_value:
            continue
        separator_match = re.search(r"[-_]", obs_value)
        if separator_match:
            sep_index = separator_match.start()
            prefix = obs_value[:sep_index].strip()
            description = obs_value[sep_index + 1:].strip()
        else:
            # sem "-"/"_" pra separar prefixo/descrição — diferente do export .xlsx
            # (onde isso indica linha malformada), aqui é comum no dado real do
            # Projectile (ex: códigos como "2542A012"). Decisão deliberada: agrupa
            # como "Geral" em vez de descartar/marcar como aviso.
            prefix, description = "Geral", obs_value
        if not prefix or not description:
            issues.append(RowIssue(
                row=i, reason="descricao_vazia",
                message=f'Lançamento {i}: {"prefixo vazio" if not prefix else "descrição vazia"} em "{obs_value}".',
            ))
            continue

        hs_float = round(float(row.get("horas") or 0), 3)
        if hs_float <= 0:
            continue

        package_name = html.unescape(str(row.get("pacote") or "")).strip() or "Geral"
        package_key = package_name if split_by_package else SINGLE_PACKAGE_KEY

        if package_key not in packages:
            packages[package_key] = WorkPackage(key=package_key, project_name=package_name)
            package_order.append(package_key)
            groups_by_package[package_key] = {}
            group_order_by_package[package_key] = []

        groups = groups_by_package[package_key]
        group_order = group_order_by_package[package_key]
        if prefix not in groups:
            groups[prefix] = Group(name=prefix)
            group_order.append(prefix)
        group = groups[prefix]

        existing = next(
            (a for a in group.activities if a.description.casefold() == description.casefold()), None
        )
        if existing:
            existing.hours = round(existing.hours + hs_float, 3)
        else:
            group.activities.append(Activity(description=description, hours=hs_float))

    if not split_by_package and SINGLE_PACKAGE_KEY in packages and rows:
        name = html.unescape(str(rows[0].get("pacote") or "")).strip()
        packages[SINGLE_PACKAGE_KEY].project_name = name
        packages[SINGLE_PACKAGE_KEY].key = name

    result = []
    for key in package_order:
        pkg = packages[key]
        pkg.groups = [groups_by_package[key][name] for name in group_order_by_package[key]]
        result.append(pkg)
    return result, issues
