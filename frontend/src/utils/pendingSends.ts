import type { ProjectSendStatusRow } from "../store/useManagementStore";

/** Depois de quantos dias corridos do fim do mês um relatório sem envio passa a contar como ATRASADO. */
export const LATE_AFTER_DAYS = 10;

export type PendingItem = {
  client: string;
  project_id: string;
  project_name: string;
  month: string;
  status: "none" | "partial";
  missing_pacotes: string[];
  /** Dias corridos desde o último dia do mês. */
  daysLate: number;
  late: boolean;
};

export type PendingClient = {
  client: string;
  items: PendingItem[];
  oldestDays: number;
  lateCount: number;
};

export type PendingSummary = { clients: PendingClient[]; total: number; late: number };

/** Dias corridos entre o último dia de `month` ("AAAA-MM") e `today`. 0 ou negativo = o mês ainda não fechou. */
export function daysSinceMonthEnd(month: string, today: Date): number {
  const [year, m] = month.split("-").map(Number);
  if (!year || !m) return 0;
  const lastDay = new Date(year, m, 0); // dia 0 do mês seguinte = último dia deste
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((startOfToday.getTime() - lastDay.getTime()) / 86_400_000);
}

/** O que está pendente de envio: projeto/mês com status "none" (nada enviado) ou "partial" (faltam pacotes),
 * só em meses já FECHADOS (o mês corrente ainda está em andamento) e dentro de `months`. Fechado/enviado não
 * entra. Agrupa por cliente, o mais atrasado primeiro — é a lista de quem cobrar. */
export function summarizePending(
  rows: ProjectSendStatusRow[],
  months: Set<string> | null,
  today: Date = new Date(),
): PendingSummary {
  const byClient = new Map<string, PendingItem[]>();
  for (const row of rows) {
    if (row.status !== "none" && row.status !== "partial") continue;
    if (months && months.size > 0 && !months.has(row.month)) continue;
    const daysLate = daysSinceMonthEnd(row.month, today);
    if (daysLate <= 0) continue;
    const item: PendingItem = {
      client: row.client,
      project_id: row.project_id,
      project_name: row.project_name,
      month: row.month,
      status: row.status,
      missing_pacotes: row.missing_pacotes,
      daysLate,
      late: daysLate > LATE_AFTER_DAYS,
    };
    byClient.set(row.client, [...(byClient.get(row.client) ?? []), item]);
  }
  const clients: PendingClient[] = [...byClient.entries()].map(([client, items]) => ({
    client,
    items: items.sort((a, b) => b.daysLate - a.daysLate || a.project_name.localeCompare(b.project_name, "pt-BR")),
    oldestDays: Math.max(...items.map((i) => i.daysLate)),
    lateCount: items.filter((i) => i.late).length,
  }));
  clients.sort(
    (a, b) =>
      b.oldestDays - a.oldestDays || b.items.length - a.items.length || a.client.localeCompare(b.client, "pt-BR"),
  );
  const total = clients.reduce((sum, c) => sum + c.items.length, 0);
  const late = clients.reduce((sum, c) => sum + c.lateCount, 0);
  return { clients, total, late };
}
