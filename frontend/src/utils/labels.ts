// Espelha backend/app/generator.py::_LABELS e _MONTH_NAMES — os textos fixos
// do relatório (título, cabeçalhos, Bruto/Performance) precisam aparecer
// traduzidos tanto no preview quanto no arquivo exportado, então as duas
// pontas usam o mesmo dicionário. Qualquer rótulo novo lá precisa ser
// replicado aqui também.
export type Language = "pt" | "en" | "de";

export const LABELS: Record<Language, {
  title: string;
  subtitle: string;
  activityDescription: string;
  hours: string;
  bruto: string;
  performance: string;
  totalHours: string;
}> = {
  pt: {
    title: "RELATÓRIO DE HORAS",
    subtitle: "Relatório de horas referentes ao mês de {month}",
    activityDescription: "Descritivo de Atividades",
    hours: "Horas",
    bruto: "Bruto",
    performance: "Performance",
    totalHours: "Total de horas {month}:",
  },
  en: {
    title: "HOURS REPORT",
    subtitle: "Hours report for the month of {month}",
    activityDescription: "Activity Description",
    hours: "Hours",
    bruto: "Gross",
    performance: "Performance",
    totalHours: "Total hours {month}:",
  },
  de: {
    title: "STUNDENBERICHT",
    subtitle: "Stundenbericht für den Monat {month}",
    activityDescription: "Tätigkeitsbeschreibung",
    hours: "Stunden",
    bruto: "Brutto",
    performance: "Performance",
    totalHours: "Gesamtstunden {month}:",
  },
};

const MONTH_NAMES: Partial<Record<Language, Record<string, string>>> = {
  en: {
    janeiro: "January", fevereiro: "February", março: "March", abril: "April",
    maio: "May", junho: "June", julho: "July", agosto: "August",
    setembro: "September", outubro: "October", novembro: "November", dezembro: "December",
  },
  de: {
    janeiro: "Januar", fevereiro: "Februar", março: "März", abril: "April",
    maio: "Mai", junho: "Juni", julho: "Juli", agosto: "August",
    setembro: "September", outubro: "Oktober", novembro: "November", dezembro: "Dezember",
  },
};

export function translateMonthLabel(monthLabel: string, language: Language): string {
  const monthNames = MONTH_NAMES[language];
  if (!monthNames) return monthLabel;
  const [name, ...rest] = monthLabel.split("/");
  const translated = monthNames[name.trim().toLowerCase()];
  return translated ? [translated, ...rest].join("/") : monthLabel;
}
