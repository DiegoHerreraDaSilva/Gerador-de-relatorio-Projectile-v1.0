import { create } from "zustand";
import { useAuthStore } from "./useAuthStore";
import { reportTabBundle, useReportStore } from "./useReportStore";
import { isLoadingTabBundle, useReportTabsStore, type AutoTabMeta } from "./useReportTabsStore";
import { draftToEditor, editorToDraft, type AutoDraft } from "../utils/autoDraft";
import { buildGeneratePayload } from "../utils/generatePayload";
import { api, ApiError } from "../utils/autoApi";
import { useMyReviewsStore } from "./useMyReviewsStore";
import type { ReportHeader, RowIssue, WorkPackage } from "../api/types";

/** Aba "Geração automática" (só gerente) + o salvamento no servidor da guia
 * do editor aberta a partir dela. Contrato em
 * `backend/app/api/routers/auto_generation.py`. */

export type AutoStatus =
  | "gerando" | "erro" | "em_revisao" | "revisado" | "devolvido" | "aprovado" | "enviado" | "pulado";

export const EDITABLE_STATUSES: AutoStatus[] = ["em_revisao", "revisado", "devolvido"];
// o revisor edita até mandar pra aprovação; depois disso, só o gerente
export const REVIEWER_EDITABLE_STATUSES: AutoStatus[] = ["em_revisao", "devolvido"];

/** A guia aberta ainda salva no servidor? Depende de quem abriu. */
export function canEditAutoTab(auto: Pick<AutoTabMeta, "status" | "role">): boolean {
  const allowed = auto.role === "reviewer" ? REVIEWER_EDITABLE_STATUSES : EDITABLE_STATUSES;
  return allowed.includes(auto.status as AutoStatus);
}

/** Rotas do relatório: as do gerente ou as de "Minhas revisões". */
function reportUrl(role: AutoTabMeta["role"], reportId: string): string {
  return role === "reviewer" ? `/my-reviews/${reportId}` : `/auto-generation/reports/${reportId}`;
}

export type ReviewComment = { action: "submitted" | "returned"; comment: string | null; actor_name: string | null; created_at: string };

export type Reviewer = { login: string; name: string };

export type SendDefaults = {
  to: string[]; cc: string[]; subject: string; message: string; files: string[]; sender: string;
  // o Diagnóstico só conta "Enviado" pra remetentes de ALBERTO_EMAIL
  counts_in_diagnostics: boolean;
};

export type SendRequest = { to: string[]; cc: string[]; subject: string; message: string; formats?: Array<"xlsx" | "pdf"> };

export type AutoBadges = {
  packages?: number;
  package_ids?: string[];
  package_names?: string[];
  // modo em que o rascunho foi GERADO (a configuração pode ter mudado depois)
  mode?: "projeto" | "pacote";
  numbers?: string[];
  suggested?: string[];
  memory_applied?: boolean;
  issues?: number;
  hours_changed?: boolean;
  missing_hours?: number;
  skip_reason?: string;
};

export type AutoItem = {
  id: string;
  competence: string;
  project_id: string;
  family_key: string;
  project_name: string;
  client: string | null;
  status: AutoStatus;
  reviewer_login: string | null;
  reviewer_name: string | null;
  draft_version: number;
  source_hours: number | null;
  hours_now: number | null;
  approved_by: string | null;
  approved_at: string | null;
  sent_by: string | null;
  sent_at: string | null;
  // último envio ao cliente (só em "enviado")
  last_sent: { to: string[]; cc: string[]; actor_name: string | null; created_at: string } | null;
  error: string | null;
  updated_at: string;
  badges: AutoBadges;
  // última observação do revisor ("submitted") ou da devolução ("returned")
  last_comment: ReviewComment | null;
  // configuração individual do projeto (só o que difere do padrão) e o que vale de fato
  rule: ProjectRule;
  effective: EffectiveConfig;
};

/** O que um projeto pode ter diferente do padrão — guardado pela família
 * (vale nos meses seguintes do mesmo trabalho). Ausente = herda. */
export type ProjectRule = Partial<{
  enabled: boolean;
  mode: "projeto" | "pacote";
  signer1_name: string;
  signer1_company: string;
  signer2_name: string;
  signer2_company: string;
  include_performance: boolean;
  formats: Array<"xlsx" | "pdf">;
  // revisor com que o rascunho já nasce (o nome o backend preenche pelo Projectile)
  reviewer_login: string;
  reviewer_name: string;
}>;

export type EffectiveConfig = Required<ProjectRule> & {
  location?: string;
  number_pattern?: string;
  // o formato em linguagem de gente ("SE.##.###", `#` = dígito); null = regra escrita à mão
  number_model?: string | null;
};

export type AutoRun = {
  id: string;
  competence: string;
  status: "running" | "done" | "failed";
  triggered_by: string | null;
  started_at: string;
  finished_at: string | null;
  counts_json: Record<string, number> | null;
  error: string | null;
};

export type NewProject = { project_id: string; name: string; client: string; hours: number };

export type CompetenceView = {
  competence: string;
  month_label: string;
  run: AutoRun | null;
  items: AutoItem[];
  counts: Record<string, number>;
  new_projects: NewProject[];
};

export type PreviewProject = NewProject & {
  family_key: string;
  family_label: string;
  planned: "sera_gerado" | "fechado" | "desativado";
  mode: "pacote" | "projeto";
  // quem revisou o último relatório aprovado (vale se a configuração não tiver revisor)
  remembered_reviewer: Reviewer | null;
  rule: ProjectRule;
  effective: EffectiveConfig;
};

export type Preview = { competence: string; month_label: string; projects: PreviewProject[] };

export type AutoConfig = {
  defaults: Record<string, unknown>;
  config: Record<string, unknown>;
  effective: Record<string, unknown>;
  rules: Array<{ family_key: string; label: string; config: Record<string, unknown> }>;
};

export type SaveState = "saved" | "dirty" | "saving" | "conflict" | "error";

const SAVE_DEBOUNCE_MS = 2500;

export { ApiError, errorList } from "../utils/autoApi";

interface AutoGenerationState {
  current: string | null;
  previous: string | null;
  runs: AutoRun[];
  selected: string | null;
  view: CompetenceView | null;
  preview: Preview | null;
  loading: boolean;
  error: string;
  busy: Record<string, boolean>;
  config: AutoConfig | null;
  saveState: Record<string, SaveState>;
  reviewers: Reviewer[] | null;
  reviewersError: string;
  _loadedForLogin: string | null;

  init: () => Promise<void>;
  select: (competence: string) => Promise<void>;
  refresh: () => Promise<void>;
  run: (projectIds?: string[]) => Promise<void>;
  setNumber: (item: AutoItem, packageId: string, code: string) => Promise<void>;
  action: (item: AutoItem, action: "skip" | "reopen" | "regenerate", comment?: string) => Promise<void>;
  openInEditor: (itemId: string, role?: "manager" | "reviewer") => Promise<void>;
  flushSave: (reportId: string) => Promise<boolean>;
  approve: (reportId: string) => Promise<{ warnings: string[] }>;
  loadReviewers: () => Promise<void>;
  assignReviewer: (item: AutoItem, login: string | null) => Promise<void>;
  returnToReviewer: (reportId: string, comment: string) => Promise<void>;
  submitReview: (reportId: string, comment: string) => Promise<void>;
  loadSendDefaults: (reportId: string) => Promise<SendDefaults>;
  sendReport: (item: AutoItem, body: SendRequest) => Promise<void>;
  sendCombined: (items: AutoItem[], body: SendRequest) => Promise<void>;
  loadConfig: () => Promise<void>;
  saveConfig: (config: Record<string, unknown>) => Promise<void>;
  saveRule: (familyKey: string, config: Record<string, unknown> | null) => Promise<void>;
}

let pollTimer: ReturnType<typeof setTimeout> | null = null;
const saveTimers: Record<string, ReturnType<typeof setTimeout>> = {};
const savingNow: Record<string, Promise<boolean> | undefined> = {};

function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(() => {
    pollTimer = null;
    void useAutoGenerationStore.getState().refresh();
  }, 2000);
}

/** Estado do editor de uma guia: a ativa está viva em `useReportStore`; as
 * outras só existem como bundle serializado. */
function tabContent(tabId: string): {
  packages: WorkPackage[]; header: ReportHeader; includePerformance: boolean; issues: RowIssue[];
} | null {
  const tabs = useReportTabsStore.getState();
  if (tabs.activeTabId === tabId) {
    const s = useReportStore.getState();
    return { packages: s.packages, header: s.header, includePerformance: s.includePerformanceInExport, issues: s.currentIssues };
  }
  const bundle = tabs.bundles[tabId];
  if (!bundle) return null;
  try {
    const parsed = JSON.parse(bundle);
    return {
      packages: parsed.packages, header: parsed.header, includePerformance: parsed.includePerformanceInExport,
      issues: parsed.currentIssues ?? [],
    };
  } catch {
    return null;
  }
}

function autoTabFor(reportId: string) {
  return useReportTabsStore.getState().tabs.find((t) => t.auto?.reportId === reportId);
}

export const useAutoGenerationStore = create<AutoGenerationState>((set, get) => ({
  current: null,
  previous: null,
  runs: [],
  selected: null,
  view: null,
  preview: null,
  loading: false,
  error: "",
  busy: {},
  config: null,
  saveState: {},
  reviewers: null,
  reviewersError: "",
  _loadedForLogin: null,

  init: async () => {
    const login = useAuthStore.getState().user?.login ?? null;
    if (get()._loadedForLogin !== login) {
      set({
        current: null, previous: null, runs: [], selected: null, view: null, preview: null, config: null,
        reviewers: null, reviewersError: "", _loadedForLogin: login,
      });
    }
    if (!get().reviewers) void get().loadReviewers();
    set({ loading: true, error: "" });
    try {
      const data = await api<{ current: string; previous: string; runs: AutoRun[] }>("/auto-generation/competences");
      if (get()._loadedForLogin !== login) return;
      set({ current: data.current, previous: data.previous, runs: data.runs });
      await get().select(get().selected ?? data.previous);
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e), loading: false });
    }
  },

  select: async (competence) => {
    set({ selected: competence, view: null, preview: null, loading: true, error: "" });
    await get().refresh();
  },

  refresh: async () => {
    const competence = get().selected;
    const login = get()._loadedForLogin;
    if (!competence) return;
    try {
      const view = await api<CompetenceView>(`/auto-generation/competences/${competence}`);
      if (get().selected !== competence || get()._loadedForLogin !== login) return;
      let preview: Preview | null = null;
      if (!view.run && competence === get().current) {
        preview = await api<Preview>(`/auto-generation/competences/${competence}/preview`);
      }
      if (get().selected !== competence) return;
      set({ view, preview, loading: false, error: "" });
      if (view.run?.status === "running") schedulePoll();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e), loading: false });
    }
  },

  run: async (projectIds) => {
    const competence = get().selected;
    if (!competence) return;
    set({ error: "" });
    try {
      await api(`/auto-generation/competences/${competence}/run`, {
        method: "POST",
        body: JSON.stringify({ project_ids: projectIds ?? [] }),
      });
      const runs = await api<{ runs: AutoRun[] }>("/auto-generation/competences");
      set({ runs: runs.runs });
      await get().refresh();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    }
  },

  setNumber: async (item, packageId, code) => {
    set((s) => ({ busy: { ...s.busy, [item.id]: true }, error: "" }));
    try {
      // relatório aberto no editor: o número é digitado lá (a lista bloqueia
      // o campo nesse caso), senão o próximo salvamento da guia
      // sobrescreveria o número daqui
      if (autoTabFor(item.id)) throw new Error("Esse relatório está aberto no editor — digite o número lá.");
      await api(`/auto-generation/reports/${item.id}/numbers`, {
        method: "PATCH",
        body: JSON.stringify({ numbers: { [packageId]: code }, draft_version: item.draft_version }),
      });
      await get().refresh();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
      await get().refresh();
    } finally {
      set((s) => ({ busy: { ...s.busy, [item.id]: false } }));
    }
  },

  action: async (item, action, comment = "") => {
    set((s) => ({ busy: { ...s.busy, [item.id]: true }, error: "" }));
    try {
      await api(`/auto-generation/reports/${item.id}/${action}`, {
        method: "POST",
        body: action === "regenerate" ? undefined : JSON.stringify({ comment }),
      });
      // o rascunho mudou no servidor: a guia aberta dele ficou velha
      if (action === "regenerate" || action === "reopen") {
        const tab = autoTabFor(item.id);
        if (tab) useReportTabsStore.getState().closeTab(tab.id);
      }
      await get().refresh();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set((s) => ({ busy: { ...s.busy, [item.id]: false } }));
    }
  },

  openInEditor: async (itemId, role = "manager") => {
    const existing = autoTabFor(itemId);
    if (existing && (existing.auto?.role ?? "manager") === role) {
      useReportTabsStore.getState().switchTab(existing.id);
      return;
    }
    // aberto no outro papel (gerente que também é o revisor): salva e reabre
    if (existing) {
      await get().flushSave(itemId);
      useReportTabsStore.getState().closeTab(existing.id);
    }
    const detail = await api<{
      id: string; competence: string; status: AutoStatus; draft_version: number; project_name: string;
      reviewer_name: string | null; draft: AutoDraft | null;
      events: Array<{ action: string; comment: string | null }>;
    }>(reportUrl(role, itemId));
    if (!detail.draft) throw new Error("Esse relatório não tem rascunho (gere de novo).");
    const editor = draftToEditor(detail.draft);
    const lastReturn = [...(detail.events ?? [])].reverse().find((e) => e.action === "returned");
    const meta: AutoTabMeta = {
      reportId: detail.id,
      draftVersion: detail.draft_version,
      competence: detail.competence,
      status: detail.status,
      formats: editor.formats,
      extras: editor.extras,
      role,
      reviewerName: detail.reviewer_name,
      returnComment: detail.status === "devolvido" ? lastReturn?.comment ?? null : null,
    };
    useReportTabsStore.getState().openAutoTab(
      meta,
      detail.project_name,
      reportTabBundle(editor.packages, editor.header, editor.includePerformance, editor.issues),
    );
    set((s) => ({ saveState: { ...s.saveState, [detail.id]: "saved" } }));
  },

  flushSave: async (reportId) => {
    if (saveTimers[reportId]) {
      clearTimeout(saveTimers[reportId]);
      delete saveTimers[reportId];
    }
    if (savingNow[reportId]) await savingNow[reportId];
    if (get().saveState[reportId] !== "dirty") return get().saveState[reportId] !== "conflict";
    const tab = autoTabFor(reportId);
    const content = tab ? tabContent(tab.id) : null;
    if (!tab?.auto || !content) return false;
    const auto = tab.auto;
    const draft = editorToDraft(
      content.packages, content.header, content.includePerformance, auto.formats, auto.extras, content.issues,
    );
    set((s) => ({ saveState: { ...s.saveState, [reportId]: "saving" } }));
    const promise = (async () => {
      try {
        const res = await api<{ draft_version: number }>(`${reportUrl(auto.role, reportId)}/draft`, {
          method: "PUT",
          body: JSON.stringify({ draft, draft_version: auto.draftVersion }),
        });
        useReportTabsStore.getState().updateAutoMeta(reportId, { draftVersion: res.draft_version });
        // editou de novo enquanto salvava: continua sujo
        set((s) => ({ saveState: { ...s.saveState, [reportId]: s.saveState[reportId] === "saving" ? "saved" : s.saveState[reportId] } }));
        return true;
      } catch (e) {
        const conflict = e instanceof ApiError && e.status === 409;
        set((s) => ({ saveState: { ...s.saveState, [reportId]: conflict ? "conflict" : "error" } }));
        return false;
      } finally {
        delete savingNow[reportId];
      }
    })();
    savingNow[reportId] = promise;
    return promise;
  },

  approve: async (reportId) => {
    const tab = autoTabFor(reportId);
    if (!tab?.auto || useReportTabsStore.getState().activeTabId !== tab.id) {
      throw new Error("Abra o relatório no editor pra aprovar.");
    }
    const saved = await get().flushSave(reportId);
    if (!saved) throw new Error("O rascunho não foi salvo no servidor — resolva isso antes de aprovar.");
    const live = useReportStore.getState();
    const auto = autoTabFor(reportId)!.auto!;
    const payload = buildGeneratePayload(live.packages, live.header, auto.formats);
    const res = await api<{ status: AutoStatus; warnings: string[] }>(`/auto-generation/reports/${reportId}/approve`, {
      method: "POST",
      body: JSON.stringify({ payload, draft_version: auto.draftVersion }),
    });
    useReportTabsStore.getState().updateAutoMeta(reportId, { status: res.status });
    void get().refresh();
    useMyReviewsStore.getState().refreshAll();
    return { warnings: res.warnings };
  },

  loadReviewers: async () => {
    try {
      const data = await api<{ reviewers: Reviewer[] }>("/auto-generation/reviewers");
      set({ reviewers: data.reviewers, reviewersError: "" });
    } catch (e) {
      set({ reviewersError: e instanceof Error ? e.message : String(e) });
    }
  },

  assignReviewer: async (item, login) => {
    set((s) => ({ busy: { ...s.busy, [item.id]: true }, error: "" }));
    try {
      const res = await api<{ status: AutoStatus; reviewer_name: string | null }>(`/auto-generation/reports/${item.id}/reviewer`, {
        method: "PUT",
        body: JSON.stringify({ login }),
      });
      useReportTabsStore.getState().updateAutoMeta(item.id, { status: res.status, reviewerName: res.reviewer_name });
      await get().refresh();
      useMyReviewsStore.getState().refreshAll();
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) });
    } finally {
      set((s) => ({ busy: { ...s.busy, [item.id]: false } }));
    }
  },

  returnToReviewer: async (reportId, comment) => {
    await api(`/auto-generation/reports/${reportId}/return`, { method: "POST", body: JSON.stringify({ comment }) });
    useReportTabsStore.getState().updateAutoMeta(reportId, { status: "devolvido", returnComment: comment });
    void get().refresh();
    useMyReviewsStore.getState().refreshAll();
  },

  loadSendDefaults: (reportId) => api<SendDefaults>(`/auto-generation/reports/${reportId}/send`),

  sendReport: async (item, body) => {
    await api(`/auto-generation/reports/${item.id}/send`, { method: "POST", body: JSON.stringify(body) });
    useReportTabsStore.getState().updateAutoMeta(item.id, { status: "enviado" });
    await get().refresh();
  },

  sendCombined: async (items, body) => {
    await api("/auto-generation/send", {
      method: "POST",
      body: JSON.stringify({ ...body, report_ids: items.map((i) => i.id) }),
    });
    for (const item of items) useReportTabsStore.getState().updateAutoMeta(item.id, { status: "enviado" });
    await get().refresh();
  },

  submitReview: async (reportId, comment) => {
    const saved = await get().flushSave(reportId);
    if (!saved) throw new Error("O rascunho não foi salvo no servidor — resolva isso antes de mandar pra aprovação.");
    const res = await api<{ status: AutoStatus }>(`/my-reviews/${reportId}/submit`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    });
    useReportTabsStore.getState().updateAutoMeta(reportId, { status: res.status, returnComment: null });
    useMyReviewsStore.getState().refreshAll();
  },

  loadConfig: async () => {
    const config = await api<AutoConfig>("/auto-generation/config");
    set({ config });
  },

  saveConfig: async (config) => {
    await api("/auto-generation/config", { method: "PUT", body: JSON.stringify(config) });
    await get().loadConfig();
  },

  saveRule: async (familyKey, config) => {
    const url = `/auto-generation/rules/${encodeURIComponent(familyKey)}`;
    if (config && Object.keys(config).length) await api(url, { method: "PUT", body: JSON.stringify(config) });
    else await api(url, { method: "DELETE" });
    await get().refresh();
  },
}));

/** Edição na guia automática ativa → marca "não salvo" e salva no servidor
 * depois de uma pausa. Troca/abertura de guia não conta como edição. */
useReportStore.subscribe(() => {
  if (isLoadingTabBundle()) return;
  const tabs = useReportTabsStore.getState();
  const auto = tabs.tabs.find((t) => t.id === tabs.activeTabId)?.auto;
  if (!auto || !canEditAutoTab(auto)) return;
  const reportId = auto.reportId;
  const store = useAutoGenerationStore.getState();
  if (store.saveState[reportId] === "conflict") return;
  useAutoGenerationStore.setState((s) => ({ saveState: { ...s.saveState, [reportId]: "dirty" } }));
  if (saveTimers[reportId]) clearTimeout(saveTimers[reportId]);
  saveTimers[reportId] = setTimeout(() => {
    delete saveTimers[reportId];
    void useAutoGenerationStore.getState().flushSave(reportId);
  }, SAVE_DEBOUNCE_MS);
});

/** Outro usuário no mesmo navegador: as guias automáticas (rascunhos do
 * servidor) do anterior somem. */
useAuthStore.subscribe((state, prev) => {
  if (state.user?.login !== prev.user?.login) useReportTabsStore.getState().closeAutoTabs();
});
