export type MyHoursEntry = {
  date: string; // "YYYY-MM-DD"
  hours: number;
  pacote: string;
  observacao: string;
  project_id: string | null;
  project_name: string;
  cost_center: string | null;
  billable: boolean;
};

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export function totalHours(entries: MyHoursEntry[]): number {
  return round2(entries.reduce((sum, e) => sum + e.hours, 0));
}

export function distinctDaysWorked(entries: MyHoursEntry[]): number {
  return new Set(entries.map((e) => e.date)).size;
}

export type ProjectTotal = { name: string; hours: number };

/** Ranking de horas por projeto, maior primeiro — base do BarList. */
export function aggregateByProject(entries: MyHoursEntry[]): ProjectTotal[] {
  const totals = new Map<string, number>();
  for (const e of entries) {
    totals.set(e.project_name, (totals.get(e.project_name) ?? 0) + e.hours);
  }
  return Array.from(totals.entries())
    .map(([name, hours]) => ({ name, hours: round2(hours) }))
    .sort((a, b) => b.hours - a.hours);
}

export type DayTotal = { date: string; hours: number };

/** Série por dia, ordenada cronologicamente. Dias sem lançamento simplesmente
 * não aparecem — nunca inventa um zero no meio da série (ver LineChart). */
export function aggregateByDay(entries: MyHoursEntry[]): DayTotal[] {
  const totals = new Map<string, number>();
  for (const e of entries) {
    totals.set(e.date, (totals.get(e.date) ?? 0) + e.hours);
  }
  return Array.from(totals.entries())
    .map(([date, hours]) => ({ date, hours: round2(hours) }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export type BillableSplit = { billableHours: number; nonBillableHours: number; billablePct: number | null };

export function billableSplit(entries: MyHoursEntry[]): BillableSplit {
  let billableHours = 0;
  let nonBillableHours = 0;
  for (const e of entries) {
    if (e.billable) billableHours += e.hours;
    else nonBillableHours += e.hours;
  }
  const total = billableHours + nonBillableHours;
  return {
    billableHours: round2(billableHours),
    nonBillableHours: round2(nonBillableHours),
    billablePct: total > 0 ? billableHours / total : null,
  };
}
