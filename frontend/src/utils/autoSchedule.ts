/** Texto do agendador da rodada mensal (`backend/app/auto_generation/scheduler.py`).
 * O backend manda `next_at` já no fuso de São Paulo ("2026-10-01T06:00:00-03:00");
 * a data e a hora são lidas do texto, sem passar por `Date`, pra não depender do
 * fuso do navegador de quem está olhando. */

export type ScheduleInfo = {
  enabled: boolean;
  day: number;
  // "HH:MM"
  time: string;
  next_at: string;
  // competência que a próxima geração vai gerar ("2026-09") e o nome dela
  target: string;
  target_label: string;
};

/** "2026-10-01T06:00:00-03:00" → "01/10/2026 às 06:00". */
export function formatScheduleAt(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  return match ? `${match[3]}/${match[2]}/${match[1]} às ${match[4]}:${match[5]}` : iso;
}

/** A frase do cabeçalho da aba e do padrão geral. */
export function describeSchedule(schedule: ScheduleInfo | null | undefined): string {
  if (!schedule) return "";
  if (!schedule.enabled) {
    return "Geração automática desligada — os rascunhos saem só pelo botão “Gerar rascunhos”.";
  }
  return `Próxima geração automática: ${formatScheduleAt(schedule.next_at)} · rascunhos de ${schedule.target_label}.`;
}
