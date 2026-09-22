import { MESES_PT } from "../store/useReportStore";

export const EARLIEST_REPORT_YEAR = 2008;

/** Anos com dados disponíveis no Projectile, do atual até 2008. */
export function getReportYearOptions(currentYear = new Date().getFullYear()): string[] {
  return Array.from(
    { length: Math.max(0, currentYear - EARLIEST_REPORT_YEAR + 1) },
    (_, index) => String(currentYear - index),
  );
}

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

function canonicalMonth(value: string): string | null {
  return MESES_PT.find((month) => month.toLowerCase() === value.trim().toLowerCase()) ?? null;
}

/** Converte o rótulo persistido do relatório de volta para os controles.
 * Aceita as três formas produzidas por buildPeriodLabel e mantém um fallback
 * separado para bundles antigos que só guardavam o mês final. */
export function parsePeriodLabelForControls(
  label: string,
  fallbackEndLabel = label,
  fallbackYear = String(new Date().getFullYear())
): MonthYearRange {
  const crossYear = /^([^/]+)\/(\d{4})\s+a\s+([^/]+)\/(\d{4})$/i.exec(label.trim());
  if (crossYear) {
    const startMonth = canonicalMonth(crossYear[1]);
    const endMonth = canonicalMonth(crossYear[3]);
    if (startMonth && endMonth) {
      return { startMonth, startYear: crossYear[2], endMonth, endYear: crossYear[4] };
    }
  }

  const sameYear = /^(.+?)\s+a\s+([^/]+)\/(\d{4})$/i.exec(label.trim());
  if (sameYear) {
    const startMonth = canonicalMonth(sameYear[1]);
    const endMonth = canonicalMonth(sameYear[2]);
    if (startMonth && endMonth) {
      return { startMonth, startYear: sameYear[3], endMonth, endYear: sameYear[3] };
    }
  }

  const single = /^([^/]+)\/(\d{4})$/.exec(label.trim());
  const fallbackEnd = /^([^/]+)\/(\d{4})$/.exec(fallbackEndLabel.trim());
  const startMonth = single ? canonicalMonth(single[1]) : null;
  const endMonth = fallbackEnd ? canonicalMonth(fallbackEnd[1]) : null;
  const startYear = single?.[2] ?? fallbackYear;

  return {
    startMonth: startMonth ?? MESES_PT[0],
    startYear,
    endMonth: endMonth ?? startMonth ?? MESES_PT[0],
    endYear: fallbackEnd?.[2] ?? startYear,
  };
}

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
