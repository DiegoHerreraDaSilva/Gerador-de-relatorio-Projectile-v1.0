import { useEffect } from "react";
import { Clock, CalendarCheck, Receipt, RefreshCw } from "lucide-react";
import { useMyHoursStore, type MyHoursPeriod } from "../store/useMyHoursStore";
import { SortableTh } from "./SortableTh";
import { useSortableRows } from "../hooks/useSortableRows";
import { BarList, type BarListItem } from "./BarList";
import { LineChart } from "./LineChart";
import { Donut } from "./Donut";
import { fmtNum } from "../utils/fmt";
import {
  aggregateByProject,
  aggregateByDay,
  billableSplit,
  totalHours,
  distinctDaysWorked,
  type MyHoursEntry,
} from "../utils/myHours";

const PERIOD_OPTIONS: { value: MyHoursPeriod; label: string }[] = [
  { value: "current_month", label: "Mês atual" },
  { value: "last_3", label: "Últimos 3 meses" },
  { value: "last_6", label: "Últimos 6 meses" },
  { value: "last_12", label: "Últimos 12 meses" },
];

const MAX_PROJECT_BARS = 8;

// lista ranqueada não pode só cortar em N e descartar o resto (mentiria
// sobre a proporção) — dobra a cauda num bucket "Outros" que preserva o
// total (ver skill de dashboard Schwaben).
function capWithOthers(items: { name: string; hours: number }[]): BarListItem[] {
  if (items.length <= MAX_PROJECT_BARS) return items;
  const head = items.slice(0, MAX_PROJECT_BARS - 1);
  const tailHours = items.slice(MAX_PROJECT_BARS - 1).reduce((sum, i) => sum + i.hours, 0);
  return [...head, { name: "Outros", hours: Math.round(tailHours * 100) / 100 }];
}

function formatDayLabel(iso: string): string {
  // "2026-08-03" -> "03/08"
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
}

function KpiCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="my-hours-card my-hours-kpi-card">
      <div className="my-hours-kpi-top">
        <div className="my-hours-kpi-value">{value}</div>
        <span className="my-hours-kpi-icon-box">{icon}</span>
      </div>
      <div className="my-hours-kpi-label">{label}</div>
      {sub && <p className="my-hours-kpi-sub">{sub}</p>}
    </div>
  );
}

export function MyHoursDashboard() {
  const entries = useMyHoursStore((s) => s.entries);
  const businessDaysExpected = useMyHoursStore((s) => s.businessDaysExpected);
  const period = useMyHoursStore((s) => s.period);
  const setPeriod = useMyHoursStore((s) => s.setPeriod);
  const error = useMyHoursStore((s) => s.error);
  const loaded = useMyHoursStore((s) => s.loaded);
  const refreshing = useMyHoursStore((s) => s.refreshing);
  const load = useMyHoursStore((s) => s.load);

  useEffect(() => {
    load();
  }, [load]);

  const sort = useSortableRows<MyHoursEntry>(entries, (e, key) => {
    if (key === "date") return e.date;
    if (key === "pacote") return e.pacote;
    if (key === "observacao") return e.observacao;
    return e.hours;
  });

  if (!loaded) {
    return (
      <div className="my-hours-page">
        <div className="my-hours-card">
          <p className={error ? "error-text" : "muted"}>{error || "Carregando..."}</p>
        </div>
      </div>
    );
  }

  const total = totalHours(entries);
  const daysWorked = distinctDaysWorked(entries);
  const { billableHours, nonBillableHours, billablePct } = billableSplit(entries);
  const projectBars = capWithOthers(aggregateByProject(entries));
  const dayPoints = aggregateByDay(entries).map((d) => ({ label: formatDayLabel(d.date), value: d.hours }));

  return (
    <div className="my-hours-page">
      <div>
        <h2 className="my-hours-title">Suas horas apontadas</h2>
        <p className="my-hours-subtitle">Dados direto do Projectile — clique num cabeçalho de coluna pra ordenar a tabela.</p>
      </div>

      {error && (
        <div className="my-hours-card">
          <p className="error-text">{error}</p>
        </div>
      )}

      <div className="my-hours-toolbar">
        <label className="my-hours-period">
          <span className="my-hours-period-label">Período</span>
          <select value={period} onChange={(e) => setPeriod(e.target.value as MyHoursPeriod)}>
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
        <button type="button" className="my-hours-refresh" onClick={() => load(true)} disabled={refreshing}>
          <RefreshCw size={14} strokeWidth={2} className={refreshing ? "spin" : ""} />
          {refreshing ? "Atualizando..." : "Atualizar"}
        </button>
      </div>

      <div className="my-hours-kpi-row">
        <KpiCard icon={<Clock size={18} strokeWidth={1.8} />} label="Total de horas" value={`${fmtNum(total)} h`} />
        <KpiCard
          icon={<CalendarCheck size={18} strokeWidth={1.8} />}
          label="Dias com apontamento"
          value={`${daysWorked} de ${businessDaysExpected}`}
          sub="dias úteis do período"
        />
        <KpiCard
          icon={<Receipt size={18} strokeWidth={1.8} />}
          label="Faturável"
          value={billablePct === null ? "—" : `${fmtNum(billablePct * 100)}%`}
          sub={`${fmtNum(billableHours)} h de ${fmtNum(billableHours + nonBillableHours)} h`}
        />
      </div>

      <div className="my-hours-viz-grid">
        <div className="my-hours-card">
          <h3 className="my-hours-card-title">Horas por projeto</h3>
          <BarList items={projectBars} emptyMessage="Nenhum lançamento no período selecionado." />
        </div>

        <div className="my-hours-card">
          <h3 className="my-hours-card-title">Faturável x não faturável</h3>
          <Donut
            slices={[
              { label: "Faturável", value: billableHours, color: "var(--accent)" },
              { label: "Não faturável", value: nonBillableHours, color: "#78838d" },
            ]}
            totalLabel={`${fmtNum(billableHours + nonBillableHours)} h`}
            totalCaption="Total"
          />
        </div>

        <div className="my-hours-card">
          <h3 className="my-hours-card-title">Horas por dia</h3>
          <LineChart points={dayPoints} />
        </div>
      </div>

      <div className="my-hours-card">
        <h3 className="my-hours-card-title">Lançamentos</h3>
        <div className="my-hours-table-wrap">
          <table className="my-hours-table">
            <thead>
              <tr>
                <SortableTh sortKey="date" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Data</SortableTh>
                <SortableTh sortKey="pacote" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Pacote</SortableTh>
                <SortableTh sortKey="observacao" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Observação</SortableTh>
                <SortableTh sortKey="hours" activeKey={sort.sortKey} direction={sort.direction} onSort={sort.toggleSort}>Horas</SortableTh>
              </tr>
            </thead>
            <tbody>
              {sort.sortedRows.length === 0 && (
                <tr><td colSpan={4} className="muted">Nenhum lançamento no período selecionado.</td></tr>
              )}
              {sort.sortedRows.map((e, i) => (
                <tr key={`${e.date}-${i}`}>
                  <td>{e.date.split("-").reverse().join("/")}</td>
                  <td>{e.pacote}</td>
                  <td>{e.observacao}</td>
                  <td>{fmtNum(e.hours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
