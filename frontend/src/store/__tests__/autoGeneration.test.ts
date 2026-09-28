import { beforeEach, describe, expect, it, vi } from "vitest";
import { draftToEditor, editorToDraft, type AutoDraft } from "../../utils/autoDraft";

function installMemoryLocalStorage() {
  let store: Record<string, string> = {};
  (globalThis as unknown as { localStorage: Storage }).localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      store = {};
    },
    key: () => null,
    get length() {
      return Object.keys(store).length;
    },
  } as Storage;
}

const DRAFT: AutoDraft = {
  schema: 1,
  mode: "pacote",
  header: {
    location_date: "Santo André, 01.09.2026",
    month_label: "Agosto/2026",
    signer1_name: "Diego",
    signer1_company: "Schwaben Engineering",
    signer2_name: "",
    signer2_company: "Mercedes-Benz do Brasil",
  },
  include_performance: false,
  formats: ["xlsx", "pdf"],
  packages: [
    {
      id: "pkg1",
      key: "1546.1-001 Estribo 08.2026",
      source_key: "1546.1-001 estribo",
      project_code: "",
      suggested_code: "SE.26.053",
      project_name: "1546.1-001 Estribo 08.2026",
      pacote_scope: "1546.1-001 Estribo 08.2026",
      language: "pt",
      chart_bar: true,
      chart_pie: false,
      groups: [
        {
          id: "g1",
          source_key: "modelagem",
          name: "Modelagem 3D",
          performance: 0.9,
          activities: [
            { id: "a1", source_key: "ajuste de suporte", description: "Ajuste do suporte", hours: 8 },
            { id: "a2", source_key: null, description: "Linha sem horas", hours: null },
          ],
        },
      ],
    },
  ],
  issues: [{ row: 3, reason: "descricao_vazia", message: "Sem descrição", raw_hours: 4.5, raw_description: null }],
  memory_applied: true,
};

describe("rascunho da geração automática ↔ editor", () => {
  it("ida e volta preserva conteúdo, chaves da memória e o que o editor não mostra", () => {
    const editor = draftToEditor(DRAFT);
    expect(editor.packages[0].projectName).toBe("1546.1-001 Estribo 08.2026");
    expect(editor.packages[0].chartBar).toBe(true);
    expect(editor.packages[0].groups[0].activities[1].extra).toBe(true); // sem horas = linha manual
    expect(editor.header.signer1Name).toBe("Diego");
    const back = editorToDraft(editor.packages, editor.header, editor.includePerformance, editor.formats, editor.extras, editor.issues);
    expect(back).toEqual(DRAFT);
  });

  it("grupo criado no editor volta sem chave de memória", () => {
    const editor = draftToEditor(DRAFT);
    editor.packages[0].groups.push({ id: "novo", name: "Grupo novo", performance: 1, activities: [] });
    const back = editorToDraft(editor.packages, editor.header, false, ["xlsx"], editor.extras);
    expect(back.packages[0].groups[1]).toEqual({ id: "novo", source_key: null, name: "Grupo novo", performance: 1, activities: [] });
  });
});

describe("guia da geração automática", () => {
  beforeEach(() => {
    vi.resetModules();
    installMemoryLocalStorage();
  });

  const meta = () => ({
    reportId: "R1",
    draftVersion: 3,
    competence: "2026-08",
    status: "em_revisao",
    formats: ["xlsx" as const],
    extras: draftToEditor(DRAFT).extras,
  });

  it("abre com o rascunho e nunca vai pro localStorage", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { useReportStore, reportTabBundle } = await import("../useReportStore");
    const editor = draftToEditor(DRAFT);
    useReportTabsStore.getState().openAutoTab(meta(), "Estribo", reportTabBundle(editor.packages, editor.header, false));

    expect(useReportStore.getState().packages[0].id).toBe("pkg1");
    expect(useReportStore.getState().showImportCard).toBe(false);
    const saved = JSON.parse(localStorage.getItem("relatorio-horas:tabs:v1") ?? "{}");
    expect(saved.tabs.some((t: { auto?: unknown }) => t.auto)).toBe(false);
    expect(JSON.stringify(saved)).not.toContain("Ajuste do suporte");
  });

  it("abrir o mesmo relatório de novo volta pra guia que já existe", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { reportTabBundle } = await import("../useReportStore");
    const editor = draftToEditor(DRAFT);
    const bundle = reportTabBundle(editor.packages, editor.header, false);
    useReportTabsStore.getState().openAutoTab(meta(), "Estribo", bundle);
    useReportTabsStore.getState().addTab();
    useReportTabsStore.getState().openAutoTab(meta(), "Estribo", bundle);
    const tabs = useReportTabsStore.getState().tabs;
    expect(tabs.filter((t) => t.auto?.reportId === "R1")).toHaveLength(1);
    expect(tabs.find((t) => t.id === useReportTabsStore.getState().activeTabId)?.auto?.reportId).toBe("R1");
  });

  it("troca de usuário fecha as guias automáticas", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { reportTabBundle } = await import("../useReportStore");
    const editor = draftToEditor(DRAFT);
    useReportTabsStore.getState().openAutoTab(meta(), "Estribo", reportTabBundle(editor.packages, editor.header, false));
    useReportTabsStore.getState().closeAutoTabs();
    const s = useReportTabsStore.getState();
    expect(s.tabs.some((t) => t.auto)).toBe(false);
    expect(s.tabs.length).toBeGreaterThan(0);
  });
});

describe("formato do número do relatório", () => {
  it("confere com o padrão SE.AA.NNN e explica o formato sem mostrar regex", async () => {
    const { matchesNumberPattern, numberPatternLabel } = await import("../../utils/autoDraft");
    const pattern = String.raw`^SE\.\d{2}\.\d{3}$`; // o que o backend devolve em effective.number_pattern
    expect(matchesNumberPattern("SE.26.053", pattern)).toBe(true);
    expect(matchesNumberPattern("SE.26.0511", pattern)).toBe(false); // caso real: um dígito a mais
    expect(matchesNumberPattern("SE.26.053", undefined)).toBe(true);
    expect(numberPatternLabel("SE.##.###")).toBe("SE.##.### (ex.: SE.26.053)");
    expect(numberPatternLabel(undefined)).toBe("SE.##.### (ex.: SE.26.053)");
    expect(numberPatternLabel("SE.##.####")).toBe("SE.##.####");
    // formato configurado inválido nunca trava a digitação (o backend barra na aprovação)
    expect(matchesNumberPattern("qualquer", "([")).toBe(true);
  });
});

describe("guia aberta por quem revisa", () => {
  beforeEach(() => {
    vi.resetModules();
    installMemoryLocalStorage();
  });

  it("revisor edita até mandar pra aprovação; o gerente continua editando", async () => {
    const { canEditAutoTab } = await import("../useAutoGenerationStore");
    expect(canEditAutoTab({ status: "em_revisao", role: "reviewer" })).toBe(true);
    expect(canEditAutoTab({ status: "devolvido", role: "reviewer" })).toBe(true);
    expect(canEditAutoTab({ status: "revisado", role: "reviewer" })).toBe(false);
    expect(canEditAutoTab({ status: "revisado", role: "manager" })).toBe(true);
    expect(canEditAutoTab({ status: "revisado" })).toBe(true); // guia antiga sem papel = gerente
    expect(canEditAutoTab({ status: "aprovado", role: "manager" })).toBe(false);
  });

  it("salva pelas rotas de Minhas revisões, nunca pelas do gerente", async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      calls.push(url);
      return { ok: true, json: async () => ({ draft_version: 4 }) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);
    const { useAutoGenerationStore } = await import("../useAutoGenerationStore");
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { reportTabBundle } = await import("../useReportStore");
    const editor = draftToEditor(DRAFT);
    useReportTabsStore.getState().openAutoTab(
      { reportId: "R1", draftVersion: 3, competence: "2026-08", status: "em_revisao", formats: ["xlsx"], extras: editor.extras, role: "reviewer" },
      "Estribo",
      reportTabBundle(editor.packages, editor.header, false),
    );
    useAutoGenerationStore.setState({ saveState: { R1: "dirty" } });
    expect(await useAutoGenerationStore.getState().flushSave("R1")).toBe(true);
    expect(calls).toEqual(["/my-reviews/R1/draft"]);
    expect(useReportTabsStore.getState().tabs.find((t) => t.auto)?.auto?.draftVersion).toBe(4);
    vi.unstubAllGlobals();
  });
});

describe("destinatários do envio ao cliente", () => {
  it("aceita ; , espaço e quebra de linha entre os endereços", async () => {
    const { parseAddresses } = await import("../../components/AutoSendModal");
    expect(parseAddresses("a@x.com; b@y.com,c@z.com\n d@w.com ;;")).toEqual(["a@x.com", "b@y.com", "c@z.com", "d@w.com"]);
    expect(parseAddresses("   ")).toEqual([]);
  });

  it("só oferece os formatos que foram aprovados", async () => {
    const { approvedFormats } = await import("../../components/AutoSendModal");
    expect([...approvedFormats(["Relatório_Horas-Agosto.2026.xlsx", "Relatório_Horas-Agosto.2026.PDF"])].sort()).toEqual(["pdf", "xlsx"]);
    expect([...approvedFormats(["a.xlsx", "b (2).xlsx"])]).toEqual(["xlsx"]);
  });
});

describe("busca de revisor", () => {
  it("acha por pedaço do nome ou do login, sem acento e em qualquer ordem", async () => {
    const { filterReviewers } = await import("../../components/ReviewerPicker");
    const list = [
      { login: "dherrera", name: "Diego Herrera da Silva" },
      { login: "jsouza", name: "João Souza" },
      { login: "amaral", name: "Ana Amaral" },
    ];
    const logins = (q: string) => filterReviewers(list, q).map((r) => r.login);
    expect(logins("joao")).toEqual(["jsouza"]);
    expect(logins("silva die")).toEqual(["dherrera"]);
    expect(logins("AMA")).toEqual(["amaral"]);
    expect(logins("herr")).toEqual(["dherrera"]);
    expect(logins("   ")).toHaveLength(3);
    expect(logins("zzz")).toEqual([]);
  });
});
