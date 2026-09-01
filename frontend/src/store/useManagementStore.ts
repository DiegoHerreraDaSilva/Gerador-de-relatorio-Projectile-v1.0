import { create } from "zustand";

export type KpiSource = "manual" | "auto" | null;

export type MonthRow = {
  month: string;
  worked_hours: number;
  billed_hours: number | null;
  billed_hours_source: KpiSource;
  perf_hours: number | null;
  perf_kpi_pct: number | null;
  elaboration_days: number | null;
  elaboration_days_source: KpiSource;
  nonbillable_hours: number;
  nonbillable_kpi_pct: number | null;
};

export type NonbillablePackageRow = {
  month: string;
  package: string;
  hours: number;
};

type KpisResponse = {
  months: MonthRow[];
  cost_centers: string[];
  available_projects: string[];
  available_clients: string[];
  nonbillable_breakdown: NonbillablePackageRow[];
};

export const ALL_COST_CENTERS = ["CAD", "CAE"];
// sentinela pro período "últimos 12 meses corridos" (padrão) — qualquer outro
// valor de `period` é tratado como um ano fechado (Jan-Dez), ex: "2026".
export const ROLLING_PERIOD = "rolling";

interface ManagementState {
  rows: MonthRow[] | null;
  nonbillableBreakdown: NonbillablePackageRow[];
  availableProjects: string[];
  availableClients: string[];
  error: string;
  loaded: boolean;
  refreshing: boolean;
  _inFlight: boolean;
  _pending: boolean;

  // filtros — Competência é só de exibição (não refaz a busca, os 12 meses já
  // estão carregados); Centro de Custo/Cliente/Projeto mudam o resultado
  // vindo do banco, então mudá-los força um novo fetch.
  period: string;
  selectedMonths: string[];
  costCenters: string[];
  clients: string[];
  projects: string[];

  // busca os dados só na primeira vez que o painel é aberto — trocar de volta
  // pra "Geração de Relatório" e voltar não deve refazer a requisição, já que
  // o componente desmonta ao trocar de view, mas essa store não. `force`
  // ignora esse cache do FRONTEND (usado pelo botão "Atualizar" e pelos
  // filtros de banco). `bypassBackendCache` também ignora o cache do
  // BACKEND (~15min, por período) — só o botão "Atualizar" deve usar isso;
  // trocar um filtro não precisa pagar o custo de uma busca nova no banco.
  load: (force?: boolean, bypassBackendCache?: boolean) => Promise<void>;
  updateRow: (month: string, patch: Partial<MonthRow>) => void;
  setError: (message: string) => void;
  setSelectedMonths: (months: string[]) => void;
  setCostCenters: (costCenters: string[]) => void;
  setClients: (clients: string[]) => void;
  setProjects: (projects: string[]) => void;
  setPeriod: (period: string) => void;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function buildQuery(
  state: Pick<ManagementState, "period" | "costCenters" | "clients" | "projects">,
  bypassBackendCache: boolean
): string {
  const params = new URLSearchParams({ months: "12" });
  if (state.period !== ROLLING_PERIOD) params.set("year", state.period);
  state.costCenters.forEach((c) => params.append("cost_centers", c));
  state.clients.forEach((c) => params.append("clients", c));
  state.projects.forEach((p) => params.append("projects", p));
  if (bypassBackendCache) params.set("force_refresh", "true");
  return params.toString();
}

export const useManagementStore = create<ManagementState>((set, get) => ({
  rows: null,
  nonbillableBreakdown: [],
  availableProjects: [],
  availableClients: [],
  error: "",
  loaded: false,
  refreshing: false,
  _inFlight: false,
  _pending: false,
  period: ROLLING_PERIOD,
  selectedMonths: [],
  costCenters: ALL_COST_CENTERS,
  clients: [],
  projects: [],

  load: async (force = false, bypassBackendCache = false) => {
    if (get().loaded && !force) return;
    if (get()._inFlight) {
      // já tem uma busca rodando — esse banco é lento (às vezes 1min+), então
      // empilhar mais uma por cima só piora a fila no servidor. Só marca que
      // precisa buscar de novo (com os filtros mais atuais) assim que a atual
      // terminar, em vez de disparar outra em paralelo.
      set({ _pending: true });
      return;
    }
    set({ refreshing: true, _inFlight: true, _pending: false });
    try {
      const query = buildQuery(get(), bypassBackendCache);
      const res = await fetch(`/management/kpis?${query}`);
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const data: KpisResponse = await res.json();
      set({
        rows: data.months,
        nonbillableBreakdown: data.nonbillable_breakdown,
        availableProjects: data.available_projects,
        availableClients: data.available_clients,
        loaded: true,
        error: "",
      });
    } catch {
      set({ error: "Não consegui carregar os dados do painel. Tenta de novo em instantes." });
    } finally {
      set({ refreshing: false, _inFlight: false });
      if (get()._pending) get().load(true);
    }
  },

  updateRow: (month, patch) => {
    set((state) => ({
      rows: (state.rows ?? []).map((r) => {
        if (r.month !== month) return r;
        const next = { ...r, ...patch };
        next.perf_hours = next.billed_hours === null ? null : round2(next.billed_hours - next.worked_hours);
        next.perf_kpi_pct = next.perf_hours === null || next.worked_hours <= 0 ? null : next.perf_hours / next.worked_hours;
        return next;
      }),
    }));
  },

  setError: (message) => set({ error: message }),
  setSelectedMonths: (months) => set({ selectedMonths: months }),
  setCostCenters: (costCenters) => {
    set({ costCenters });
    get().load(true);
  },
  setClients: (clients) => {
    set({ clients });
    get().load(true);
  },
  setProjects: (projects) => {
    set({ projects });
    get().load(true);
  },
  setPeriod: (period) => {
    // muda o conjunto de meses inteiro — uma seleção de Competência antiga
    // (do período anterior) não bate com os meses novos e deixaria a tela
    // vazia sem explicação, então limpa junto.
    set({ period, selectedMonths: [] });
    get().load(true);
  },
}));
