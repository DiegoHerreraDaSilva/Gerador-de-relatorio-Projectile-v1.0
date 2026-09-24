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
from contextlib import contextmanager
from typing import Iterator

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB

from .core.config import get_settings
from .db_credentials import DbCredentialsError, get_projectile_db_password
from .parser import SINGLE_PACKAGE_KEY, RowIssue, WorkPackage, _PackageAccumulator


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
# Vem de core.config.Settings (default idêntico ao valor fixo anterior) —
# nunca muda na prática, só existe como variável pra não ficar hardcoded.
_SYS_CLIENT_ID = get_settings().projectile_sys_client_id


def _connection_kwargs() -> dict:
    host = os.environ.get("PROJECTILE_DB_HOST")
    user = os.environ.get("PROJECTILE_DB_USER")
    database = os.environ.get("PROJECTILE_DB_NAME", "projectile")
    port = int(os.environ.get("PROJECTILE_DB_PORT", "3306"))
    if not host or not user:
        raise ProjectileDbError(
            "Configuração do banco do Projectile ausente. Defina PROJECTILE_DB_HOST e "
            "PROJECTILE_DB_USER no .env (veja .env.example)."
        )
    try:
        password = get_projectile_db_password(user)
    except DbCredentialsError as e:
        # Sem isso, a ausência de senha no Credential Manager vazava como uma
        # exceção crua (DbCredentialsError não é ProjectileDbError) — nenhuma rota
        # em main.py a captura, então virava um 500 sem a mensagem genérica de
        # infra (ver `_log_and_generic_error`), quebrando o contrato de erro do app.
        raise ProjectileDbError(str(e)) from e
    return dict(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=8,
        # autocommit: esse módulo só faz SELECT, nunca escreve — mas cada
        # conexão do pool é reaproveitada entre várias requisições, e o MySQL
        # do Projectile usa REPEATABLE READ por padrão. Sem autocommit, a
        # primeira query da conexão abriria uma transação implícita cujo
        # "retrato" dos dados ficaria congelado até o próximo commit, e toda
        # query seguinte na mesma conexão devolveria dado desatualizado
        # silenciosamente. Com autocommit, cada SELECT enxerga o dado atual.
        autocommit=True,
    )


# Pool de verdade (DBUtils.PooledDB) em vez de uma conexão única + RLock
# global: cada chamada pega sua PRÓPRIA conexão emprestada, então duas
# requisições concorrentes deixam de serializar em fila uma atrás da outra.
# Isso também elimina a causa raiz de um bug real de produção
# (`ValueError: read of closed file` com 2+ usuários simultâneos) — a causa
# não era "falta de lock", era duas threads compartilhando a MESMA conexão
# (o polling de e-mail em background, via `asyncio.to_thread`, roda numa
# thread OS de verdade, concorrente com requisições HTTP normais). Com pool,
# threads concorrentes nunca mais tocam a mesma conexão ao mesmo tempo.
#
# `maxconnections` deliberadamente pequeno (padrão 5, `projectile_db_pool_size`
# em core/config.py): esse MySQL é legado, on-premise, sem staging pra medir
# `max_connections` real do servidor — fica bem abaixo de qualquer default
# razoável (tipicamente 151+) em vez de arriscar sobrecarregar produção.
# `blocking=True`: sob pico, uma chamada extra ESPERA uma conexão liberar em
# vez de levantar erro imediatamente — mesma experiência de "fila", só que
# agora só quem está de fato esperando bloqueia, não todo mundo.
# `ping=1`: verifica (e reconecta se preciso) a conexão emprestada do cache
# a cada `.connection()` — substitui o `ping(reconnect=True)` manual de antes.
_pool: PooledDB | None = None
_pool_init_lock = threading.Lock()


def _get_pool() -> PooledDB:
    global _pool
    if _pool is None:
        with _pool_init_lock:
            if _pool is None:
                pool_size = get_settings().projectile_db_pool_size
                try:
                    _pool = PooledDB(
                        creator=pymysql,
                        mincached=1,
                        maxcached=pool_size,
                        maxconnections=pool_size,
                        blocking=True,
                        ping=1,
                        **_connection_kwargs(),
                    )
                except pymysql.MySQLError as e:
                    raise ProjectileDbError(f"Falha ao conectar no banco do Projectile: {e}") from e
    return _pool


def _get_connection() -> pymysql.connections.Connection:
    """Empresta uma conexão do pool. Quem chama é dono dela e precisa
    devolvê-la com `.close()` (que aqui devolve ao pool, não fecha de
    verdade) — usar via `_borrowed_connection()` faz isso automaticamente."""
    try:
        return _get_pool().connection()
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao conectar no banco do Projectile: {e}") from e


@contextmanager
def _borrowed_connection(
    conn: pymysql.connections.Connection | None = None,
) -> Iterator[pymysql.connections.Connection]:
    """Se `conn` já foi passada (chamador quer reaproveitar uma conexão em
    várias queries do mesmo request, ex: `management.compute_monthly_kpis`),
    só a repassa e NÃO devolve ao pool — quem abriu é dono e decide quando
    devolver. Caso contrário, empresta uma conexão nova do pool e garante a
    devolução ao final, sucesso ou erro."""
    if conn is not None:
        yield conn
        return
    borrowed = _get_connection()
    try:
        yield borrowed
    finally:
        borrowed.close()


def open_connection() -> pymysql.connections.Connection:
    """Empresta uma conexão do pool pra reaproveitar em várias queries de um
    mesmo request (ex: `auth.verify_projectile_login`,
    `management.compute_monthly_kpis`). Diferente das funções `fetch_*`
    deste módulo, o chamador AQUI é responsável por devolvê-la ao pool com
    `.close()` (nunca destrói a conexão de verdade, só a libera pro próximo
    uso) — sempre dentro de um `try/finally`."""
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
    try:
        with _borrowed_connection() as conn, conn.cursor() as cur:
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


def fetch_my_hours(
    start_date: str, end_date: str,
    employee_id: str | None = None, employee_name: str | None = None,
) -> list[dict]:
    """Como `fetch_employee_hours` (mesmo filtro por funcionário, mesmo
    fallback pra nome), mas junta também `temployee` (`cost_center`) e traz
    `project_id`/`external` (igual `fetch_engineering_hours`) — nenhuma das
    duas funções tinha as duas coisas juntas. Usada pelo Dashboard de horas
    pessoal (`GET /my-hours`), que precisa de projeto e faturável/não
    faturável por lançamento, não só o texto do pacote.

    Traz também `inicio`/`fim` (`ttimebit.pStart`/`pEnd`, varchar "HHMM" —
    medido 100% preenchido nos 11.278 lançamentos de 2026, o que habilita
    análise de horário do dia) e `top_project` (`tjob.capTopProject`, 99,96%
    preenchido — o nível acima do projeto, ex: "1471 INT_Administrativo").

    NÃO traz `ttimebit.pAssessableTime` de propósito: medido NULL em 100% dos
    lançamentos de quem só tem trabalho interno (77% no geral), então
    `tjob.pExternal` continua sendo o único sinal confiável de faturável."""
    if not employee_id and not employee_name:
        raise ValueError("informe employee_id ou employee_name")
    try:
        with _borrowed_connection() as conn, conn.cursor() as cur:
            if employee_id:
                match_clause, match_param = "tj.pEmployee = %s", employee_id
            else:
                match_clause, match_param = "tj.capEmployee LIKE %s", f"%{employee_name}%"
            cur.execute(
                f"""
                SELECT tb.pDate AS data, tb.pTime AS horas, tb.capJob AS pacote,
                       tb.pNote AS observacao, tj.pProject AS project_id,
                       te.pCostCenter AS cost_center, tj.pExternal AS external,
                       tb.pStart AS inicio, tb.pEnd AS fim,
                       tj.capTopProject AS top_project
                FROM ttimebit tb
                JOIN tjob tj ON tj.pJob = tb.pJob AND tj.sysClientId = tb.sysClientId
                JOIN temployee te ON te.pEmployee = tj.pEmployee AND te.sysClientId = tb.sysClientId
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


def fetch_employee_contracts(employee_id: str) -> list[dict]:
    """Jornada contratual do funcionário, uma linha por vigência de contrato:
    `{"begin", "end", "weekday_hours": {0..6 -> horas}}` (0=segunda, igual
    `date.weekday()`).

    `temployeecontract.pPlannedTimeMonday..Sunday` é a única fonte REAL de
    "horas esperadas por dia" neste banco — validado: 564 dos 578 contratos
    têm segunda preenchida, e sábado/domingo vêm NULL (tratados como 0). As
    alternativas foram medidas e descartadas:
    `biemployeeplannedpresencedaily` tem 441k linhas mas para em 2024-11-08, e
    `tworkingtime` tem só 1.184 linhas pra 125 funcionários desde 2009 (com
    `pPresence` sujo, misturando tipo de presença com descrição de job).

    Devolve TODAS as vigências (são poucas — 3 num caso real medido) em vez da
    válida numa data só: o dashboard cobre até 12 meses e um contrato pode
    mudar no meio do período, então quem chama resolve dia a dia. Lista vazia
    é resultado legítimo e comum (ex: estagiário sem contrato cadastrado) —
    quem chama precisa ter um fallback, nunca assumir 8h."""
    try:
        with _borrowed_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT pContractBegin, pContractEnd,
                       pPlannedTimeMonday, pPlannedTimeTuesday, pPlannedTimeWednesday,
                       pPlannedTimeThursday, pPlannedTimeFriday, pPlannedTimeSaturday,
                       pPlannedTimeSunday
                FROM temployeecontract
                WHERE sysClientId = %s AND pEmployee = %s
                ORDER BY pContractBegin
                """,
                (_SYS_CLIENT_ID, employee_id),
            )
            columns = (
                "pPlannedTimeMonday", "pPlannedTimeTuesday", "pPlannedTimeWednesday",
                "pPlannedTimeThursday", "pPlannedTimeFriday", "pPlannedTimeSaturday",
                "pPlannedTimeSunday",
            )
            return [
                {
                    "begin": row["pContractBegin"],
                    "end": row["pContractEnd"],
                    "weekday_hours": {i: float(row[c] or 0) for i, c in enumerate(columns)},
                }
                for row in cur.fetchall()
            ]
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar contrato do Projectile: {e}") from e


def fetch_daily_hours_totals(
    start_date: str, end_date: str,
    employee_id: str | None = None, employee_name: str | None = None,
) -> list[dict]:
    """Total de horas por DIA do funcionário (`[{"data", "horas"}]`, ordenado)
    — mesmos joins e filtros de `fetch_my_hours`, só agregado no SQL.

    Existe separado porque o Dashboard de horas precisa de uma janela MUITO
    maior que o período exibido: a tendência mensal cobre 13 meses e o
    baseline empírico de jornada precisa de ~120 dias, mas trazer 12 meses de
    lançamentos crus só pra somar por dia seria trafegar milhares de linhas
    duas vezes. Uma chamada com janela longa alimenta a série mensal, o
    baseline e os percentis diários de uma vez.

    Não devolve dia sem apontamento: dia ausente não é "dia de 0h", é dia sem
    informação (pode ser férias/atestado, e medido que este banco não tem
    fonte confiável de ausência). Quem precisa da lista de dias úteis pega em
    `generator.business_days_between`."""
    if not employee_id and not employee_name:
        raise ValueError("informe employee_id ou employee_name")
    try:
        with _borrowed_connection() as conn, conn.cursor() as cur:
            if employee_id:
                match_clause, match_param = "tj.pEmployee = %s", employee_id
            else:
                match_clause, match_param = "tj.capEmployee LIKE %s", f"%{employee_name}%"
            cur.execute(
                f"""
                SELECT tb.pDate AS data, SUM(tb.pTime) AS horas
                FROM ttimebit tb
                JOIN tjob tj ON tj.pJob = tb.pJob AND tj.sysClientId = tb.sysClientId
                WHERE {match_clause}
                  AND tb.sysClientId = %s
                  AND tb.pDate BETWEEN %s AND %s
                  AND (tb.pDeleteFlag IS NULL OR tb.pDeleteFlag = '')
                GROUP BY tb.pDate
                ORDER BY tb.pDate
                """,
                (match_param, _SYS_CLIENT_ID, start_date, end_date),
            )
            return cur.fetchall()
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar totais diários do Projectile: {e}") from e


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

    Devolve TODAS as linhas de CAD+CAE (com `cost_center`, `project_id`,
    `external` — `tjob.pExternal`, usado por `management.py` pra decidir
    faturável/não faturável, ver seu docstring pra validação desse campo — e
    `person`, `tjob.capEmployee`, pra alimentar o filtro por pessoa do painel)
    pra `management.py` cachear e filtrar por Centro de Custo/Cliente/
    Projeto/Pessoa em Python — evita repetir essa query a cada troca de
    filtro. NUNCA faz join
    direto com `tproject` aqui: já medido que isso
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
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT tb.pDate AS data, tb.pTime AS horas, tb.capJob AS pacote,
                       tj.pProject AS project_id, te.pCostCenter AS cost_center,
                       tj.pExternal AS external, tj.capEmployee AS person
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


def fetch_engineering_employees(start_date: str, end_date: str) -> list[dict]:
    """Funcionários de engenharia (CAD+CAE) com ao menos um apontamento no
    período — o universo que gerente/coordenador pode escolher no Dashboard
    de horas (`/my-hours?employee_id=`). Mesmo join e filtros de
    `fetch_engineering_hours` (sysClientId + índice de data), só que
    `DISTINCT` por funcionário. Nome montado como no login
    (`auth.verify_projectile_login`): `pFirstName pName`, com fallback pro
    `tjob.capEmployee`."""
    try:
        with _borrowed_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT te.pEmployee AS employee_id, te.pFirstName, te.pName,
                       te.pFiliale, te.pCostCenter AS cost_center, tj.capEmployee
                FROM ttimebit tb
                JOIN tjob tj ON tj.pJob = tb.pJob AND tj.sysClientId = tb.sysClientId
                JOIN temployee te ON te.pEmployee = tj.pEmployee AND te.sysClientId = tb.sysClientId
                WHERE (te.pCostCenter LIKE %s OR te.pCostCenter LIKE %s)
                  AND tb.sysClientId = %s
                  AND tb.pDate BETWEEN %s AND %s
                  AND (tb.pDeleteFlag IS NULL OR tb.pDeleteFlag = '')
                """,
                ("%CAD%", "%CAE%", _SYS_CLIENT_ID, start_date, end_date),
            )
            rows = cur.fetchall()
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar funcionários de engenharia do Projectile: {e}") from e

    employees: dict[str, dict] = {}
    for row in rows:
        employee_id = str(row["employee_id"] or "").strip()
        if not employee_id or employee_id in employees:
            continue
        first = html.unescape(html.unescape(str(row.get("pFirstName") or ""))).strip()
        last = html.unescape(html.unescape(str(row.get("pName") or ""))).strip()
        name = f"{first} {last}".strip() or html.unescape(str(row.get("capEmployee") or "")).strip() or employee_id
        employees[employee_id] = {
            "employee_id": employee_id,
            "name": name,
            "filiale": html.unescape(str(row.get("pFiliale") or "")).strip() or None,
            "cost_center": html.unescape(str(row.get("cost_center") or "")).strip() or None,
        }
    return sorted(employees.values(), key=lambda e: e["name"].casefold())


_PROJECT_CODE_RE = re.compile(r"^(\d+)")


def extract_project_code(pacote_raw: str) -> str | None:
    """Prefixo numérico do pacote de trabalho, usado como "código do
    projeto" pra exibição — ver `fetch_project_codes`. O que vem depois do
    número varia (`1564.1.1-001 MBB_CAD_ACCELO - ...` com ponto,
    `1565-001 MBB_CE...` só com hífen), então captura só os dígitos do
    início, sem exigir separador específico."""
    match = _PROJECT_CODE_RE.match(html.unescape(str(pacote_raw or "")).strip())
    return match.group(1) if match else None


def fetch_project_ids_with_hours(
    start_date: str, end_date: str, conn: pymysql.connections.Connection | None = None
) -> list[str]:
    """Projetos (CAD+CAE) que têm ao menos um lançamento de hora no período —
    usado pra popular o seletor de Cliente/Projeto da tela de importação
    "por cliente" (`/management/clients-with-hours`,
    `/management/client-projects`) só com quem tem apontamento no mês em
    vista, sem precisar de uma query nova: reaproveita
    `fetch_engineering_hours` (já otimizada, ver seu docstring) e extrai os
    `project_id` distintos em Python."""
    rows = fetch_engineering_hours(start_date, end_date, conn=conn)
    return sorted({r["project_id"] for r in rows if r.get("project_id")})


def fetch_project_codes(
    start_date: str, end_date: str, conn: pymysql.connections.Connection | None = None
) -> dict[str, str]:
    """project_id -> "código do projeto" no período — o Projectile não tem
    uma coluna de código separada pra `tproject`, mas o pacote de trabalho
    (`ttimebit.capJob`) sempre começa com ele, ex: em
    "1564.1.1-001 MBB_CAD_ACCELO - PP2030 08.2026" o código é "1564" (todo
    pacote desse projeto compartilha esse mesmo prefixo). Reaproveita
    `fetch_engineering_hours` (mesma fonte de `fetch_project_ids_with_hours`)
    em vez de uma query nova — só usado pra exibição (prefixo em
    dropdowns/filtros), nunca pra identificar o projeto de verdade (isso
    continua sendo `project_id`)."""
    rows = fetch_engineering_hours(start_date, end_date, conn=conn)
    codes: dict[str, str] = {}
    for row in rows:
        project_id = row.get("project_id")
        if not project_id or project_id in codes:
            continue
        code = extract_project_code(row.get("pacote"))
        if code:
            codes[project_id] = code
    return codes


def fetch_project_hours(
    project_ids: list[str], start_date: str, end_date: str, conn: pymysql.connections.Connection | None = None
) -> list[dict]:
    """Horas de TODOS os funcionários (CAD+CAE) nos projetos informados, no
    período — usado pelo gerente pra gerar relatório "por cliente"/"por
    projeto" na tela de importação (`/parse-db-client`), diferente de
    `fetch_employee_hours` (só o usuário logado) e `fetch_engineering_hours`
    (todo mundo, sem filtro de projeto). Filtra direto por
    `tj.pProject IN (...)` — mesma técnica usada pra evitar o join direto
    com `tproject` citado em `fetch_engineering_hours`.

    Devolve `observacao`/`horas`/`pacote`/`project_id`: os três primeiros no
    mesmo formato que `group_hours` já consome (pacote de trabalho bruto, o
    nome do projeto já vem embutido nesse valor — por isso
    `group_hours(rows, split_by_package=True)` separa por projeto e por
    pacote sem precisar de agrupamento novo); `project_id` é usado por
    `group_hours_by_project` no modo "um relatório por projeto"."""
    if not project_ids:
        return []
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(project_ids))
            cur.execute(
                f"""
                SELECT tb.pDate AS data, tb.pNote AS observacao, tb.pTime AS horas,
                       tb.capJob AS pacote, tj.pProject AS project_id
                FROM ttimebit tb
                JOIN tjob tj ON tj.pJob = tb.pJob AND tj.sysClientId = tb.sysClientId
                JOIN temployee te ON te.pEmployee = tj.pEmployee AND te.sysClientId = tb.sysClientId
                WHERE tj.pProject IN ({placeholders})
                  AND (te.pCostCenter LIKE %s OR te.pCostCenter LIKE %s)
                  AND tb.sysClientId = %s
                  AND tb.pDate BETWEEN %s AND %s
                  AND (tb.pDeleteFlag IS NULL OR tb.pDeleteFlag = '')
                ORDER BY tb.pDate
                """,
                (*project_ids, "%CAD%", "%CAE%", _SYS_CLIENT_ID, start_date, end_date),
            )
            return cur.fetchall()
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar horas dos projetos no Projectile: {e}") from e


def _missing_observacao_issue(row_index: int, hs_float: float, row: dict) -> RowIssue | None:
    """Hora sem Observação preenchida não pode desaparecer da soma em
    silêncio — mesmo critério em `group_hours` e `group_hours_by_project`,
    só reportado quando há hora de fato (>0) pra não gerar aviso por linha
    vazia/zerada sem apontamento nenhum."""
    if hs_float <= 0:
        return None
    row_date = row.get("data")
    date_label = row_date.strftime("%d/%m/%Y") if hasattr(row_date, "strftime") else str(row_date or "data desconhecida")
    pacote_label = html.unescape(str(row.get("pacote") or "")).strip() or "Sem pacote"
    return RowIssue(
        row=row_index, reason="descricao_vazia",
        message=(
            f"Lançamento {row_index}: descrição vazia (Observação não preenchida) — {hs_float} h "
            f"descartada(s) em {date_label}, pacote \"{pacote_label}\"."
        ),
        raw_hours=hs_float,
    )


def group_hours_by_project(rows: list[dict], project_names: dict[str, str]) -> tuple[list["WorkPackage"], list[RowIssue]]:
    """Agrupa as linhas de `fetch_project_hours` em um `WorkPackage` por
    PROJETO (não por pacote de trabalho) — usado no modo "1 relatório por
    projeto" da importação "por cliente": aqui quem vira `Group` (a divisão
    visível dentro do relatório) é o pacote de trabalho (`capJob`), e cada
    atividade é a Observação inteira (sem dividir prefixo/descrição — não
    sobra um 3º nível pra isso na estrutura WorkPackage->Group->Activity).
    Reaproveita `_PackageAccumulator` (mesma classe de `group_hours`), só
    troca o que vira chave de pacote/grupo."""
    accumulator = _PackageAccumulator()
    issues: list[RowIssue] = []

    for i, row in enumerate(rows, start=1):
        obs_value = html.unescape(str(row.get("observacao") or "")).strip()
        hs_float = round(float(row.get("horas") or 0), 3)
        if not obs_value:
            issue = _missing_observacao_issue(i, hs_float, row)
            if issue:
                issues.append(issue)
            continue
        if hs_float <= 0:
            continue

        project_id = str(row.get("project_id") or "").strip()
        if not project_id:
            issues.append(RowIssue(
                row=i, reason="projeto_desconhecido",
                message=f'Lançamento {i}: sem projeto associado ("{obs_value}").',
                raw_hours=hs_float,
                raw_description=obs_value,
            ))
            continue

        package_name = project_names.get(project_id) or project_id
        pacote = html.unescape(str(row.get("pacote") or "")).strip() or "Geral"

        accumulator.add_activity(
            package_key=project_id,
            package_name=package_name,
            group_name=pacote,
            description=obs_value,
            hours=hs_float,
        )

    return accumulator.build(), issues


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
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
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
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
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
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
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


def fetch_project_details(
    project_ids: list[str], conn: pymysql.connections.Connection | None = None
) -> dict[str, dict]:
    """Nome e cliente por projeto (`pProject` -> `{"name", "client"}`) — usado
    pela tabela "Relatórios enviados" do painel, que precisa mostrar cliente
    e projeto juntos por linha (diferente de `fetch_project_names_for_ids`/
    `fetch_clients_for_projects`, que só devolvem listas soltas pra popular
    filtro). Mesma técnica de lookup por `pProject IN (...)` (PK), sem join
    com as tabelas de horas. Aceita `conn` já aberta, ver
    `fetch_engineering_hours`."""
    if not project_ids:
        return {}
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(project_ids))
            cur.execute(
                f"SELECT pProject, pDescription, capCustomer FROM tproject "
                f"WHERE pProject IN ({placeholders})",
                project_ids,
            )
            return {
                row["pProject"]: {
                    "name": html.unescape(row["pDescription"] or "").strip(),
                    "client": html.unescape(row["capCustomer"] or "").strip(),
                }
                for row in cur.fetchall()
            }
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar detalhes de projeto do Projectile: {e}") from e


def fetch_project_ids_for_names(
    names: list[str], conn: pymysql.connections.Connection | None = None
) -> list[str]:
    """Resolve nomes de projeto (`tproject.pDescription`) pros IDs
    correspondentes — usado quando o filtro de Projeto está ativo. Aceita
    `conn` já aberta, ver `fetch_engineering_hours`."""
    if not names:
        return []
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(names))
            cur.execute(f"SELECT pProject FROM tproject WHERE pDescription IN ({placeholders})", names)
            return [row["pProject"] for row in cur.fetchall()]
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar projetos do Projectile: {e}") from e


def fetch_all_projects(conn: pymysql.connections.Connection | None = None) -> dict[str, str]:
    """Todos os projetos (`pProject` -> `pDescription`) do Projectile, sem
    recorte por período/cliente — usado por `email_ingest.py` como universo de
    candidatos pro fuzzy match do nome de projeto extraído do relatório
    (texto livre digitado pelo Alberto, não necessariamente idêntico ao nome
    oficial). `tproject` é pequena (poucos milhares de linhas, sem join), não
    tem o mesmo risco de scan lento de `fetch_engineering_hours`. Aceita
    `conn` já aberta, ver `fetch_engineering_hours`."""
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pProject, pDescription FROM tproject "
                "WHERE pDescription IS NOT NULL AND pDescription <> ''"
            )
            return {
                row["pProject"]: html.unescape(row["pDescription"]).strip()
                for row in cur.fetchall()
            }
    except pymysql.MySQLError as e:
        raise ProjectileDbError(f"Falha ao consultar projetos do Projectile: {e}") from e


def fetch_all_projects_with_details(conn: pymysql.connections.Connection | None = None) -> list[dict]:
    """Todos os projetos com nome e cliente juntos (`[{"id","name","client"}]`),
    sem recorte por período — usado pelo seletor de projeto da tela de
    Diagnóstico (cadastro/edição manual de amostra), que precisa poder
    escolher QUALQUER projeto, não só os que já têm horas num período dado
    (diferente de `fetch_project_details`, que exige uma lista de ids).
    Mesmo universo de `fetch_all_projects`, só que devolve cliente junto.
    Aceita `conn` já aberta, ver `fetch_engineering_hours`."""
    try:
        with _borrowed_connection(conn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pProject, pDescription, capCustomer FROM tproject "
                "WHERE pDescription IS NOT NULL AND pDescription <> '' "
                "ORDER BY pDescription"
            )
            return [
                {
                    "id": row["pProject"],
                    "name": html.unescape(row["pDescription"]).strip(),
                    "client": html.unescape(row["capCustomer"] or "").strip(),
                }
                for row in cur.fetchall()
            ]
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
    accumulator = _PackageAccumulator()
    issues: list[RowIssue] = []

    for i, row in enumerate(rows, start=1):
        # o Projectile guarda alguns campos de texto com entidades HTML (ex:
        # "relat&#243;rio" em vez de "relatório") — provavelmente de como a
        # interface deles salva o texto. Decodifica antes de usar.
        obs_value = html.unescape(str(row.get("observacao") or "")).strip()
        hs_float = round(float(row.get("horas") or 0), 3)
        if not obs_value:
            # descartar em silêncio esconderia apontamento de verdade do
            # usuário sem nenhum rastro — mesmo critério do export .xlsx
            # (`parser.py` `_classify_incomplete_row`).
            issue = _missing_observacao_issue(i, hs_float, row)
            if issue:
                issues.append(issue)
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
                raw_hours=hs_float if hs_float > 0 else None,
                raw_description=description or prefix or None,
            ))
            continue

        if hs_float <= 0:
            continue

        package_name = html.unescape(str(row.get("pacote") or "")).strip() or "Geral"
        package_key = package_name if split_by_package else SINGLE_PACKAGE_KEY

        accumulator.add_activity(
            package_key=package_key,
            package_name=package_name,
            group_name=prefix,
            description=description,
            hours=hs_float,
        )

    if not split_by_package and rows:
        name = html.unescape(str(rows[0].get("pacote") or "")).strip()
        accumulator.rename_package(SINGLE_PACKAGE_KEY, name)

    return accumulator.build(), issues
