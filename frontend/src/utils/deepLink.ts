import type { AppView } from "../appView";

/** Base do título da aba — a mesma do `index.html`. */
export const BASE_TITLE = "Geração de Relatório de Horas";

/** Título com o contador de pendências: revisões que esperam a pessoa +
 * aprovações que esperam o gerente (do `summary` de `/my-reviews/summary`). */
export function titleWithPending(summary: { to_review: number; awaiting_approval: number | null } | null): string {
  const pending = (summary?.to_review ?? 0) + (summary?.awaiting_approval ?? 0);
  return pending > 0 ? `(${pending}) ${BASE_TITLE}` : BASE_TITLE;
}

const VIEWS: readonly string[] = [
  "report",
  "management",
  "diagnostics",
  "dashboard",
  "history",
  "analytics",
  "analytics-chat",
  "auto-generation",
  "my-reviews",
];

/** Lê o deep link dos avisos por e-mail (`?view=…&report=…`) — view
 * desconhecida ou ausente vira `null` (o app decide o padrão). */
export function parseDeepLink(search: string): { view: AppView | null; reportId: string | null } {
  const params = new URLSearchParams(search);
  const rawView = params.get("view");
  const reportId = (params.get("report") || "").trim() || null;
  return { view: rawView && VIEWS.includes(rawView) ? (rawView as AppView) : null, reportId };
}
