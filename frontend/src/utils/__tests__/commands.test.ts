import { describe, expect, it, vi } from "vitest";
import { VIEW_ACCESS, VIEW_ORDER } from "../../appView";
import { buildCommands, canAccess, filterCommands, type PaletteContext } from "../commands";

function context(patch: Partial<PaletteContext> = {}): PaletteContext {
  return {
    isManager: false,
    isCoordinator: false,
    currentView: "report",
    hasAssignedReviews: false,
    tabs: [
      { id: "t1", label: "Legislation Package - Estribo" },
      { id: "t2", label: "Guia 2" },
    ],
    activeTabId: "t1",
    navigate: vi.fn(),
    switchTab: vi.fn(),
    newReport: vi.fn(),
    logout: vi.fn(),
    ...patch,
  };
}

const ids = (commands: { id: string }[]) => commands.map((c) => c.id);
const viewIds = (ctx: PaletteContext) =>
  ids(buildCommands(ctx).filter((c) => c.id.startsWith("view:"))).map((id) => id.slice(5));

describe("quem vê cada tela (a mesma regra do menu lateral)", () => {
  it("canAccess por papel", () => {
    const colaborador = { isManager: false, isCoordinator: false };
    const coordenador = { isManager: false, isCoordinator: true };
    const gerente = { isManager: true, isCoordinator: false };
    expect([colaborador, coordenador, gerente].map((u) => canAccess("all", u))).toEqual([true, true, true]);
    expect([colaborador, coordenador, gerente].map((u) => canAccess("coordinator", u))).toEqual([false, true, true]);
    expect([colaborador, coordenador, gerente].map((u) => canAccess("manager", u))).toEqual([false, false, true]);
  });

  it("toda tela da ordem tem uma regra de acesso", () => {
    expect(VIEW_ORDER).toHaveLength(new Set(VIEW_ORDER).size);
    expect(VIEW_ORDER.every((view) => view in VIEW_ACCESS)).toBe(true);
  });

  it("colaborador só vê as telas livres; 'Minhas revisões' só quando há revisão atribuída", () => {
    expect(viewIds(context())).toEqual(["report", "dashboard", "history"]);
    expect(viewIds(context({ hasAssignedReviews: true }))).toEqual(["report", "dashboard", "history", "my-reviews"]);
  });

  it("coordenador ganha o Diagnóstico, mas nunca Gerência, Analytics, Chat nem Geração automática", () => {
    const views = viewIds(context({ isCoordinator: true }));
    expect(views).toContain("diagnostics");
    expect(views).not.toContain("management");
    expect(views).not.toContain("analytics");
    expect(views).not.toContain("analytics-chat");
    expect(views).not.toContain("auto-generation");
  });

  it("gerente vê tudo", () => {
    expect(viewIds(context({ isManager: true, hasAssignedReviews: true }))).toEqual(VIEW_ORDER);
  });

  it("estar na tela de revisões a mantém na lista mesmo sem atribuição (como o menu)", () => {
    expect(viewIds(context({ currentView: "my-reviews" }))).toContain("my-reviews");
  });
});

describe("comandos: guias e ações", () => {
  it("cada guia aberta vira um comando; a atual aparece marcada só na tela do relatório", () => {
    const commands = buildCommands(context());
    const tab = commands.find((c) => c.id === "tab:t1");
    expect(tab?.hint).toBe("guia atual");
    expect(commands.find((c) => c.id === "tab:t2")?.hint).toBeUndefined();
    const elsewhere = buildCommands(context({ currentView: "history" })).find((c) => c.id === "tab:t1");
    expect(elsewhere?.hint).toBeUndefined();
  });

  it("escolher uma guia vai pra tela do relatório e troca de guia, nessa ordem", () => {
    const ctx = context({ currentView: "history" });
    const order: string[] = [];
    ctx.navigate = vi.fn(() => void order.push("navegar"));
    ctx.switchTab = vi.fn(() => void order.push("trocar"));
    buildCommands(ctx)
      .find((c) => c.id === "tab:t2")
      ?.run();
    expect(order).toEqual(["navegar", "trocar"]);
    expect(ctx.switchTab).toHaveBeenCalledWith("t2");
  });

  it("ações: novo relatório e sair chamam o que o contexto entregou", () => {
    const ctx = context();
    const commands = buildCommands(ctx);
    commands.find((c) => c.id === "action:new-report")?.run();
    commands.find((c) => c.id === "action:logout")?.run();
    expect(ctx.newReport).toHaveBeenCalledOnce();
    expect(ctx.logout).toHaveBeenCalledOnce();
  });

  it("a tela atual aparece marcada", () => {
    const commands = buildCommands(context({ currentView: "dashboard" }));
    expect(commands.find((c) => c.id === "view:dashboard")?.hint).toBe("tela atual");
  });
});

describe("filterCommands", () => {
  const all = buildCommands(context({ isManager: true, hasAssignedReviews: true }));

  it("busca vazia devolve tudo, na ordem", () => {
    expect(filterCommands(all, "  ")).toBe(all);
  });

  it("ignora acento e maiúsculas e aceita palavras em qualquer ordem", () => {
    expect(ids(filterCommands(all, "DIAGNOSTICO"))).toContain("view:diagnostics");
    expect(ids(filterCommands(all, "relatórios diagnóstico"))).toContain("view:diagnostics");
  });

  it("acha por sinônimo (palavra-chave), não só pelo título", () => {
    expect(ids(filterCommands(all, "kpi"))).toEqual(["view:management"]);
    expect(ids(filterCommands(all, "logout"))).toEqual(["action:logout"]);
  });

  it("título que começa com a busca vem antes do que só contém", () => {
    const result = ids(filterCommands(all, "hist"));
    expect(result[0]).toBe("view:history");
  });

  it("sem resultado devolve lista vazia", () => {
    expect(filterCommands(all, "xyzzy")).toEqual([]);
  });

  it("acha uma guia pelo nome do projeto", () => {
    expect(ids(filterCommands(all, "estribo"))).toEqual(["tab:t1"]);
  });
});
