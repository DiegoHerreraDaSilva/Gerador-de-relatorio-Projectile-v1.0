import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  CHANGELOG,
  entriesFor,
  markSeen,
  readSeenVersion,
  roleOf,
  unseenEntries,
  type ChangelogEntry,
} from "../changelog";

const LOG: ChangelogEntry[] = [
  { version: "3", title: "Três", items: [{ text: "c-todos" }, { text: "c-gerente", roles: ["manager"] }] },
  { version: "2", title: "Dois", items: [{ text: "b-gerente", roles: ["manager"] }] },
  { version: "1", title: "Um", items: [{ text: "a-todos" }] },
];

describe("roleOf", () => {
  it("gerente vence coordenador; o resto é colaborador", () => {
    expect(roleOf({ isManager: true, isCoordinator: true })).toBe("manager");
    expect(roleOf({ isManager: false, isCoordinator: true })).toBe("coordinator");
    expect(roleOf({ isManager: false, isCoordinator: false })).toBe("collaborator");
  });
});

describe("unseenEntries", () => {
  it("primeira vez (nada visto): só a mais recente, não o histórico inteiro", () => {
    expect(unseenEntries(null, "manager", LOG).map((e) => e.version)).toEqual(["3"]);
  });

  it("mostra só o que veio depois da versão vista, da mais nova pra mais antiga", () => {
    expect(unseenEntries("1", "manager", LOG).map((e) => e.version)).toEqual(["3", "2"]);
    expect(unseenEntries("2", "manager", LOG).map((e) => e.version)).toEqual(["3"]);
  });

  it("já viu a última: nada a mostrar", () => {
    expect(unseenEntries("3", "manager", LOG)).toEqual([]);
  });

  it("versão vista que não existe mais na lista: cai na mais recente", () => {
    expect(unseenEntries("antiga", "manager", LOG).map((e) => e.version)).toEqual(["3"]);
  });

  it("filtra os itens pelo papel e some a entrada que não tem nada pra ele", () => {
    const collaborator = unseenEntries("1", "collaborator", LOG);
    expect(collaborator.map((e) => e.version)).toEqual(["3"]); // a "2" só tinha item de gerente
    expect(collaborator[0].items.map((i) => i.text)).toEqual(["c-todos"]);
  });
});

describe("entriesFor", () => {
  it("todas as entradas, só com os itens do papel", () => {
    expect(entriesFor("collaborator", LOG).map((e) => e.version)).toEqual(["3", "1"]);
    expect(entriesFor("manager", LOG).map((e) => e.version)).toEqual(["3", "2", "1"]);
  });
});

describe("a lista real", () => {
  it("toda entrada tem versão única, título e pelo menos um item pra algum papel", () => {
    expect(new Set(CHANGELOG.map((e) => e.version)).size).toBe(CHANGELOG.length);
    for (const entry of CHANGELOG) {
      expect(entry.title.trim()).not.toBe("");
      expect(entry.items.length).toBeGreaterThan(0);
    }
  });

  it("colaborador vê ao menos um item (a novidade nunca abre vazia pra ninguém)", () => {
    for (const role of ["manager", "coordinator", "collaborator"] as const) {
      expect(entriesFor(role).length).toBeGreaterThan(0);
    }
  });
});

describe("o que cada pessoa já viu (por login, neste navegador)", () => {
  const store: Record<string, string> = {};
  beforeEach(() => {
    for (const key of Object.keys(store)) delete store[key];
    (globalThis as unknown as { localStorage: Storage }).localStorage = {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => void (store[k] = v),
      removeItem: (k: string) => void delete store[k],
      clear: () => {},
      key: () => null,
      length: 0,
    } as Storage;
  });
  afterEach(() => {
    delete (globalThis as { localStorage?: Storage }).localStorage;
  });

  it("guarda por login sem diferenciar caixa e não mistura pessoas", () => {
    expect(readSeenVersion("Ana")).toBeNull();
    markSeen("Ana", "2026-09-30");
    expect(readSeenVersion("ana")).toBe("2026-09-30");
    expect(readSeenVersion("beto")).toBeNull();
  });

  it("sem localStorage (modo privado) não quebra: só volta a aparecer", () => {
    delete (globalThis as { localStorage?: Storage }).localStorage;
    expect(() => markSeen("ana", "1")).not.toThrow();
    expect(readSeenVersion("ana")).toBeNull();
  });
});
