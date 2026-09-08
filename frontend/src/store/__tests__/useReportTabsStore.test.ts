import { describe, it, expect, beforeEach, vi } from "vitest";
import type { WorkPackage } from "../../api/types";

/** Mock mínimo de localStorage (ambiente de teste roda em Node puro, sem
 * DOM — ver `environment: "node"` em vite.config.ts) — precisa existir
 * ANTES de importar `useReportTabsStore`, já que `hydrate()` roda uma vez
 * no carregamento do módulo. */
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

function fakePackage(overrides: Partial<WorkPackage> = {}): WorkPackage {
  return {
    id: "p1",
    key: "p1",
    projectCode: "SE.01.001",
    projectName: "Projeto A",
    groups: [],
    collapsedGroupIds: new Set(),
    fileName: "",
    fileNameEdited: false,
    chartBar: false,
    chartPie: false,
    pacoteScope: null,
    ...overrides,
  };
}

// `vi.resetModules()` + `import()` dinâmico em cada teste: `hydrate()` só
// roda uma vez, no carregamento do módulo — pra testar boot com estados
// diferentes de localStorage (vazio, corrompido, com dado válido) cada
// teste precisa de uma reavaliação fresca do módulo, não a mesma instância
// reaproveitada entre casos.
beforeEach(() => {
  vi.resetModules();
  installMemoryLocalStorage();
});

describe("useReportTabsStore", () => {
  it("começa com 1 guia em branco quando não há nada salvo", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const s = useReportTabsStore.getState();
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0].label).toBe("Guia 1");
    expect(s.tabs[0].labelEdited).toBe(false);
    expect(s.bundles[s.activeTabId]).toBeTruthy();
  });

  it("addTab cria uma guia nova vazia e preserva o conteúdo da guia anterior", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { useReportStore } = await import("../useReportStore");

    useReportStore.setState((s) => {
      s.packages = [fakePackage()];
      s.showImportCard = false;
    });
    const firstTabId = useReportTabsStore.getState().activeTabId;

    useReportTabsStore.getState().addTab();
    const secondTabId = useReportTabsStore.getState().activeTabId;

    expect(secondTabId).not.toBe(firstTabId);
    expect(useReportTabsStore.getState().tabs).toHaveLength(2);
    expect(useReportStore.getState().packages).toHaveLength(0); // guia nova começa em branco

    useReportTabsStore.getState().switchTab(firstTabId);
    expect(useReportStore.getState().packages).toHaveLength(1);
    expect(useReportStore.getState().packages[0].projectName).toBe("Projeto A");
  });

  it("renomeia a guia sozinha pro nome do projeto na 1ª vez que ganha pacotes", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { useReportStore } = await import("../useReportStore");

    useReportStore.setState((s) => {
      s.packages = [fakePackage({ projectName: "Encapsulamento Cabina" })];
    });

    const active = useReportTabsStore.getState();
    const tab = active.tabs.find((t) => t.id === active.activeTabId);
    expect(tab?.label).toBe("Encapsulamento Cabina");
    expect(tab?.labelEdited).toBe(false);
  });

  it("renameTab manual trava o rótulo — import não sobrescreve mais", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { useReportStore } = await import("../useReportStore");

    const id = useReportTabsStore.getState().activeTabId;
    useReportTabsStore.getState().renameTab(id, "Meu apelido");
    useReportStore.setState((s) => {
      s.packages = [fakePackage({ projectName: "Outro nome qualquer" })];
    });

    const tab = useReportTabsStore.getState().tabs.find((t) => t.id === id);
    expect(tab?.label).toBe("Meu apelido");
    expect(tab?.labelEdited).toBe(true);
  });

  it("closeTab nunca fecha a última guia restante", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const onlyId = useReportTabsStore.getState().tabs[0].id;
    useReportTabsStore.getState().closeTab(onlyId);
    expect(useReportTabsStore.getState().tabs).toHaveLength(1);
    expect(useReportTabsStore.getState().tabs[0].id).toBe(onlyId);
  });

  it("closeTab remove só a guia fechada, mantém as outras intactas", async () => {
    const { useReportTabsStore } = await import("../useReportTabsStore");
    const { useReportStore } = await import("../useReportStore");

    const firstId = useReportTabsStore.getState().activeTabId;
    useReportTabsStore.getState().addTab();
    const secondId = useReportTabsStore.getState().activeTabId;
    useReportStore.setState((s) => {
      s.packages = [fakePackage({ projectName: "Guia 2" })];
    });

    useReportTabsStore.getState().closeTab(firstId);

    expect(useReportTabsStore.getState().tabs).toHaveLength(1);
    expect(useReportTabsStore.getState().tabs[0].id).toBe(secondId);
    // fechar a OUTRA guia (não a ativa) não deve mexer no que está carregado agora
    expect(useReportStore.getState().packages[0].projectName).toBe("Guia 2");
  });

  it("hydrate restaura as guias salvas do localStorage num boot novo", async () => {
    const mod1 = await import("../useReportTabsStore");
    const store1 = await import("../useReportStore");

    store1.useReportStore.setState((s) => {
      s.packages = [fakePackage({ projectName: "Projeto Persistido" })];
    });
    mod1.useReportTabsStore.getState().addTab();
    mod1.useReportTabsStore.getState().persist();

    vi.resetModules();
    const mod2 = await import("../useReportTabsStore");
    const store2 = await import("../useReportStore");

    expect(mod2.useReportTabsStore.getState().tabs).toHaveLength(2);
    const firstTabId = mod2.useReportTabsStore.getState().tabs[0].id;
    mod2.useReportTabsStore.getState().switchTab(firstTabId);
    expect(store2.useReportStore.getState().packages[0].projectName).toBe("Projeto Persistido");
  });

  it("localStorage com JSON inválido não quebra o boot — cai pra 1 guia em branco", async () => {
    (globalThis as unknown as { localStorage: Storage }).localStorage.setItem(
      "relatorio-horas:tabs:v1",
      "isso não é json válido{{{"
    );
    const { useReportTabsStore } = await import("../useReportTabsStore");
    expect(useReportTabsStore.getState().tabs).toHaveLength(1);
  });

  it("localStorage com formato inesperado (sem tabs/bundles) não quebra o boot", async () => {
    (globalThis as unknown as { localStorage: Storage }).localStorage.setItem(
      "relatorio-horas:tabs:v1",
      JSON.stringify({ algumaCoisa: true })
    );
    const { useReportTabsStore } = await import("../useReportTabsStore");
    expect(useReportTabsStore.getState().tabs).toHaveLength(1);
  });
});
