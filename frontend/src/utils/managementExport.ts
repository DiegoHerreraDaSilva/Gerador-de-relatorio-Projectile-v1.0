import type { MonthRow } from "../store/useManagementStore";
import type { ExportableTable } from "./downloadXlsx";

const round2 = (n: number) => Math.round(n * 100) / 100;

/** Período/Competência do filtro em texto, pro título do arquivo. */
export function periodTitle(period: string, selectedMonths: string[]): string {
  const base = period === "rolling" ? "Últimos 12 meses" : period;
  if (selectedMonths.length === 0) return base;
  const months = [...selectedMonths].sort();
  return months.length === 1 ? months[0] : `${months[0]} a ${months[months.length - 1]}`;
}

/** A tabela do Painel de Gerência, mês a mês em ordem cronológica, pronta pro Excel. Os totais seguem a MESMA
 * regra da tela: faturadas e performance só somam os meses com "Faturadas" preenchida (misturar com todos os
 * meses dava um KPI sem sentido). Percentuais vão em pontos percentuais (a API devolve fração). Com o filtro de
 * Pessoa ativo, faturado/performance/prazo não existem (vêm nulos) e o total fica em branco, não em zero. */
export function buildMonthlyTable(rows: MonthRow[], title: string, personsFilterActive = false): ExportableTable {
  const ordered = [...rows].sort((a, b) => a.month.localeCompare(b.month));
  const pct = (value: number | null) => (value === null ? null : round2(value * 100));
  const entered = ordered.filter((r) => r.billed_hours !== null);
  const workedForPerf = round2(entered.reduce((s, r) => s + r.worked_hours, 0));
  const billed = round2(entered.reduce((s, r) => s + (r.billed_hours ?? 0), 0));
  const perfHours = round2(billed - workedForPerf);
  const worked = round2(ordered.reduce((s, r) => s + r.worked_hours, 0));
  const nonbillable = round2(ordered.reduce((s, r) => s + r.nonbillable_hours, 0));
  const withDays = ordered.filter((r) => r.elaboration_days !== null);
  const avgDays = withDays.length
    ? round2(withDays.reduce((s, r) => s + (r.elaboration_days ?? 0), 0) / withDays.length)
    : null;
  const noBilling = personsFilterActive || entered.length === 0;

  return {
    title,
    columns: [
      "Competência",
      "Horas trabalhadas",
      "Horas faturadas",
      "Performance (h)",
      "Performance (%)",
      "Horas não faturáveis",
      "Não faturável (%)",
      "Prazo de elaboração (dias)",
    ],
    column_types: ["text", "hours", "hours", "hours", "percent", "hours", "percent", "text"],
    rows: ordered.map((r) => [
      r.month,
      round2(r.worked_hours),
      r.billed_hours === null ? null : round2(r.billed_hours),
      r.perf_hours === null ? null : round2(r.perf_hours),
      pct(r.perf_kpi_pct),
      round2(r.nonbillable_hours),
      pct(r.nonbillable_kpi_pct),
      r.elaboration_days === null ? null : round2(r.elaboration_days),
    ]),
    totals: [
      "Total",
      worked,
      noBilling ? null : billed,
      noBilling ? null : perfHours,
      noBilling || workedForPerf <= 0 ? null : round2((perfHours / workedForPerf) * 100),
      nonbillable,
      worked > 0 ? round2((nonbillable / worked) * 100) : null,
      personsFilterActive ? null : avgDays,
    ],
  };
}

export type MonthDelta = {
  /** Variação das horas trabalhadas sobre o mês anterior, em % (null se não há mês anterior ou ele foi 0). */
  workedPct: number | null;
  /** Variação do KPI de performance, em pontos percentuais (null se faltar um dos dois meses). */
  perfPoints: number | null;
};

function previousMonthKey(month: string): string | null {
  const [year, m] = month.split("-").map(Number);
  if (!year || !m) return null;
  return m === 1 ? `${year - 1}-12` : `${year}-${String(m - 1).padStart(2, "0")}`;
}

/** Comparativo de cada mês com o mês CALENDÁRIO anterior, calculado sobre todas as linhas (não só as filtradas:
 * comparar "agosto" com "julho" vale mesmo com só agosto selecionado). Mês anterior ausente não vira zero. */
export function previousMonthDeltas(rows: MonthRow[]): Map<string, MonthDelta> {
  const byMonth = new Map(rows.map((r) => [r.month, r]));
  const out = new Map<string, MonthDelta>();
  for (const row of rows) {
    const key = previousMonthKey(row.month);
    const prev = key ? byMonth.get(key) : undefined;
    out.set(row.month, {
      workedPct:
        prev && prev.worked_hours > 0
          ? round2(((row.worked_hours - prev.worked_hours) / prev.worked_hours) * 100)
          : null,
      perfPoints:
        prev && prev.perf_kpi_pct !== null && row.perf_kpi_pct !== null
          ? round2((row.perf_kpi_pct - prev.perf_kpi_pct) * 100)
          : null,
    });
  }
  return out;
}

/** "▲ 5,2%" / "▼ 3,1 pts" / "= 0" — com sinal explícito pra leitor de tela e sem cor como único sinal. */
export function formatDelta(value: number | null, unit: "%" | "pts"): string {
  if (value === null) return "";
  if (value === 0) return "= 0";
  const arrow = value > 0 ? "▲" : "▼";
  const number = Math.abs(value).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  return `${arrow} ${number}${unit === "%" ? "%" : " pts"}`;
}
