import { create } from "zustand";

export type Sample = {
  sample_id: string;
  received_at: string;
  project_id: string;
  project_name: string;
  match_score: number;
  month: string;
  billed_hours: number;
  business_days: number;
  source: "email" | "manual";
  edited: boolean;
  // null = amostra cobre o projeto inteiro; string = cobre só esse pacote de
  // trabalho (lido da marca oculta do .xlsx, ver generator.py/email_ingest.py).
  pacote_scope: string | null;
};

export type SkippedMessage = { message_id: string; received_at: string; reason: string };

export type Project = { id: string; name: string; client: string };

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
  return res.json();
}

interface DiagnosticsState {
  samples: Sample[];
  skipped: SkippedMessage[];
  projects: Project[];
  loaded: boolean;
  projectsLoaded: boolean;
  refreshing: boolean;
  error: string;
  _inFlight: boolean;

  // busca só na primeira vez que a tela é aberta (igual useManagementStore) —
  // sair de "Diagnóstico" e voltar não deve refazer a requisição, já que o
  // componente desmonta ao trocar de view, mas essa store não. `force`
  // ignora esse cache (botão "Atualizar" e depois de editar/apagar/cadastrar
  // uma amostra).
  load: (force?: boolean) => Promise<void>;
  loadProjects: () => Promise<void>;
  setError: (message: string) => void;
}

export const useDiagnosticsStore = create<DiagnosticsState>((set, get) => ({
  samples: [],
  skipped: [],
  projects: [],
  loaded: false,
  projectsLoaded: false,
  refreshing: false,
  error: "",
  _inFlight: false,

  load: async (force = false) => {
    if (get().loaded && !force) return;
    if (get()._inFlight) return;
    set({ refreshing: true, _inFlight: true, error: "" });
    try {
      const data = await fetchJson<{ samples: Sample[]; skipped_messages: SkippedMessage[] }>(
        "/management/kpis/samples"
      );
      set({ samples: data.samples, skipped: data.skipped_messages, loaded: true });
    } catch {
      set({ error: "Não consegui carregar as amostras. Tenta de novo em instantes." });
    } finally {
      set({ refreshing: false, _inFlight: false });
    }
  },

  loadProjects: async () => {
    if (get().projectsLoaded) return;
    try {
      const projects = await fetchJson<Project[]>("/management/projects");
      set({ projects, projectsLoaded: true });
    } catch {
      set({ error: "Não consegui carregar a lista de projetos." });
    }
  },

  setError: (message) => set({ error: message }),
}));
