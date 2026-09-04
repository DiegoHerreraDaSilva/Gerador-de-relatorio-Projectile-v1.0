/** Tipos e agregações do Dashboard de horas pessoal.
 *
 * O backend (`GET /my-hours`) já entrega o que o frontend NÃO pode derivar dos
 * lançamentos: a lista de dias úteis, a referência de jornada com a fonte, a
 * série de 13 meses e a comparação com a janela anterior. Aqui ficam só as
 * agregações que dependem do recorte visível (e do cross-filter). */

export type BillingClass = "externo" | "interno" | "nao_classificado";

export type MyHoursEntry = {
  id: string;
  date: string; // "YYYY-MM-DD"
  start: string | null; // "HH:MM" — null quando pStart/pEnd é inválido
  end: string | null;
  hours: number;
  pacote: string;
  observacao: string;
  project_id: string | null;
  project_name: string;
  top_project: string | null;
  cost_center: string | null;
  billing_class: BillingClass;
};

/** `source` é o que autoriza (ou proíbe) percentual na tela: só `contract`
 * vem de jornada declarada. Ver `allows_percentage`. */
export type JourneySource = "contract" | "empirical" | "calendar" | "none";

export type MyHoursReference = {
  source: JourneySource;
  hours_per_weekday: number[] | null; // 7 posições, 0 = segunda
  hours_per_day: number | null;
  allows_percentage: boolean;
  sample_days: number | null;
  window_days: number | null;
  label: string;
  divergence_note: string | null;
};

export type MyHoursBusinessDays = {
  list: string[];
  closed: string[];
  count: number;
  closed_count: number;
  month_total: number;
  month_remaining: number;
  holidays: string[];
  source: string;
  note: string;
};

export type MonthlyPoint = {
  month: string; // "YYYY-MM"
  hours: number;
  days_worked: number;
  business_days: number;
  business_days_closed: number;
  partial: boolean;
  no_data: boolean;
};

export type MyHoursComparison = {
  label: string;
  hours: number;
  delta_hours: number;
  delta_pct: number;
};

export type MyHoursDailyStats = {
  p25: number | null;
  median: number | null;
  p75: number | null;
  n: number;
  window_days: number;
};

export type MyHoursResponse = {
  period: string;
  start_date: string;
  end_date: string;
  today: string;
  entries: MyHoursEntry[];
  business_days: MyHoursBusinessDays;
  reference: MyHoursReference;
  expected: { closed: number | null; period: number | null; month: number | null };
  gap_days: string[];
  outlier_days: string[];
  monthly_series: MonthlyPoint[];
  comparison: MyHoursComparison | null;
  daily_stats: MyHoursDailyStats;
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

export type PacoteTotal = { name: string; hours: number; share: number };

/** Ranking de horas por PACOTE de trabalho (`capJob`), maior primeiro.
 *
 * Pacote e não projeto: medido que o usuário de referência tem 1 projeto e 3
 * pacotes, então agrupar por projeto rende uma barra só. O projeto sobe pro
 * subtítulo do card, onde é contexto em vez de eixo.
 *
 * `share` é a fração do total do período (não do maior item) — uma barra
 * normalizada pelo próprio máximo fica sempre em 100% e deixa de ser gráfico
 * quando existe um item só. */
export function aggregateByPacote(entries: MyHoursEntry[]): PacoteTotal[] {
  const totals = new Map<string, number>();
  for (const e of entries) {
    const key = e.pacote || "Sem pacote";
    totals.set(key, (totals.get(key) ?? 0) + e.hours);
  }
  const total = entries.reduce((sum, e) => sum + e.hours, 0);
  return Array.from(totals.entries())
    .map(([name, hours]) => ({
      name,
      hours: round2(hours),
      share: total > 0 ? hours / total : 0,
    }))
    .sort((a, b) => b.hours - a.hours);
}

/** Mapa "YYYY-MM-DD" -> horas somadas. Dia sem lançamento não entra: dia
 * ausente é dia sem informação, não dia de zero hora (o calendário distingue
 * os dois estados visualmente). */
export function dailyTotals(entries: MyHoursEntry[]): Map<string, number> {
  const totals = new Map<string, number>();
  for (const e of entries) {
    totals.set(e.date, round2((totals.get(e.date) ?? 0) + e.hours));
  }
  return totals;
}

export type DayWindow = {
  date: string;
  startMin: number; // minutos desde a meia-noite
  endMin: number;
  spanHours: number;
  loggedHours: number;
};

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":");
  return Number(h) * 60 + Number(m);
}

/** Janela entrada->saída por dia, a partir de `start`/`end` dos lançamentos.
 *
 * Só considera lançamentos com AMBAS as pontas válidas (o backend anula as
 * duas quando o span é negativo). Dia sem nenhum lançamento válido não entra
 * — nunca inferir horário a partir do total de horas. */
export function dayWindows(entries: MyHoursEntry[]): DayWindow[] {
  const byDay = new Map<string, { min: number; max: number; logged: number }>();
  for (const e of entries) {
    if (!e.start || !e.end) continue;
    const from = toMinutes(e.start);
    const to = toMinutes(e.end);
    const current = byDay.get(e.date);
    if (!current) {
      byDay.set(e.date, { min: from, max: to, logged: e.hours });
    } else {
      current.min = Math.min(current.min, from);
      current.max = Math.max(current.max, to);
      current.logged += e.hours;
    }
  }
  return Array.from(byDay.entries())
    .map(([date, w]) => ({
      date,
      startMin: w.min,
      endMin: w.max,
      spanHours: round2((w.max - w.min) / 60),
      loggedHours: round2(w.logged),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

export type BillingSplit = {
  externo: number;
  interno: number;
  nao_classificado: number;
  total: number;
  /** true quando pelo menos duas classes passam de 5% — só aí uma faixa de
   * composição informa algo. Medido 100% interno no usuário de referência:
   * um donut ali gastava um terço da largura pra dizer "0% / 100%". */
  worthShowing: boolean;
};

export function billingSplit(entries: MyHoursEntry[]): BillingSplit {
  const acc = { externo: 0, interno: 0, nao_classificado: 0 };
  for (const e of entries) acc[e.billing_class] += e.hours;
  const total = acc.externo + acc.interno + acc.nao_classificado;
  const meaningful = total > 0
    ? Object.values(acc).filter((h) => h / total >= 0.05).length
    : 0;
  return {
    externo: round2(acc.externo),
    interno: round2(acc.interno),
    nao_classificado: round2(acc.nao_classificado),
    total: round2(total),
    worthShowing: meaningful >= 2,
  };
}

/** Média por dia da semana (0=segunda) sobre os dias COM apontamento, e a
 * amplitude entre o maior e o menor.
 *
 * A amplitude existe pra decidir se vale desenhar: medido seg 5,76 ... sex
 * 5,87 no usuário de referência, ou seja 0,16 h de amplitude (2,8%) — cinco
 * barras praticamente idênticas ocupando um card pra dizer "não há padrão
 * por dia da semana". Abaixo do limiar, o dashboard escreve a frase. */
export function weekdayProfile(entries: MyHoursEntry[]): {
  averages: (number | null)[];
  counts: number[];
  amplitude: number;
} {
  const perDay = dailyTotals(entries);
  const buckets: number[][] = [[], [], [], [], [], [], []];
  for (const [date, hours] of perDay) {
    // "YYYY-MM-DD" -> índice 0=segunda, sem depender de fuso do Date local
    const weekday = (new Date(`${date}T12:00:00`).getDay() + 6) % 7;
    buckets[weekday].push(hours);
  }
  const averages = buckets.map((b) =>
    b.length > 0 ? round2(b.reduce((s, h) => s + h, 0) / b.length) : null
  );
  const present = averages.filter((a): a is number => a !== null);
  return {
    averages,
    counts: buckets.map((b) => b.length),
    amplitude: present.length > 1 ? round2(Math.max(...present) - Math.min(...present)) : 0,
  };
}
