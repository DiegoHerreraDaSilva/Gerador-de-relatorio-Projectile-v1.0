import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextSort, useHistoryStore, type ReportSummary } from "../useHistoryStore";

function report(id: string): ReportSummary {
  return {
    id,
    report_number: `SE.${id}`,
    scope: null,
    competence_label: "Agosto/2026",
    project_name_snapshot: "Projeto",
    status: "generated",
    current_version_id: null,
    current_version_number: 1,
    created_by: "ana",
    created_by_name_snapshot: "Ana",
    created_at: "2026-09-01T10:00:00",
    updated_at: "2026-09-01T10:00:00",
  };
}

type Call = { url: string; method: string; body?: unknown };

function mockFetch(handler: (call: Call) => unknown) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const call = { url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined };
      calls.push(call);
      return { ok: true, status: 200, json: async () => handler(call), text: async () => "" };
    }),
  );
  return calls;
}

beforeEach(() => {
  useHistoryStore.setState({
    reports: [report("1"), report("2"), report("3")],
    total: 3,
    sort: null,
    checkedIds: [],
    checkedAll: null,
    selectedReportId: null,
    filters: { search: "", status: "" },
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("ordenação", () => {
  it("1º clique cresce, 2º decresce, 3º volta ao padrão; outra coluna recomeça", () => {
    const a = nextSort(null, "numero");
    expect(a).toEqual({ column: "numero", order: "asc" });
    const b = nextSort(a, "numero");
    expect(b).toEqual({ column: "numero", order: "desc" });
    expect(nextSort(b, "numero")).toBeNull();
    expect(nextSort(b, "projeto")).toEqual({ column: "projeto", order: "asc" });
  });

  it("pede a lista ao servidor com sort e order, sem perder a busca", async () => {
    const calls = mockFetch(() => ({ items: [], page: 1, page_size: 20, total: 0 }));
    useHistoryStore.setState({ filters: { search: " mercedes ", status: "" } });
    useHistoryStore.getState().setSort("versao");
    await vi.waitFor(() => expect(calls.length).toBe(1));
    const params = new URLSearchParams(calls[0].url.split("?")[1]);
    expect(params.get("sort")).toBe("versao");
    expect(params.get("order")).toBe("asc");
    expect(params.get("q")).toBe("mercedes");
  });

  it("sem ordenação escolhida não manda sort (vale o padrão do servidor)", async () => {
    const calls = mockFetch(() => ({ items: [], page: 1, page_size: 20, total: 0 }));
    await useHistoryStore.getState().loadReports(1);
    expect(calls[0].url).not.toContain("sort=");
  });
});

describe("seleção", () => {
  it("marca e desmarca um por um", () => {
    const s = useHistoryStore.getState();
    s.toggleChecked("1");
    s.toggleChecked("2");
    s.toggleChecked("1");
    expect(useHistoryStore.getState().checkedIds).toEqual(["2"]);
  });

  it("marcar a página seleciona os três; desmarcar tira só os da página e preserva os de outras", () => {
    useHistoryStore.setState({ checkedIds: ["outra-pagina"] });
    useHistoryStore.getState().checkPage(true);
    expect(useHistoryStore.getState().checkedIds.sort()).toEqual(["1", "2", "3", "outra-pagina"]);
    useHistoryStore.getState().checkPage(false);
    expect(useHistoryStore.getState().checkedIds).toEqual(["outra-pagina"]);
  });

  it("selecionar todos os resultados busca os ids do filtro inteiro", async () => {
    const calls = mockFetch(() => ({ ids: ["1", "2", "3", "4", "5"], total: 5, truncated: false }));
    useHistoryStore.setState({ filters: { search: "abacate", status: "" } });
    await useHistoryStore.getState().checkAllMatching();
    expect(calls[0].url).toBe("/reports/ids?q=abacate");
    expect(useHistoryStore.getState().checkedIds).toHaveLength(5);
    expect(useHistoryStore.getState().checkedAll).toEqual({ total: 5, truncated: false });
    useHistoryStore.getState().toggleChecked("1"); // mexer na seleção desfaz o "todos"
    expect(useHistoryStore.getState().checkedAll).toBeNull();
  });
});

describe("apagar", () => {
  it("manda DELETE em lotes de 200, limpa a seleção e recarrega a lista", async () => {
    const ids = Array.from({ length: 450 }, (_, i) => `id${i}`);
    const calls = mockFetch((call) => {
      if (call.method === "DELETE") {
        const sent = (call.body as { ids: string[] }).ids;
        return { deleted: sent.map((id) => ({ id })), not_found: [], files_removed: sent.length, files_failed: 0 };
      }
      return { items: [], page: 1, page_size: 20, total: 0 };
    });
    useHistoryStore.setState({ checkedIds: ids });
    const result = await useHistoryStore.getState().deleteChecked();

    const deletes = calls.filter((c) => c.method === "DELETE");
    expect(deletes.map((c) => (c.body as { ids: string[] }).ids.length)).toEqual([200, 200, 50]);
    expect(result.deleted).toHaveLength(450);
    expect(result.files_removed).toBe(450);
    expect(useHistoryStore.getState().checkedIds).toEqual([]);
    expect(calls[calls.length - 1]?.url).toContain("/reports?"); // recarregou a lista
  });

  it("fecha o detalhe se o relatório aberto foi apagado", async () => {
    mockFetch((call) =>
      call.method === "DELETE"
        ? { deleted: [{ id: "1" }], not_found: [], files_removed: 0, files_failed: 0 }
        : { items: [], page: 1, page_size: 20, total: 0 },
    );
    useHistoryStore.setState({ selectedReportId: "1", checkedIds: ["1"] });
    await useHistoryStore.getState().deleteChecked();
    expect(useHistoryStore.getState().selectedReportId).toBeNull();
  });

  it("erro do servidor propaga e mantém a seleção para tentar de novo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 502, text: async () => "falhou" })),
    );
    useHistoryStore.setState({ checkedIds: ["1", "2"] });
    await expect(useHistoryStore.getState().deleteChecked()).rejects.toThrow();
    expect(useHistoryStore.getState().checkedIds).toEqual(["1", "2"]);
  });
});
