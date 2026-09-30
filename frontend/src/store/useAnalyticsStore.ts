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

export type GenerationHealth = {
  window_days: number;
  total: number;
  failed: number;
  failure_rate: number | null;
  avg_duration_ms: number | null;
  p95_duration_ms: number | null;
  last_failure: {
    started_at: string;
    format: string;
    error_code: string | null;
    error_message: string | null;
  } | null;
};

export type SystemHealth = {
  generation: GenerationHealth;
  artifacts: { count: number; bytes: number };
  auto_generation: {
    competence: string | null;
    status: string;
    triggered_by: string | null;
    started_at: string | null;
    finished_at: string | null;
    error: string | null;
  } | null;
  skipped_messages: { count: number; last_received_at: string | null; last_reason: string | null };
  checked_at: string;
};

interface AnalyticsState {
  summary: AnalyticsSummary | null;
  health: SystemHealth | null;
  loading: boolean;
  healthLoading: boolean;
  error: string;
  healthError: string;
  loadSummary: () => Promise<void>;
  loadHealth: () => Promise<void>;
}

export const useAnalyticsStore = create<AnalyticsState>((set) => ({
  summary: null,
  health: null,
  loading: false,
  healthLoading: false,
  error: "",
  healthError: "",

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

  loadHealth: async () => {
    set({ healthLoading: true, healthError: "" });
    try {
      const res = await fetch("/analytics/health");
      if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
      const data: SystemHealth = await res.json();
      set({ health: data });
    } catch {
      set({ healthError: "Não consegui carregar a saúde do sistema. Tenta de novo em instantes." });
    } finally {
      set({ healthLoading: false });
    }
  },
}));
