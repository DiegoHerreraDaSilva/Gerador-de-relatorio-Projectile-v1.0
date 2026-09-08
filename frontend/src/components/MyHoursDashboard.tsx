import { useEffect, useMemo } from "react";
import { AlertTriangle, CalendarX2, Check, RefreshCw, X } from "lucide-react";
import { useMyHoursStore, type MyHoursPeriod } from "../store/useMyHoursStore";
import { SortableTh } from "./SortableTh";
import { useSortableRows } from "../hooks/useSortableRows";
import { CalendarHeat } from "./MyHours/CalendarHeat";
import { MonthlyColumns } from "./MyHours/MonthlyColumns";
import { PacoteBars } from "./MyHours/PacoteBars";
import { PeriodSegmented } from "./MyHours/PeriodSegmented";
import { MyHoursFilters } from "./MyHours/MyHoursFilters";
import { MyHoursSkeleton } from "./MyHours/MyHoursSkeleton";
import { fmtNum } from "../utils/fmt";
import {
  aggregateByPacote,
  applyMyHoursFilters,
  billingSplit,
  dailyTotals,
  distinctDaysWorked,
  gapDays as computeGapDays,
  hasActiveMyHoursFilters,
  totalHours,
  weekdayProfile,
  type MyHoursEntry,
} from "../utils/myHours";

const WEEKDAY_SHORT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const MAX_GAP_CHIPS = 6;
/** Abaixo desta amplitude entre o maior e o menor dia da semana, cinco barras
 * não informam nada — vira frase. Medido 0,16 h no usuário de referência. */
const WEEKDAY_AMPLITUDE_THRESHOLD = 0.75;
function brDate(iso: string): string {
  return iso.split("-").reverse().join("/");
}

function weekdayOf(iso: string): string {
  return WEEKDAY_SHORT[(new Date(`${iso}T12:00:00`).getDay() + 6) % 7];
}

export function MyHoursDashboard() {
  const s = useMyHoursStore();

  useEffect(() => {
    s.load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isCurrentMonth = s.period === "current_month";
  const filtersActive = hasActiveMyHoursFilters(s.filters);

  // Competência/Cliente/Projeto/Pacote são filtros GLOBAIS (ao contrário do
  // antigo clique-numa-barra, que só afetava a tabela): recalculam cards,
  // calendário e gráficos derivados dos lançamentos, igual às outras abas.
  // O que continua de fora — referência de jornada, esperado, comparação com
  // o período anterior — vem pronto do backend sobre o período INTEIRO,
  // porque jornada é uma propriedade da pessoa, não do cliente/projeto
  // filtrado; por isso os cards que usam esses valores dizem isso.
  const filteredEntries = useMemo(
    () => applyMyHoursFilters(s.entries, s.filters),
    [s.entries, s.filters]
  );

  const total = totalHours(filteredEntries);
  const daysWorked = distinctDaysWorked(filteredEntries);
  const avgPerDay = daysWorked > 0 ? total / daysWorked : null;
  const perDay = useMemo(() => dailyTotals(filteredEntries), [filteredEntries]);
  const pacotes = useMemo(() => aggregateByPacote(filteredEntries), [filteredEntries]);
  const billing = useMemo(() => billingSplit(filteredEntries), [filteredEntries]);
  const weekday = useMemo(() => weekdayProfile(filteredEntries), [filteredEntries]);

  // lacuna recalculada sobre o FILTRADO: um dia útil sem apontamento NESTE
  // recorte (ex.: filtrado por Cliente X, um dia trabalhado só noutro
  // cliente também conta como lacuna do recorte).
  const gapDays = useMemo(
    () => computeGapDays(perDay, s.businessDays.closed),
    [perDay, s.businessDays.closed]
  );

  const projectNames = useMemo(
    () => Array.from(new Set(filteredEntries.map((e) => e.project_name).filter(Boolean))),
    [filteredEntries]
  );

  const closedCount = s.businessDays.closed_count;

  // drill-down de um dia (clique no calendário) — separado dos filtros
  // globais, afeta só a tabela
  const filtered = useMemo(
    () => filteredEntries.filter((e) => s.selectedDate === null || e.date === s.selectedDate),
    [filteredEntries, s.selectedDate]
  );

  const sort = useSortableRows<MyHoursEntry>(filtered, (e, key) => {
    if (key === "date") return `${e.date} ${e.start ?? ""}`;
    if (key === "time") return e.start ?? null;
    if (key === "pacote") return e.pacote;
    if (key === "observacao") return e.observacao;
    return e.hours;
  });

  // ---- estados de página ----
  if (!s.loaded && s.error) {
    return (
      <div className="myh-page">
        <MyHoursHeader s={s} />
        <div className="myh-card myh-card--error" role="alert">
          <p className="error-text">
            <AlertTriangle size={15} strokeWidth={2} /> {s.error}
          </p>
          <button type="button" className="btn-primary" onClick={() => s.load(true)}>
            Tentar de novo
          </button>
        </div>
      </div>
    );
  }

  if (!s.loaded) {
    return (
      <div className="myh-page" aria-busy="true">
        <MyHoursHeader s={s} />
        <p className="sr-only" aria-live="polite">Carregando suas horas</p>
        <MyHoursSkeleton />
      </div>
    );
  }

  const empty = s.entries.length === 0;
  const emptyFiltered = !empty && filteredEntries.length === 0;

  return (
    <div className="myh-page">
      <MyHoursHeader s={s} />

      {s.error && (
        <div className="myh-banner myh-banner--error" role="alert">
          <AlertTriangle size={15} strokeWidth={2} />
          <span>{s.error}</span>
          {s.fetchedAt && <span className="muted">Mostrando dados de {s.fetchedAt}.</span>}
          <button type="button" onClick={() => s.load(true)}>Tentar de novo</button>
        </div>
      )}

      {isCurrentMonth && !empty && (
        <p className="myh-banner myh-banner--info">
          Mês em curso — {closedCount} de {s.businessDays.month_total} dias úteis encerrados.
        </p>
      )}

      <p className="sr-only" aria-live="polite">
        {s.refreshing
          ? "Atualizando"
          : `${filtered.length} lançamentos, ${fmtNum(total)} horas no recorte filtrado`}
      </p>

      {!empty && (
        <MyHoursFilters
          entries={s.entries}
          filters={s.filters}
          onChange={s.setFilter}
          onReset={s.resetFilters}
        />
      )}

      {empty ? (
        <div className="myh-card myh-empty">
          <CalendarX2 size={28} strokeWidth={1.5} />
          <h3>Nenhum lançamento entre {brDate(s.startDate)} e {brDate(s.endDate)}</h3>
          <p className="muted">
            Ou não houve apontamento nesse recorte, ou suas horas estão sob outro
            nome no Projectile. O período tem {s.businessDays.count} dias úteis.
          </p>
          <div className="myh-empty-actions">
            <button type="button" className="btn-primary" onClick={() => s.setPeriod("last_3")}>
              Ampliar para 3 meses
            </button>
            <button type="button" onClick={() => s.load(true)}>Atualizar</button>
          </div>
        </div>
      ) : emptyFiltered ? (
        <div className="myh-card myh-empty">
          <CalendarX2 size={28} strokeWidth={1.5} />
          <h3>Nenhum lançamento com os filtros atuais</h3>
          <p className="muted">Tente remover algum filtro de Competência, Cliente, Projeto ou Pacote.</p>
          <div className="myh-empty-actions">
            <button type="button" className="btn-primary" onClick={s.resetFilters}>
              Limpar filtros
            </button>
          </div>
        </div>
      ) : (
        <div className={`myh-grid ${s.refreshing ? "is-refreshing" : ""}`}>
          {/* R1 — KPIs individuais no lugar do gráfico de fechamento */}
          <div className="myh-col-12 myh-kpi-row">
            <section className="myh-card">
              <h3 className="myh-card-title">Horas apontadas</h3>
              <p className="myh-big-number">{fmtNum(total)}<span> h</span></p>
              <p className="myh-card-foot muted">
                {daysWorked} {daysWorked === 1 ? "dia" : "dias"} com apontamento
                {filtersActive && " neste filtro"}
              </p>
            </section>

            <section className="myh-card">
              <h3 className="myh-card-title">Dias com apontamento</h3>
              <p className="myh-big-number">
                {daysWorked}
                {closedCount > 0 && <span> de {closedCount}</span>}
              </p>
              <p className="myh-card-foot muted">dias úteis encerrados no período</p>
            </section>

            <section className="myh-card">
              <h3 className="myh-card-title">Média por dia apontado</h3>
              <p className="myh-big-number">
                {avgPerDay !== null ? fmtNum(avgPerDay) : "—"}<span> h/dia</span>
              </p>
              <p className="myh-card-foot muted">
                {fmtNum(total)} h ÷ {daysWorked} {daysWorked === 1 ? "dia" : "dias"}
              </p>
            </section>

            <section className="myh-card">
              <h3 className="myh-card-title">Referência da sua jornada</h3>
              {s.expected.closed !== null ? (
                <>
                  <p className="myh-big-number">
                    {s.reference.allows_percentage ? "" : "~"}
                    {fmtNum(s.expected.closed)}<span> h</span>
                  </p>
                  <p className="myh-card-foot muted">
                    {s.reference.allows_percentage ? "esperado" : "estimado"} até hoje ·{" "}
                    {filtersActive
                      ? "período completo, sem os filtros acima"
                      : `${fmtNum(totalHours(s.entries))} h apontadas`}
                  </p>
                </>
              ) : (
                <p className="muted">Sem referência de jornada — histórico insuficiente.</p>
              )}
            </section>
          </div>

          {/* R2 — calendário, sozinho, largura total */}
          <section className="myh-card myh-card--viz myh-col-12">
            <h3 className="myh-card-title">Calendário de apontamento</h3>
            <CalendarHeat
              totals={perDay}
              businessDays={s.businessDays.list}
              gapDays={gapDays}
              holidays={s.businessDays.holidays}
              outlierDays={s.outlierDays}
              today={s.today}
              rangeStart={s.startDate}
              rangeEnd={s.endDate}
              referenceHours={s.reference.hours_per_day}
              selectedDate={s.selectedDate}
              onSelectDate={s.toggleDate}
            />
            {weekday.amplitude > 0 && (
              <p className="myh-card-foot muted">
                {weekday.amplitude >= WEEKDAY_AMPLITUDE_THRESHOLD ? (
                  <>
                    Por dia da semana:{" "}
                    {weekday.averages
                      .slice(0, 5)
                      .map((a, i) => (a === null ? null : `${WEEKDAY_SHORT[i]} ${fmtNum(a)}`))
                      .filter(Boolean)
                      .join(" · ")}{" "}
                    h — amplitude {fmtNum(weekday.amplitude)} h.
                  </>
                ) : (
                  <>
                    Amplitude entre dias da semana de apenas {fmtNum(weekday.amplitude)} h — não
                    há padrão por dia da semana.
                  </>
                )}
              </p>
            )}
          </section>

          {/* R3 — dias úteis sem apontamento ao lado de ritmo e projeção, mesma altura */}
          <div className="myh-col-12 myh-row-pair">
            <section className="myh-card">
              <h3 className="myh-card-title">Dias úteis sem apontamento</h3>
              {gapDays.length === 0 ? (
                <p className="myh-ok">
                  <Check size={16} strokeWidth={2.2} />
                  Nenhum dia útil encerrado sem apontamento — {daysWorked} de {closedCount}.
                </p>
              ) : (
                <>
                  <p className="myh-big-number myh-big-number--warn">
                    {gapDays.length}
                    <span> {gapDays.length === 1 ? "dia" : "dias"}</span>
                  </p>
                  <div className="myh-chips">
                    {gapDays.slice(0, MAX_GAP_CHIPS).map((d) => (
                      <button
                        type="button"
                        key={d}
                        className={`myh-chip ${s.selectedDate === d ? "is-selected" : ""}`}
                        aria-pressed={s.selectedDate === d}
                        onClick={() => s.toggleDate(d)}
                      >
                        {brDate(d)} ({weekdayOf(d)})
                      </button>
                    ))}
                    {gapDays.length > MAX_GAP_CHIPS && (
                      <span className="muted">
                        e outros {gapDays.length - MAX_GAP_CHIPS}
                      </span>
                    )}
                  </div>
                </>
              )}
              <p className="myh-card-foot muted">
                Férias, atestado, folga e feriado municipal não são conhecidos por
                esta tela.
              </p>
            </section>

            <section className="myh-card">
              <h3 className="myh-card-title">Onde seu tempo foi</h3>
              {projectNames.length > 0 && (
                <p className="myh-card-sub muted">
                  {projectNames.length === 1
                    ? `Projeto ${projectNames[0]}`
                    : `${projectNames.length} projetos`}
                  {" · "}
                  {billing.worthShowing
                    ? `${fmtNum(billing.externo)} h externo / ${fmtNum(billing.interno)} h interno`
                    : billing.interno === billing.total
                    ? "Todo o período é trabalho interno"
                    : billing.externo === billing.total
                    ? "Todo o período é trabalho externo"
                    : "Classificação do projeto indisponível"}
                </p>
              )}
              <PacoteBars
                items={pacotes}
                selected={s.filters.pacotes}
                onSelect={s.togglePacoteFilter}
              />
              <p className="myh-card-foot muted">
                Externo/interno é a classificação do projeto, não faturamento.
              </p>
            </section>
          </div>

          {/* R4 — tendência */}
          <section className="myh-card myh-card--viz myh-col-12">
            <h3 className="myh-card-title">Tendência — 13 meses</h3>
            <MonthlyColumns series={s.monthlySeries} />
            {filtersActive && (
              <p className="myh-card-foot muted">
                Não considera os filtros de Competência/Cliente/Projeto/Pacote — é sobre
                todo o seu histórico.
              </p>
            )}
          </section>

          {/* R5 — tabela */}
          <section className="myh-card myh-col-12">
            <div className="myh-card-head">
              <h3 className="myh-card-title">Lançamentos</h3>
              <span className="muted">
                {filtered.length}
                {filtered.length !== filteredEntries.length && ` de ${filteredEntries.length}`}{" "}
                {filtered.length === 1 ? "lançamento" : "lançamentos"}
              </span>
            </div>

            {s.selectedDate && (
              <div className="myh-active-filters">
                <button
                  type="button"
                  className="myh-chip is-selected"
                  onClick={() => s.toggleDate(s.selectedDate!)}
                >
                  {brDate(s.selectedDate)} <X size={12} strokeWidth={2.5} />
                </button>
                <button type="button" className="myh-link" onClick={() => s.toggleDate(s.selectedDate!)}>
                  Limpar
                </button>
              </div>
            )}

            <div
              className="myh-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Tabela de lançamentos, rolável"
            >
              <table className="myh-table">
                <caption className="sr-only">
                  Lançamentos de horas do período, ordenável por coluna
                </caption>
                <thead>
                  <tr>
                    <SortableTh sortKey="date" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Data</SortableTh>
                    <SortableTh sortKey="time" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Horário</SortableTh>
                    <SortableTh sortKey="pacote" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Pacote</SortableTh>
                    <SortableTh sortKey="observacao" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Observação</SortableTh>
                    <SortableTh sortKey="hours" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Horas</SortableTh>
                  </tr>
                </thead>
                <tbody>
                  {sort.sortedRows.length === 0 && (
                    <tr>
                      <td colSpan={5} className="muted">
                        Nenhum lançamento com os filtros ativos.
                      </td>
                    </tr>
                  )}
                  {sort.sortedRows.map((e) => (
                    <tr key={e.id}>
                      <td><time dateTime={e.date}>{brDate(e.date)}</time></td>
                      <td className="myh-td-time">
                        {e.start && e.end ? `${e.start}–${e.end}` : "—"}
                      </td>
                      <td>{e.pacote}</td>
                      <td className="myh-td-obs" title={e.observacao}>{e.observacao}</td>
                      <td className="myh-td-num">{fmtNum(e.hours)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={4}>Total</td>
                    <td className="myh-td-num">{fmtNum(totalHours(filtered))}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </section>

          {/* R6 — limites dos dados */}
          <details className="myh-card myh-col-12 myh-limits">
            <summary>Limites destes dados</summary>
            <ul>
              <li>
                <strong>Motivo de um dia sem apontamento</strong> não é conhecido:
                férias, atestado e folga não têm fonte confiável neste banco. A tela
                mostra o fato, nunca a causa.
              </li>
              <li>
                <strong>Dias úteis considerados</strong>: {s.businessDays.note}. Feriado
                municipal de outras cidades e ponte facultativa não entram.
              </li>
              <li>
                <strong>Jornada de referência</strong>: {s.reference.label.toLowerCase()}
                {s.reference.hours_per_day !== null && ` (${fmtNum(s.reference.hours_per_day)} h/dia)`}
                {!s.reference.allows_percentage &&
                  " — por não ser jornada de contrato declarada, esta tela não afirma percentual de cumprimento."}
              </li>
              <li>
                <strong>Referência, tendência de 13 meses, projeção e comparação</strong> sempre
                olham o período completo do usuário — não reagem aos filtros de
                Competência/Cliente/Projeto/Pacote, porque descrevem sua jornada e seu
                histórico, não um recorte de trabalho.
              </li>
              <li>
                <strong>Planejado vs realizado por pacote</strong> não está disponível:
                os jobs deste usuário não têm estimativa cadastrada no Projectile.
              </li>
              <li>
                <strong>Conferência/aprovação e faturamento</strong> não existem como
                dado: os campos correspondentes estão vazios em todos os lançamentos.
                “Externo/interno” é classificação do projeto, não receita.
              </li>
              <li>
                <strong>Comparação com colegas</strong> está fora de escopo: o centro
                de custo tem gente demais de menos pra uma média não identificar
                indivíduos. Visão de equipe é papel do Painel de Gerência.
              </li>
            </ul>
          </details>
        </div>
      )}
    </div>
  );
}

/** Cabeçalho + proveniência + recorte + chip da referência de jornada.
 *
 * Renderizado em TODOS os estados (carregando, erro, vazio, normal): sem o
 * seletor e o botão vivos, um erro no primeiro carregamento deixava a tela
 * sem nenhuma ação possível a não ser F5. */
function MyHoursHeader({ s }: { s: ReturnType<typeof useMyHoursStore.getState> }) {
  const ref = s.reference;
  const refDetail =
    ref.source === "empirical" && ref.sample_days
      ? `Mediana de ${ref.sample_days} dias`
      : ref.source === "calendar"
      ? "Sem contrato cadastrado"
      : null;

  return (
    <header className="myh-head">
      <div>
        <h2 className="myh-title">Suas horas apontadas</h2>
        <p className="myh-prov muted">
          Projectile
          {s.startDate && ` · ${brDate(s.startDate)} – ${brDate(s.endDate)}`}
          {s.fetchedAt && ` · atualizado às ${s.fetchedAt}`}
        </p>
      </div>

      <div className="myh-head-controls">
        {ref.hours_per_day !== null ? (
          <span
            className={`myh-ref-chip ${ref.allows_percentage ? "is-declared" : "is-estimated"}`}
            title={
              ref.allows_percentage
                ? "Jornada declarada em contrato — permite calcular aderência"
                : "Jornada estimada — a tela não afirma percentual de cumprimento"
            }
          >
            <strong>
              {ref.allows_percentage ? "" : "~"}
              {fmtNum(ref.hours_per_day)} h/dia
            </strong>
            <span>{ref.label}{refDetail && ` · ${refDetail}`}</span>
          </span>
        ) : (
          <span className="myh-ref-chip is-missing">
            <strong>Sem referência</strong>
            <span>Histórico insuficiente</span>
          </span>
        )}

        <PeriodSegmented
          value={s.period}
          disabled={s.refreshing}
          onChange={(p: MyHoursPeriod) => s.setPeriod(p)}
        />
        <button
          type="button"
          className="myh-refresh"
          onClick={() => s.load(true)}
          disabled={s.refreshing}
          aria-label="Atualizar dados"
        >
          <RefreshCw size={14} strokeWidth={2} className={s.refreshing ? "spin" : ""} />
          {s.refreshing ? "Atualizando" : "Atualizar"}
        </button>
      </div>

      {ref.divergence_note && (
        <p className="myh-divergence">
          <AlertTriangle size={13} strokeWidth={2} /> {ref.divergence_note}
        </p>
      )}
    </header>
  );
}
