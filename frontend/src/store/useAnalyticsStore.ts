import { create } from "zustand";

export type HoursBreakdownRow = { hours: number } & Record<string, string | number>;

export type GenerationFormatStats = { format: string; avg_duration_ms: number | null; count: number };

export type GenerationStats = {
  total: number;
  failed: number;
  failure_rate: number | null;
  avg_duration_ms: number | null;
  by_format: GenerationFormatStats[];
};

export type ReportsOverTimeRow = { period: string; count: number };

export type TopCreatorRow = { login: string; name: string; reports: number };

export type AnalyticsSummary = {
  totals: { reports: number; versions: number; artifacts: number };
  hours_by_competence: { competence_label: string; hours: number }[];
  hours_by_group: { group_name: string; hours: number }[];
  hours_by_project: { project_name: string; hours: number }[];
  generation: GenerationStats;
  reports_over_time: ReportsOverTimeRow[];
  top_creators: TopCreatorRow[];
};

interface AnalyticsState {
  summary: AnalyticsSummary | null;
  loading: boolean;
  error: string;
  loadSummary: () => Promise<void>;
}

export const useAnalyticsStore = create<AnalyticsState>((set) => ({
  summary: null,
  loading: false,
  error: "",

  loadSummary: async () => {
    set({ loading: true, error: "" });
    try {
      const res = await fetch("/analytics/summary");
      if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
      const data: AnalyticsSummary = await res.json();
      set({ summary: data });
    } catch {
      set({ error: "Não consegui carregar as métricas. Tenta de novo em instantes." });
    } finally {
      set({ loading: false });
    }
  },
}));
