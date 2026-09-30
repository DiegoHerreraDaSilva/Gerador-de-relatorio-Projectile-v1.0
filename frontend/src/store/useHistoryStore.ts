import { create } from "zustand";

export type ReportSummary = {
  id: string;
  report_number: string;
  scope: string | null;
  competence_label: string;
  project_name_snapshot: string;
  status: string;
  current_version_id: string | null;
  current_version_number: number | null;
  created_by: string;
  created_by_name_snapshot: string;
  created_at: string;
  updated_at: string;
};

export type VersionSummary = {
  id: string;
  report_id: string;
  version_number: number;
  created_by: string;
  created_from: string;
  change_summary: string | null;
  created_at: string;
};

export type SnapshotActivity = { description: string; hours: number | null };
export type SnapshotGroup = { name: string; performance: number; activities: SnapshotActivity[] };
export type SnapshotHeader = {
  project_code: string;
  project_name: string;
  location_date: string;
  month_label: string;
  signer1_name: string;
  signer1_company: string;
  signer2_name: string;
  signer2_company: string;
};

export type VersionDetail = VersionSummary & {
  report_id: string;
  snapshot: {
    data: {
      header: SnapshotHeader;
      groups: SnapshotGroup[];
      pacote_scope: string | null;
      language: string;
      has_chart_bar: boolean;
      has_chart_pie: boolean;
    };
    data_hash: string;
    schema_version: string;
    captured_at: string;
  };
};

export type GenerationSummary = {
  id: string;
  report_id: string;
  report_version_id: string;
  version_number: number;
  format: string;
  requested_by: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  status: "started" | "success" | "failed";
  error_code: string | null;
  error_message: string | null;
};

export type ArtifactSummary = {
  id: string;
  generation_id: string;
  artifact_type: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  sha256: string;
  created_at: string;
  report_version_id: string;
  version_number: number;
};

export type AuditEvent = {
  id: string;
  actor_id: string;
  actor_name_snapshot: string;
  action: string;
  entity_type: string;
  entity_id: string;
  source: string;
  created_at: string;
};

type Paginated<T> = { items: T[]; page: number; page_size: number; total: number };

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
  return res.json();
}

/** `search` = busca geral (Número, Projeto, Competência e Criado por),
 * feita no backend (`GET /reports?q=`) porque a lista é paginada lá. */
export type HistoryFilters = { search: string; status: string };

/** Colunas ordenáveis da lista (o backend valida a mesma lista: `SORT_COLUMNS`). */
export type SortColumn = "numero" | "projeto" | "competencia" | "versao" | "criado_por" | "atualizado";
export type SortState = { column: SortColumn; order: "asc" | "desc" } | null;

/** 1º clique = crescente, 2º = decrescente, 3º = volta à ordem padrão (mais recente primeiro). */
export function nextSort(current: SortState, column: SortColumn): SortState {
  if (!current || current.column !== column) return { column, order: "asc" };
  return current.order === "asc" ? { column, order: "desc" } : null;
}

export type DeleteResult = {
  deleted: { id: string }[];
  not_found: string[];
  files_removed: number;
  files_failed: number;
};

// só a resposta da busca mais recente vale: digitando rápido, uma busca
// antiga que volte depois da nova não pode sobrescrever o resultado
let latestReportsRequest = 0;

interface HistoryState {
  reports: ReportSummary[];
  page: number;
  pageSize: number;
  total: number;
  loading: boolean;
  error: string;

  filters: HistoryFilters;
  setFilter: (key: keyof HistoryFilters, value: string) => void;

  sort: SortState;
  setSort: (column: SortColumn) => void;

  // seleção para apagar (só gerente): ids marcados, inclusive de outras páginas
  checkedIds: string[];
  // "selecionar todos" do filtro inteiro: quantos existem e se o teto do servidor cortou
  checkedAll: { total: number; truncated: boolean } | null;
  toggleChecked: (id: string) => void;
  checkPage: (checked: boolean) => void;
  checkAllMatching: () => Promise<void>;
  clearChecked: () => void;
  deleteChecked: () => Promise<DeleteResult>;

  selectedReportId: string | null;
  selectedReport: ReportSummary | null;
  versions: VersionSummary[];
  generations: GenerationSummary[];
  artifacts: ArtifactSummary[];
  auditEvents: AuditEvent[];
  detailLoading: boolean;
  detailError: string;

  selectedVersionId: string | null;
  selectedVersionDetail: VersionDetail | null;
  versionDetailLoading: boolean;

  loadReports: (page?: number) => Promise<void>;
  selectReport: (reportId: string) => Promise<void>;
  clearSelection: () => void;
  loadVersionDetail: (versionId: string) => Promise<void>;
  closeVersionDetail: () => void;
}

const PAGE_SIZE = 20;

export const useHistoryStore = create<HistoryState>((set, get) => ({
  reports: [],
  page: 1,
  pageSize: PAGE_SIZE,
  total: 0,
  loading: false,
  error: "",

  filters: { search: "", status: "" },
  setFilter: (key, value) => set((s) => ({ filters: { ...s.filters, [key]: value } })),

  sort: null,
  setSort: (column) => {
    set((s) => ({ sort: nextSort(s.sort, column) }));
    void get().loadReports(1);
  },

  checkedIds: [],
  checkedAll: null,
  toggleChecked: (id) =>
    set((s) => ({
      checkedIds: s.checkedIds.includes(id) ? s.checkedIds.filter((x) => x !== id) : [...s.checkedIds, id],
      checkedAll: null,
    })),
  checkPage: (checked) =>
    set((s) => {
      const pageIds = s.reports.map((r) => r.id);
      const others = s.checkedIds.filter((id) => !pageIds.includes(id));
      return { checkedIds: checked ? [...others, ...pageIds] : others, checkedAll: null };
    }),
  checkAllMatching: async () => {
    const { search, status } = get().filters;
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    if (status) params.set("status", status);
    const data = await fetchJson<{ ids: string[]; total: number; truncated: boolean }>(
      `/reports/ids?${params.toString()}`,
    );
    set({ checkedIds: data.ids, checkedAll: { total: data.total, truncated: data.truncated } });
  },
  clearChecked: () => set({ checkedIds: [], checkedAll: null }),
  deleteChecked: async () => {
    const ids = get().checkedIds;
    const result: DeleteResult = { deleted: [], not_found: [], files_removed: 0, files_failed: 0 };
    // o servidor aceita até 200 por chamada
    for (let i = 0; i < ids.length; i += 200) {
      const res = await fetch("/reports", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: ids.slice(i, i + 200) }),
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
      const part = (await res.json()) as DeleteResult;
      result.deleted.push(...part.deleted);
      result.not_found.push(...part.not_found);
      result.files_removed += part.files_removed;
      result.files_failed += part.files_failed;
    }
    const gone = new Set(result.deleted.map((d) => d.id));
    if (get().selectedReportId && gone.has(get().selectedReportId as string)) get().clearSelection();
    set({ checkedIds: [], checkedAll: null });
    await get().loadReports(1);
    return result;
  },

  selectedReportId: null,
  selectedReport: null,
  versions: [],
  generations: [],
  artifacts: [],
  auditEvents: [],
  detailLoading: false,
  detailError: "",

  selectedVersionId: null,
  selectedVersionDetail: null,
  versionDetailLoading: false,

  loadReports: async (page) => {
    const targetPage = page ?? get().page;
    set({ loading: true, error: "" });
    const { search, status } = get().filters;
    const params = new URLSearchParams({ page: String(targetPage), page_size: String(get().pageSize) });
    if (search.trim()) params.set("q", search.trim());
    if (status) params.set("status", status);
    const { sort } = get();
    if (sort) {
      params.set("sort", sort.column);
      params.set("order", sort.order);
    }
    const request = ++latestReportsRequest;
    try {
      const data = await fetchJson<Paginated<ReportSummary>>(`/reports?${params.toString()}`);
      if (request !== latestReportsRequest) return;
      set({ reports: data.items, page: data.page, total: data.total });
    } catch {
      if (request !== latestReportsRequest) return;
      set({ error: "Não consegui carregar o histórico de relatórios. Tenta de novo em instantes." });
    } finally {
      if (request === latestReportsRequest) set({ loading: false });
    }
  },

  selectReport: async (reportId) => {
    set({
      selectedReportId: reportId,
      detailLoading: true,
      detailError: "",
      selectedVersionId: null,
      selectedVersionDetail: null,
    });
    try {
      const [report, versions, generations, artifacts, audit] = await Promise.all([
        fetchJson<ReportSummary>(`/reports/${reportId}`),
        fetchJson<Paginated<VersionSummary>>(`/reports/${reportId}/versions?page_size=100`),
        fetchJson<Paginated<GenerationSummary>>(`/reports/${reportId}/generations?page_size=100`),
        fetchJson<Paginated<ArtifactSummary>>(`/reports/${reportId}/artifacts?page_size=100`),
        fetchJson<Paginated<AuditEvent>>(`/reports/${reportId}/audit?page_size=100`),
      ]);
      set({
        selectedReport: report,
        versions: versions.items,
        generations: generations.items,
        artifacts: artifacts.items,
        auditEvents: audit.items,
      });
    } catch {
      set({ detailError: "Não consegui carregar o detalhe deste relatório. Tenta de novo em instantes." });
    } finally {
      set({ detailLoading: false });
    }
  },

  clearSelection: () =>
    set({
      selectedReportId: null,
      selectedReport: null,
      versions: [],
      generations: [],
      artifacts: [],
      auditEvents: [],
      selectedVersionId: null,
      selectedVersionDetail: null,
    }),

  loadVersionDetail: async (versionId) => {
    const reportId = get().selectedReportId;
    if (!reportId) return;
    set({ selectedVersionId: versionId, versionDetailLoading: true });
    try {
      const detail = await fetchJson<VersionDetail>(`/reports/${reportId}/versions/${versionId}`);
      set({ selectedVersionDetail: detail });
    } catch {
      set({ selectedVersionDetail: null });
    } finally {
      set({ versionDetailLoading: false });
    }
  },

  closeVersionDetail: () => set({ selectedVersionId: null, selectedVersionDetail: null }),
}));
