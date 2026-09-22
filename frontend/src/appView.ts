export type AppView = "report" | "management" | "diagnostics" | "dashboard";

export const VIEW_TITLES: Record<AppView, string> = {
  report: "Geração de Relatório de Horas",
  management: "Painel de Gerência",
  diagnostics: "Diagnóstico de relatórios",
  dashboard: "Dashboard de horas",
};
