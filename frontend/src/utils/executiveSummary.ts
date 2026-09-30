export type SummarySource = "claude" | "automatico";

export type SummaryFacts = {
  month: string;
  month_label: string;
  worked_hours: number | null;
  billed_hours: number | null;
  performance_pct: number | null;
  nonbillable_hours: number | null;
  nonbillable_pct: number | null;
  elaboration_days: number | null;
  previous_month_label: string | null;
  worked_delta_pct: number | null;
  performance_delta_pts: number | null;
  send: { sent: number; partial: number; none: number; closed: number; total: number; pending_projects: number };
  pending_clients: { client: string; projects: number }[];
};

export type ExecutiveSummary = {
  month: string;
  facts: SummaryFacts;
  text: string;
  source: SummarySource;
  ai_note: string | null;
};

/** De onde veio o texto — a pessoa precisa saber se foi a IA (com os números conferidos) ou o texto automático. */
export function sourceLabel(source: SummarySource): string {
  return source === "claude"
    ? "Redigido pelo Claude; todo número foi conferido contra os dados do Painel."
    : "Texto automático, montado direto dos números do Painel.";
}

/** O texto em parágrafos (o servidor separa o resumo da linha de pendências com linha em branco). */
export function paragraphs(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

/** Busca o resumo de um mês ("AAAA-MM"). Levanta com mensagem pronta pra tela. */
export async function fetchExecutiveSummary(month: string, useAi: boolean): Promise<ExecutiveSummary> {
  const params = new URLSearchParams({ month, use_ai: String(useAi) });
  const res = await fetch(`/management/executive-summary?${params.toString()}`);
  if (res.status === 400) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "Esse mês não tem resumo.");
  }
  if (res.status === 401) throw new Error("Sessão expirada. Entre de novo.");
  if (res.status === 403) throw new Error("Só o gerente gera o resumo do mês.");
  if (!res.ok) throw new Error("Não consegui gerar o resumo agora. Tenta de novo em instantes.");
  return (await res.json()) as ExecutiveSummary;
}
