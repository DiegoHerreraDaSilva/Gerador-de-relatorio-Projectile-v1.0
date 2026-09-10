// Espelha backend/app/generator.py::_LABELS e _MONTH_NAMES_EN — os textos fixos
// do relatório (título, cabeçalhos, Bruto/Performance) precisam aparecer
// traduzidos tanto no preview quanto no arquivo exportado, então as duas
// pontas usam o mesmo dicionário. Qualquer rótulo novo lá precisa ser
// replicado aqui também.
export type Language = "pt" | "en";

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
};

const MONTH_NAMES_EN: Record<string, string> = {
  janeiro: "January", fevereiro: "February", março: "March", abril: "April",
  maio: "May", junho: "June", julho: "July", agosto: "August",
  setembro: "September", outubro: "October", novembro: "November", dezembro: "December",
};

export function translateMonthLabel(monthLabel: string, language: Language): string {
  if (language !== "en") return monthLabel;
  const [name, ...rest] = monthLabel.split("/");
  const translated = MONTH_NAMES_EN[name.trim().toLowerCase()];
  return translated ? [translated, ...rest].join("/") : monthLabel;
}
