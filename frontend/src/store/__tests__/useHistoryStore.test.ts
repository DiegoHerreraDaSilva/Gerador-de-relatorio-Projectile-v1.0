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
    trashMode: false,
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

const EMPTY_LIST = { items: [], page: 1, page_size: 20, total: 0 };

describe("mover pra lixeira", () => {
  it("manda DELETE em lotes de 200, devolve os ids movidos, limpa a seleção e recarrega a lista", async () => {
    const ids = Array.from({ length: 450 }, (_, i) => `id${i}`);
    const calls = mockFetch((call) =>
      call.method === "DELETE"
        ? { trashed: (call.body as { ids: string[] }).ids.map((id) => ({ id })), not_found: [] }
        : EMPTY_LIST,
    );
    useHistoryStore.setState({ checkedIds: ids });
    const moved = await useHistoryStore.getState().trashChecked();

    const deletes = calls.filter((c) => c.method === "DELETE");
    expect(deletes.every((c) => c.url === "/reports")).toBe(true);
    expect(deletes.map((c) => (c.body as { ids: string[] }).ids.length)).toEqual([200, 200, 50]);
    expect(moved).toHaveLength(450);
    expect(useHistoryStore.getState().checkedIds).toEqual([]);
    expect(calls[calls.length - 1]?.url).toContain("/reports?");
  });

  it("fecha o detalhe se o relatório aberto foi movido", async () => {
    mockFetch((call) => (call.method === "DELETE" ? { trashed: [{ id: "1" }], not_found: [] } : EMPTY_LIST));
    useHistoryStore.setState({ selectedReportId: "1", checkedIds: ["1"] });
    await useHistoryStore.getState().trashChecked();
    expect(useHistoryStore.getState().selectedReportId).toBeNull();
  });

  it("erro do servidor propaga e mantém a seleção para tentar de novo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 502, text: async () => "falhou" })),
    );
    useHistoryStore.setState({ checkedIds: ["1", "2"] });
    await expect(useHistoryStore.getState().trashChecked()).rejects.toThrow();
    expect(useHistoryStore.getState().checkedIds).toEqual(["1", "2"]);
  });
});

describe("restaurar (inclusive o Desfazer do aviso)", () => {
  it("restaura os ids dados, sem depender da seleção, e recarrega", async () => {
    const calls = mockFetch((call) =>
      call.method === "POST"
        ? { restored: (call.body as { ids: string[] }).ids.map((id) => ({ id })), not_found: [] }
        : EMPTY_LIST,
    );
    useHistoryStore.setState({ checkedIds: ["outro"] });
    const back = await useHistoryStore.getState().restoreIds(["a", "b"]);
    expect(back).toEqual(["a", "b"]);
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("/reports/restore");
    expect(post?.body).toEqual({ ids: ["a", "b"] });
    expect(calls[calls.length - 1]?.url).toContain("/reports?");
  });

  it("sem ids dados, restaura os marcados", async () => {
    const calls = mockFetch((call) =>
      call.method === "POST" ? { restored: [{ id: "x" }], not_found: [] } : EMPTY_LIST,
    );
    useHistoryStore.setState({ checkedIds: ["x"] });
    await useHistoryStore.getState().restoreIds();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ ids: ["x"] });
    expect(useHistoryStore.getState().checkedIds).toEqual([]);
  });
});

describe("apagar definitivamente", () => {
  it("vai pela rota da lixeira, soma os lotes e limpa a seleção", async () => {
    const calls = mockFetch((call) =>
      call.method === "DELETE"
        ? {
            deleted: (call.body as { ids: string[] }).ids.map((id) => ({ id })),
            not_found: [],
            files_removed: 2,
            files_failed: 1,
          }
        : EMPTY_LIST,
    );
    useHistoryStore.setState({ checkedIds: Array.from({ length: 250 }, (_, i) => `id${i}`) });
    const result = await useHistoryStore.getState().purgeChecked();
    expect(calls.filter((c) => c.method === "DELETE").every((c) => c.url === "/reports/trash")).toBe(true);
    expect(result.deleted).toHaveLength(250);
    expect(result.files_removed).toBe(4); // 2 por lote, 2 lotes
    expect(result.files_failed).toBe(2);
    expect(useHistoryStore.getState().checkedIds).toEqual([]);
  });
});

describe("modo lixeira", () => {
  it("entrar na lixeira pede a lista com trash=true e zera seleção e ordem", async () => {
    const calls = mockFetch(() => EMPTY_LIST);
    useHistoryStore.setState({ checkedIds: ["1"], sort: { column: "numero", order: "asc" } });
    useHistoryStore.getState().setTrashMode(true);
    await vi.waitFor(() => expect(calls.length).toBe(1));
    const params = new URLSearchParams(calls[0].url.split("?")[1]);
    expect(params.get("trash")).toBe("true");
    expect(params.get("sort")).toBeNull();
    expect(useHistoryStore.getState().checkedIds).toEqual([]);
  });

  it("sair da lixeira volta à lista normal, sem trash", async () => {
    const calls = mockFetch(() => EMPTY_LIST);
    useHistoryStore.setState({ trashMode: true });
    useHistoryStore.getState().setTrashMode(false);
    await vi.waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].url).not.toContain("trash");
  });

  it("escolher o modo que já está ativo não refaz a busca", () => {
    const calls = mockFetch(() => EMPTY_LIST);
    useHistoryStore.getState().setTrashMode(false);
    expect(calls).toHaveLength(0);
  });

  it("'selecionar todos' na lixeira busca os ids da lixeira", async () => {
    const calls = mockFetch(() => ({ ids: ["1", "2"], total: 2, truncated: false }));
    useHistoryStore.setState({ trashMode: true });
    await useHistoryStore.getState().checkAllMatching();
    expect(calls[0].url).toBe("/reports/ids?trash=true");
  });
});
