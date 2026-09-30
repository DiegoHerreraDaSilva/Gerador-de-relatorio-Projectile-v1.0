export type TeamPerson = {
  employee_id: string;
  name: string;
  cost_center: string | null;
  hours: number;
  days_worked: number;
  closed_business_days: number;
  gap_days: string[];
  gap_count: number;
  avg_hours_per_day: number | null;
  overload_days: number;
};

export type TeamOverview = {
  month: string;
  start_date: string;
  end_date: string;
  today: string;
  people: TeamPerson[];
  totals: { people: number; with_gaps: number; hours: number; overloaded: number };
};

/** Dia com mais horas que isto conta como "pesado" (espelha `team_overview.OVERLOAD_HOURS` no backend). */
export const OVERLOAD_HOURS = 10;

/** Meses da tela: o atual e os 5 anteriores (todos dentro da janela de 12 meses do coordenador), do mais novo ao mais antigo. */
export function teamMonthOptions(today: Date = new Date(), count = 6): string[] {
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });
}

/** "02/09, 03/09 e mais 4" — as datas (AAAA-MM-DD, do mais recente ao mais antigo) que ficaram sem apontamento. */
export function gapSummary(days: string[], max = 6): string {
  const shown = days.slice(0, max).map((d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`);
  if (days.length > max) return `${shown.join(", ")} e mais ${days.length - max}`;
  if (shown.length <= 1) return shown.join("");
  return `${shown.slice(0, -1).join(", ")} e ${shown[shown.length - 1]}`;
}

/** Busca o time de um mês ("AAAA-MM"). Levanta com mensagem pronta pra tela. */
export async function fetchTeam(month: string): Promise<TeamOverview> {
  const res = await fetch(`/my-hours/team?${new URLSearchParams({ month }).toString()}`);
  if (res.status === 400) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "Esse mês não está disponível.");
  }
  if (res.status === 401) throw new Error("Sessão expirada. Entre de novo.");
  if (res.status === 403) throw new Error("Você não tem acesso a este mês ou a esta tela.");
  if (!res.ok) throw new Error("Não consegui carregar o time agora. Tenta de novo em instantes.");
  return (await res.json()) as TeamOverview;
}
