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
import threading

import pymysql
import pymysql.cursors

from .db_credentials import get_projectile_db_password
from .parser import Activity, Group, RowIssue, WorkPackage


class ProjectileDbError(RuntimeError):
    """Falha ao conectar/consultar o MySQL do Projectile — configuração
    ausente ou erro de rede/credencial, nunca erro do usuário."""


# Esse Projectile é uma instalação on-premise de cliente único: TODA tabela
# relevante (ttimebit, tjob, temployee, tproject, auser) tem `sysClientId`
# como primeira coluna de todo índice composto, mas nenhuma query aqui
# filtrava por ele — sem essa igualdade o MySQL nunca consegue "entrar" nesses
# índices e cai pra table scan completo, mesmo quando o índice certo existe.
# Confirmado via `SELECT DISTINCT sysClientId FROM ttimebit/tjob` (só '0') e
# medido: adicionar esse filtro fez a query de fetch_engineering_hours cair
# de 37.31s pra 0.45s pro mesmo resultado (vira ref/eq_ref em vez de ALL).
_SYS_CLIENT_ID = "0"


def _open_new_connection() -> pymysql.connections.Connection:
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
            # autocommit: esse módulo só faz SELECT, nunca escreve — mas a conexão
            # agora é persistente entre requisições (ver _get_connection), e o
            # MySQL do Projectile usa REPEATABLE READ por padrão. Sem autocommit,
            # a primeira query da conexão abriria uma transação implícita cujo
            # "retrato" dos dados ficaria congelado pra sempre (nunca commitado),
            # e toda query seguinte na mesma conexão devolveria dado desatualizado
            # silenciosamente. Com autocommit, cada SELECT enxerga o dado atual.
            autocommit=True,
        )
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao conectar no banco do Projectile: {e}") from e


# Conexão única, persistente entre requisições, em vez de abrir uma nova a
# cada chamada — abrir conexão é o custo real nesse MySQL legado (medido: até
# ~20s quando o servidor está sob carga, contra 0.02-0.05s num dia normal).
# Como as rotas que tocam esse banco são síncronas (sem thread pool), o app
# só processa uma operação de banco por vez, então uma única conexão
# reaproveitada é suficiente — não precisa de um pool com várias. Ninguém
# deve chamar `.close()` na conexão devolvida por `_get_connection()`: ela é
# gerenciada por este módulo e reconectada sozinha (`ping(reconnect=True)`)
# se a conexão cair (timeout do servidor, restart, etc.).
_pooled_conn: pymysql.connections.Connection | None = None
_pool_lock = threading.Lock()


def _get_connection() -> pymysql.connections.Connection:
    global _pooled_conn
    with _pool_lock:
        if _pooled_conn is not None:
            try:
                _pooled_conn.ping(reconnect=True)
                return _pooled_conn
            except pymysql.MySQLError:
                try:
                    _pooled_conn.close()
                except Exception:
                    pass
                _pooled_conn = None
        _pooled_conn = _open_new_connection()
        return _pooled_conn


def open_connection() -> pymysql.connections.Connection:
    """Nome mantido por compatibilidade com quem já importa (ex:
    `management.py`) — devolve a mesma conexão persistente de
    `_get_connection`. Não precisa (nem deve) ser fechada pelo chamador."""
    return _get_connection()


def fetch_employee_hours(
    start_date: str, end_date: str,
    employee_id: str | None = None, employee_name: str | None = None,
) -> list[dict]:
    """Busca as horas do funcionário no período. Prefere `employee_id`
    (`tjob.pEmployee`, FK de verdade — resolvida uma vez no login via
    `temployee.pLogin`, ver `auth.py:verify_projectile_login`): usa
    `IdxJobEmployee` com o filtro de `sysClientId` abaixo, então vira um
    lookup indexado em vez de scan. Se não tiver `employee_id` (ex: login sem
    registro correspondente em `temployee`), cai pro fallback por nome
    parcial (`tjob.capEmployee LIKE`), mais lento mas sempre funciona."""
    if not employee_id and not employee_name:
        raise ValueError("informe employee_id ou employee_name")
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            if employee_id:
                match_clause, match_param = "tj.pEmployee = %s", employee_id
            else:
                match_clause, match_param = "tj.capEmployee LIKE %s", f"%{employee_name}%"
            cur.execute(
                f"""
                SELECT tb.pDate AS data, tb.pNote AS observacao, tb.pTime AS horas,
                       tb.capJob AS pacote, tj.capEmployee AS funcionario
                FROM ttimebit tb
                JOIN tjob tj ON tj.pJob = tb.pJob AND tj.sysClientId = tb.sysClientId
                WHERE {match_clause}
                  AND tb.sysClientId = %s
                  AND tb.pDate BETWEEN %s AND %s
                  AND (tb.pDeleteFlag IS NULL OR tb.pDeleteFlag = '')
                ORDER BY tb.pDate, tb.pStart
                """,
                (match_param, _SYS_CLIENT_ID, start_date, end_date),
            )
            return cur.fetchall()
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar horas do Projectile: {e}") from e


def fetch_engineering_hours(
    start_date: str, end_date: str, conn: pymysql.connections.Connection | None = None
) -> list[dict]:
    """Busca as horas de TODOS os funcionários dos centros de custo de
    engenharia (CAD+CAE, sempre os dois — o recorte mais amplo permitido no
    painel) no período — usado no painel de gerência, diferente de
    `fetch_employee_hours` (que busca só o usuário logado). Aqui o join com
    `temployee` é por ID (`tj.pEmployee = te.pEmployee`), uma FK de verdade —
    mais confiável que o casamento por texto (`capEmployee LIKE`) usado
    acima, que só existe porque não havia necessidade de filtrar por centro
    de custo até agora.

    Devolve TODAS as linhas de CAD+CAE (com `cost_center` e `project_id` de
    cada uma) pra `management.py` cachear e filtrar por Centro de
    Custo/Cliente/Projeto em Python — evita repetir essa query a cada troca
    de filtro. NUNCA faz join direto com `tproject` aqui: já medido que isso
    faz o otimizador escanear tudo e leva minutos — resolver cliente/projeto
    por `pProject IN (...)` à parte (ver
    `fetch_project_ids_for_clients`/`fetch_project_ids_for_names`) evita esse
    plano ruim.

    Filtra `sysClientId` em todas as tabelas (ver `_SYS_CLIENT_ID` no topo do
    arquivo) — sem isso o MySQL não conseguia usar nenhum índice e cada
    chamada levava ~37s (medido); com o filtro vira `ref`/`eq_ref` em
    `IdxTimeBitDate`/`PRIMARY` e cai pra ~0.45s, mesmo resultado.

    Aceita uma `conn` já aberta pra reaproveitar (opcional — desde que a
    conexão passou a ser única e persistente no processo, ver
    `_get_connection`, isso é só pra quem já tem uma em mãos e quer deixar a
    reutilização explícita, ex: `management.py:compute_monthly_kpis`).
    """
    conn = conn or _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tb.pDate AS data, tb.pTime AS horas, tb.capJob AS pacote,
                       tj.pProject AS project_id, te.pCostCenter AS cost_center
                FROM ttimebit tb
                JOIN tjob tj ON tj.pJob = tb.pJob AND tj.sysClientId = tb.sysClientId
                JOIN temployee te ON te.pEmployee = tj.pEmployee AND te.sysClientId = tb.sysClientId
                WHERE (te.pCostCenter LIKE %s OR te.pCostCenter LIKE %s)
                  AND tb.sysClientId = %s
                  AND tb.pDate BETWEEN %s AND %s
                  AND (tb.pDeleteFlag IS NULL OR tb.pDeleteFlag = '')
                ORDER BY tb.pDate
                """,
                ("%CAD%", "%CAE%", _SYS_CLIENT_ID, start_date, end_date),
            )
            return cur.fetchall()
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar horas de engenharia do Projectile: {e}") from e


def fetch_clients_for_projects(
    project_ids: list[str], conn: pymysql.connections.Connection | None = None
) -> list[str]:
    """Lista de clientes só dos projetos informados — usada pra popular o
    filtro de Cliente com só quem tem horas no período em vista (últimos N
    meses), não o histórico inteiro do Projectile. Consulta direta em
    `tproject` filtrando por `pProject IN (...)` (PK, rápida) — sem join
    com as tabelas de horas (ver aviso em `fetch_engineering_hours` sobre
    por que esse join é evitado). Aceita `conn` já aberta, ver
    `fetch_engineering_hours`."""
    if not project_ids:
        return []
    conn = conn or _get_connection()
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(project_ids))
            cur.execute(
                f"SELECT DISTINCT capCustomer FROM tproject "
                f"WHERE pProject IN ({placeholders}) AND capCustomer IS NOT NULL AND capCustomer <> '' "
                f"ORDER BY capCustomer",
                project_ids,
            )
            return [html.unescape(row["capCustomer"]).strip() for row in cur.fetchall()]
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar clientes do Projectile: {e}") from e


def fetch_project_ids_for_clients(
    clients: list[str], conn: pymysql.connections.Connection | None = None
) -> list[str]:
    """Resolve nomes de cliente (`tproject.capCustomer`) pros IDs de projeto
    (`tproject.pProject`) correspondentes — usado só quando o filtro de
    Cliente está ativo, pra filtrar a query principal por `tj.pProject IN
    (...)` em vez de fazer join direto (ver `fetch_engineering_hours`).
    Aceita `conn` já aberta, ver `fetch_engineering_hours`."""
    if not clients:
        return []
    conn = conn or _get_connection()
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(clients))
            cur.execute(f"SELECT pProject FROM tproject WHERE capCustomer IN ({placeholders})", clients)
            return [row["pProject"] for row in cur.fetchall()]
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar projetos do Projectile: {e}") from e


def fetch_project_names_for_ids(
    project_ids: list[str], conn: pymysql.connections.Connection | None = None
) -> list[str]:
    """Nomes de projeto (`tproject.pDescription`) só dos IDs informados — usado
    pra popular o filtro de Projeto com só quem tem horas no período em vista.
    Projeto aqui é `tproject` de verdade, não `capJob` (pacote de trabalho):
    um projeto agrupa vários pacotes de trabalho, então usar `capJob` como
    "Projeto" misturava os dois níveis. Mesma técnica de lookup rápido por
    `pProject IN (...)` (PK) usada pra Cliente, sem join com as tabelas de
    horas. Aceita `conn` já aberta, ver `fetch_engineering_hours`."""
    if not project_ids:
        return []
    conn = conn or _get_connection()
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(project_ids))
            cur.execute(
                f"SELECT DISTINCT pDescription FROM tproject "
                f"WHERE pProject IN ({placeholders}) AND pDescription IS NOT NULL AND pDescription <> '' "
                f"ORDER BY pDescription",
                project_ids,
            )
            return [html.unescape(row["pDescription"]).strip() for row in cur.fetchall()]
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar nomes de projeto do Projectile: {e}") from e


def fetch_project_ids_for_names(
    names: list[str], conn: pymysql.connections.Connection | None = None
) -> list[str]:
    """Resolve nomes de projeto (`tproject.pDescription`) pros IDs
    correspondentes — usado quando o filtro de Projeto está ativo. Aceita
    `conn` já aberta, ver `fetch_engineering_hours`."""
    if not names:
        return []
    conn = conn or _get_connection()
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(names))
            cur.execute(f"SELECT pProject FROM tproject WHERE pDescription IN ({placeholders})", names)
            return [row["pProject"] for row in cur.fetchall()]
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar projetos do Projectile: {e}") from e


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
