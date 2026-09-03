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

export type ProjectSendStatusRow = {
  month: string;
  project_id: string;
  project_name: string;
  client: string;
  sent: boolean;
};

type KpisResponse = {
  months: MonthRow[];
  cost_centers: string[];
  available_projects: string[];
  available_clients: string[];
  project_codes: Record<string, string>;
  project_clients: Record<string, string>;
  nonbillable_breakdown: NonbillablePackageRow[];
  project_send_status: ProjectSendStatusRow[];
};

export const ALL_COST_CENTERS = ["CAD", "CAE"];
// sentinela pro período "últimos 12 meses corridos" (padrão) — qualquer outro
// valor de `period` é tratado como um ano fechado (Jan-Dez), ex: "2026".
export const ROLLING_PERIOD = "rolling";

interface ManagementState {
  rows: MonthRow[] | null;
  nonbillableBreakdown: NonbillablePackageRow[];
  projectSendStatus: ProjectSendStatusRow[];
  availableProjects: string[];
  availableClients: string[];
  // nome do projeto -> código (prefixo do pacote de trabalho, ex: "1564" em
  // "1564.1.1-001 MBB_CAD_ACCELO..."), só pra prefixar a opção no dropdown
  // de Projeto — o Projectile não tem coluna de código separada.
  projectCodes: Record<string, string>;
  // nome do projeto -> cliente, pro dropdown de Projeto só listar quem
  // pertence ao(s) cliente(s) marcado(s) no filtro de Cliente.
  projectClients: Record<string, string>;
  error: string;
  loaded: boolean;
  refreshing: boolean;
  _inFlight: boolean;
  _pending: boolean;
  // captura as opções de Cliente/Projeto só na 1ª busca (sem filtro nenhum
  // aplicado ainda, então é o conjunto mais completo possível) e nunca mais
  // sobrescreve — aplicar um filtro não deve fazer os outros itens da lista
  // sumirem dos dropdowns, só mudar o que entra nas somas da tela.
  _optionsCaptured: boolean;

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
  resetFilters: () => void;
}

export function round2(n: number): number {
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
  projectSendStatus: [],
  availableProjects: [],
  availableClients: [],
  projectCodes: {},
  projectClients: {},
  error: "",
  loaded: false,
  refreshing: false,
  _inFlight: false,
  _pending: false,
  _optionsCaptured: false,
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
        projectSendStatus: data.project_send_status,
        // só grava as opções na 1ª vez (ver `_optionsCaptured`) — buscas
        // seguintes (com filtro aplicado) trazem um recorte menor, que não
        // deve substituir a lista cheia já mostrada nos dropdowns.
        ...(get()._optionsCaptured
          ? {}
          : {
              availableProjects: data.available_projects,
              availableClients: data.available_clients,
              projectCodes: data.project_codes,
              projectClients: data.project_clients,
              _optionsCaptured: true,
            }),
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
    // projetos selecionados que não pertencem mais a nenhum dos clientes
    // marcados saem do filtro — senão ficaria um projeto de outro cliente
    // aplicado escondido, já que o dropdown de Projeto passa a só listar
    // quem pertence ao(s) cliente(s) escolhido(s) (ver ManagementFilters).
    const { projects, projectClients } = get();
    const nextProjects =
      clients.length === 0 ? projects : projects.filter((name) => clients.includes(projectClients[name]));
    set({ clients, projects: nextProjects });
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
  resetFilters: () => {
    set({
      period: ROLLING_PERIOD,
      selectedMonths: [],
      costCenters: ALL_COST_CENTERS,
      clients: [],
      projects: [],
    });
    get().load(true);
  },
}));
