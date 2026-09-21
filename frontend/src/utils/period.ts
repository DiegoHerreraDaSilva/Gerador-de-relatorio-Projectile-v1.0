import { MESES_PT } from "../store/useReportStore";

// Espelha backend/app/generator.py::parse_period_label — mês único fica
// exatamente como já era ("Julho/2026"); um período colapsa pra essa mesma
// forma quando início==fim (reduz a zero a chance de regressão no caso mais
// comum), senão "Julho a Novembro/2026" (mesmo ano) ou "Dezembro/2025 a
// Fevereiro/2026" (cruzando ano).
export function buildPeriodLabel(startMonth: string, startYear: string, endMonth: string, endYear: string): string {
  if (startMonth === endMonth && startYear === endYear) return `${startMonth}/${startYear}`;
  if (startYear === endYear) return `${startMonth} a ${endMonth}/${endYear}`;
  return `${startMonth}/${startYear} a ${endMonth}/${endYear}`;
}

export type MonthYearRange = { startMonth: string; startYear: string; endMonth: string; endYear: string };

// Os N meses calendário mais recentes já FECHADOS (nunca inclui o mês
// corrente, que ainda não tem hora completa apontada) — mesmo espírito de
// `_MY_HOURS_PERIOD_MONTHS` no backend (`main.py`), só que calculado no
// cliente, sem chamada ao servidor. `now` é injetável só pra teste.
export function lastClosedMonthsRange(monthsBack: number, now: Date = new Date()): MonthYearRange {
  const endDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const startDate = new Date(now.getFullYear(), now.getMonth() - monthsBack, 1);
  return {
    startMonth: MESES_PT[startDate.getMonth()],
    startYear: String(startDate.getFullYear()),
    endMonth: MESES_PT[endDate.getMonth()],
    endYear: String(endDate.getFullYear()),
  };
}
