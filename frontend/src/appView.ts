export type AppView =
  | "report"
  | "management"
  | "diagnostics"
  | "dashboard"
  | "history"
  | "analytics"
  | "analytics-chat"
  | "auto-generation"
  | "my-reviews";

export const VIEW_TITLES: Record<AppView, string> = {
  report: "Geração de Relatório de Horas",
  management: "Painel de Gerência",
  diagnostics: "Diagnóstico de relatórios",
  dashboard: "Dashboard de horas",
  history: "Histórico de relatórios",
  analytics: "Analytics relatórios",
  "analytics-chat": "Chat analítico",
  "auto-generation": "Geração automática",
  "my-reviews": "Minhas revisões",
};

/** Quem vê cada tela: "all" = todo mundo logado; "coordinator" = gerente ou coordenador; "manager" = só gerente.
 * Só controla o menu e a paleta de comandos — o backend barra por conta própria. */
export type NavAccess = "all" | "coordinator" | "manager";

export const VIEW_ACCESS: Record<AppView, NavAccess> = {
  report: "all",
  dashboard: "all",
  management: "manager",
  diagnostics: "coordinator",
  analytics: "manager",
  history: "all",
  "analytics-chat": "manager",
  "auto-generation": "manager",
  "my-reviews": "all",
};

/** Ordem das telas no menu lateral e na paleta de comandos. */
export const VIEW_ORDER: AppView[] = [
  "report",
  "dashboard",
  "management",
  "diagnostics",
  "analytics",
  "history",
  "analytics-chat",
  "auto-generation",
  "my-reviews",
];
