import { create } from "zustand";
import type {
  MyHoursBusinessDays,
  MyHoursComparison,
  MyHoursDailyStats,
  MyHoursEntry,
  MyHoursReference,
  MyHoursResponse,
  MonthlyPoint,
} from "../utils/myHours";

export type MyHoursPeriod = "current_month" | "last_3" | "last_6" | "last_12";

/** Separa os motivos de falha porque a ação de saída é diferente em cada um:
 * sessão expirada precisa de login, erro de entrada precisa da mensagem do
 * backend, e falha de rede precisa de "tentar de novo". Uma mensagem genérica
 * única mandava o usuário dar F5 mesmo quando bastava reentrar. */
export type MyHoursErrorKind = "session" | "input" | "network" | "";

const EMPTY_BUSINESS_DAYS: MyHoursBusinessDays = {
  list: [], closed: [], count: 0, closed_count: 0,
  month_total: 0, month_remaining: 0, holidays: [], source: "", note: "",
};

/** Referência ausente por padrão — `source: "none"` e `hours_per_day: null`.
 * Deliberado: não existe caminho de código no frontend que produza 8 h por
 * conta própria, nem no estado inicial nem no skeleton. */
const EMPTY_REFERENCE: MyHoursReference = {
  source: "none", hours_per_weekday: null, hours_per_day: null,
  allows_percentage: false, sample_days: null, window_days: null,
  label: "Sem referência de jornada", divergence_note: null,
};

interface MyHoursState {
  entries: MyHoursEntry[];
  businessDays: MyHoursBusinessDays;
  reference: MyHoursReference;
  expected: { closed: number | null; period: number | null; month: number | null };
  gapDays: string[];
  outlierDays: string[];
  monthlySeries: MonthlyPoint[];
  comparison: MyHoursComparison | null;
  dailyStats: MyHoursDailyStats;
  startDate: string;
  endDate: string;
  today: string;
  fetchedAt: string;

  period: MyHoursPeriod;
  error: string;
  errorKind: MyHoursErrorKind;
  loaded: boolean;
  refreshing: boolean;
  _inFlight: boolean;
  _pending: boolean;

  /** Cross-filter: afeta SÓ a tabela e o esmaecimento das barras, nunca os
   * KPIs. Um filtro que muda a âncora silenciosamente transforma a página
   * numa mentira — quem clica num pacote não espera que o total do período
   * mude embaixo dele. */
  selectedPacote: string | null;
  selectedDate: string | null;

  load: (force?: boolean) => Promise<void>;
  setPeriod: (period: MyHoursPeriod) => void;
  togglePacote: (pacote: string) => void;
  toggleDate: (date: string) => void;
  clearFilters: () => void;
}

export const useMyHoursStore = create<MyHoursState>((set, get) => ({
  entries: [],
  businessDays: EMPTY_BUSINESS_DAYS,
  reference: EMPTY_REFERENCE,
  expected: { closed: null, period: null, month: null },
  gapDays: [],
  outlierDays: [],
  monthlySeries: [],
  comparison: null,
  dailyStats: { p25: null, median: null, p75: null, n: 0, window_days: 0 },
  startDate: "",
  endDate: "",
  today: "",
  fetchedAt: "",

  period: "current_month",
  error: "",
  errorKind: "",
  loaded: false,
  refreshing: false,
  _inFlight: false,
  _pending: false,
  selectedPacote: null,
  selectedDate: null,

  load: async (force = false) => {
    if (get().loaded && !force) return;
    if (get()._inFlight) {
      set({ _pending: true });
      return;
    }
    set({ refreshing: true, _inFlight: true, _pending: false });
    try {
      const res = await fetch(`/my-hours?period=${get().period}`);
      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          set({ error: "Sua sessão expirou. Entre novamente.", errorKind: "session" });
          return;
        }
        if (res.status === 400) {
          const body = await res.json().catch(() => null);
          set({ error: body?.detail || "Período inválido.", errorKind: "input" });
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const data: MyHoursResponse = await res.json();
      set({
        entries: data.entries,
        businessDays: data.business_days,
        reference: data.reference,
        expected: data.expected,
        gapDays: data.gap_days,
        outlierDays: data.outlier_days,
        monthlySeries: data.monthly_series,
        comparison: data.comparison,
        dailyStats: data.daily_stats,
        startDate: data.start_date,
        endDate: data.end_date,
        today: data.today,
        fetchedAt: new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
        loaded: true,
        error: "",
        errorKind: "",
        selectedPacote: null,
        selectedDate: null,
      });
    } catch (e) {
      console.error("[my-hours] falha ao carregar", e);
      set({
        error: "Não consegui carregar suas horas. Tenta de novo em instantes.",
        errorKind: "network",
      });
    } finally {
      set({ refreshing: false, _inFlight: false });
      if (get()._pending) get().load(true);
    }
  },

  // NÃO zera `loaded`: com `loaded: false` a página trocava pelo estado de
  // carregamento inteiro a cada troca de período, e a geometria saltava. O
  // `refreshing` já cobre o feedback, mantendo o dado anterior esmaecido.
  setPeriod: (period) => {
    set({ period });
    get().load(true);
  },

  togglePacote: (pacote) =>
    set((s) => ({ selectedPacote: s.selectedPacote === pacote ? null : pacote })),
  toggleDate: (date) => set((s) => ({ selectedDate: s.selectedDate === date ? null : date })),
  clearFilters: () => set({ selectedPacote: null, selectedDate: null }),
}));
