import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Users } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { Select } from "./Select";
import { SortableTh } from "./SortableTh";
import { EmptyState, ErrorState, LoadingState } from "./PageStates";
import { useSortableRows } from "../hooks/useSortableRows";
import { useMyHoursStore } from "../store/useMyHoursStore";
import type { AppView } from "../appView";
import { fmtNum } from "../utils/fmt";
import {
  OVERLOAD_HOURS,
  fetchTeam,
  gapSummary,
  teamMonthOptions,
  type TeamOverview,
  type TeamPerson,
} from "../utils/team";

function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return `${m}/${year}`;
}

/** "Meu time" (gerente e coordenador): por pessoa de engenharia, como o mês está indo em apontamento — quem tem
 * dia útil sem nenhuma hora vem primeiro. É o que o Dashboard de horas já mostra pessoa a pessoa, numa tabela só;
 * "Ver dashboard" abre o Dashboard naquela pessoa. */
export function TeamPanel({ onNavigate }: { onNavigate: (view: AppView) => void }) {
  const months = useMemo(() => teamMonthOptions(), []);
  const [month, setMonth] = useState(months[0]);
  const [data, setData] = useState<TeamOverview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async (target: string) => {
    const request = ++latest.current;
    setLoading(true);
    setError("");
    try {
      const result = await fetchTeam(target);
      if (request === latest.current) setData(result);
    } catch (e) {
      if (request !== latest.current) return;
      setData(null);
      setError(e instanceof Error ? e.message : "Não consegui carregar o time.");
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(month);
  }, [month, load]);

  const sort = useSortableRows<TeamPerson>(data?.people ?? [], (p, key) => {
    if (key === "name") return p.name;
    if (key === "cost") return p.cost_center;
    if (key === "hours") return p.hours;
    if (key === "days") return p.days_worked;
    if (key === "avg") return p.avg_hours_per_day;
    if (key === "overload") return p.overload_days;
    return p.gap_count;
  });

  const openDashboard = (person: TeamPerson) => {
    useMyHoursStore.getState().setEmployee(person.employee_id);
    onNavigate("dashboard");
  };

  return (
    <div className="team-panel page-container">
      <PageHeader
        title="Meu time"
        description="Como cada pessoa de engenharia está apontando o mês. Quem tem dia útil sem apontamento vem primeiro."
        icon={<Users size={20} strokeWidth={1.8} />}
        actions={
          <label className="team-month">
            Mês
            <Select
              ariaLabel="Mês do time"
              value={month}
              options={months.map((m) => ({ value: m, label: monthLabel(m) }))}
              onChange={setMonth}
            />
          </label>
        }
      />

      {loading && !data && (
        <div className="card">
          <LoadingState label="Carregando o time..." rows={6} />
        </div>
      )}
      {error && (
        <div className="card">
          <ErrorState message={error} onRetry={() => void load(month)} busy={loading} />
        </div>
      )}

      {data && (
        <>
          <div className="team-totals" aria-busy={loading}>
            <div className="card">
              <span className="muted">Pessoas</span>
              <strong>{data.totals.people}</strong>
            </div>
            <div className="card">
              <span className="muted">Com dia útil sem apontamento</span>
              <strong>{data.totals.with_gaps}</strong>
            </div>
            <div className="card">
              <span className="muted">Horas apontadas</span>
              <strong>{fmtNum(data.totals.hours)} h</strong>
            </div>
            <div className="card">
              <span className="muted">Com dia acima de {OVERLOAD_HOURS} h</span>
              <strong>{data.totals.overloaded}</strong>
            </div>
          </div>

          <div className="card team-table-wrap">
            {data.people.length === 0 ? (
              <EmptyState
                icon={<Users size={22} strokeWidth={1.6} />}
                title="Ninguém com apontamento neste período"
                description="Só entram pessoas de engenharia com apontamento nos últimos dois meses."
              />
            ) : (
              <table className="kpi-table team-table">
                <thead>
                  <tr>
                    <SortableTh
                      sortKey="name"
                      activeKey={sort.sortKey}
                      direction={sort.direction}
                      onSort={sort.toggleSort}
                    >
                      Colaborador
                    </SortableTh>
                    <SortableTh
                      sortKey="cost"
                      activeKey={sort.sortKey}
                      direction={sort.direction}
                      onSort={sort.toggleSort}
                    >
                      Centro
                    </SortableTh>
                    <SortableTh
                      sortKey="hours"
                      activeKey={sort.sortKey}
                      direction={sort.direction}
                      onSort={sort.toggleSort}
                    >
                      Horas
                    </SortableTh>
                    <SortableTh
                      sortKey="days"
                      activeKey={sort.sortKey}
                      direction={sort.direction}
                      onSort={sort.toggleSort}
                    >
                      Dias com apontamento
                    </SortableTh>
                    <SortableTh
                      sortKey="gaps"
                      activeKey={sort.sortKey}
                      direction={sort.direction}
                      onSort={sort.toggleSort}
                    >
                      Dias úteis sem apontamento
                    </SortableTh>
                    <SortableTh
                      sortKey="avg"
                      activeKey={sort.sortKey}
                      direction={sort.direction}
                      onSort={sort.toggleSort}
                    >
                      Média h/dia
                    </SortableTh>
                    <SortableTh
                      sortKey="overload"
                      activeKey={sort.sortKey}
                      direction={sort.direction}
                      onSort={sort.toggleSort}
                    >
                      Dias &gt; {OVERLOAD_HOURS} h
                    </SortableTh>
                    <th aria-label="Ações" />
                  </tr>
                </thead>
                <tbody>
                  {sort.sortedRows.map((p) => (
                    <tr key={p.employee_id}>
                      <td>{p.name}</td>
                      <td>{p.cost_center ?? "—"}</td>
                      <td>{fmtNum(p.hours)}</td>
                      <td>
                        {p.days_worked}
                        <span className="muted"> de {p.closed_business_days} úteis</span>
                      </td>
                      <td>
                        {p.gap_count === 0 ? (
                          <span className="muted">—</span>
                        ) : (
                          <span className="team-gap" data-hint={gapSummary(p.gap_days)}>
                            {p.gap_count}
                          </span>
                        )}
                      </td>
                      <td>{p.avg_hours_per_day === null ? "—" : fmtNum(p.avg_hours_per_day)}</td>
                      <td>{p.overload_days === 0 ? <span className="muted">—</span> : p.overload_days}</td>
                      <td>
                        <button type="button" className="btn-secondary" onClick={() => openDashboard(p)}>
                          Ver dashboard
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="muted team-note">
              Dia sem apontamento = dia útil já encerrado sem nenhuma hora. O sistema não sabe de férias nem de
              afastamento: quem está fora o mês inteiro aparece com todos os dias sem apontamento.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
