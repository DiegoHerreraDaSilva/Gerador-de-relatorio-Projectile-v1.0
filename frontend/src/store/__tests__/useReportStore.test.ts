import { describe, it, expect, beforeEach } from "vitest";
import { useReportStore } from "../useReportStore";
import type { WorkPackage, Group, Activity } from "../../api/types";

function activity(overrides: Partial<Activity> = {}): Activity {
  return { id: overrides.id ?? "a1", description: overrides.description ?? "Atividade", hours: overrides.hours ?? 5, extra: overrides.extra ?? false };
}

function group(id: string, activities: Activity[], overrides: Partial<Group> = {}): Group {
  return { id, name: overrides.name ?? `Grupo ${id}`, performance: overrides.performance ?? 1, activities };
}

function pkg(id: string, groups: Group[], overrides: Partial<WorkPackage> = {}): WorkPackage {
  return {
    id, key: id, projectCode: "SE.01.001", projectName: "Projeto Teste",
    groups, collapsedGroupIds: new Set(), fileName: "", fileNameEdited: false,
    chartBar: false, chartPie: false, pacoteScope: null,
    ...overrides,
  };
}

// cada teste começa com um estado limpo — as actions da store empilham
// undo/mexem em `packages` diretamente, sem isolamento nenhum entre testes
// se não resetarmos.
beforeEach(() => {
  useReportStore.setState({
    packages: [], activePackageId: null, undoStack: [],
    selectedByPane: { "0": new Set(), "1": new Set() },
  });
});

describe("addActivitiesFromIssues", () => {
  it("adiciona os itens como atividades não-editáveis (extra: false) no grupo certo", () => {
    const g = group("g1", [activity({ id: "a0", description: "Original", hours: 10 })]);
    useReportStore.setState({ packages: [pkg("p1", [g])] });

    const ok = useReportStore.getState().addActivitiesFromIssues("g1", "p1", [
      { description: "Recuperada 1", hours: 3.5 },
      { description: "Recuperada 2", hours: 2 },
    ]);

    expect(ok).toBe(true);
    const activities = useReportStore.getState().packages[0].groups[0].activities;
    expect(activities).toHaveLength(3);
    const recovered = activities.filter((a) => a.description.startsWith("Recuperada"));
    expect(recovered).toHaveLength(2);
    expect(recovered.every((a) => a.extra === false)).toBe(true);
    expect(recovered.map((a) => a.hours)).toEqual([3.5, 2]);
  });

  it("devolve false e não mexe em nada quando o grupo/pacote não existe mais", () => {
    // cenário real: usuário escolheu um grupo no dropdown, trocou de guia
    // (outro pacote/grupo carregado), e só depois clicou "Adicionar" —
    // ValidationBanner.tsx usa esse retorno pra não fazer a hora recuperável
    // sumir da lista como se tivesse sido adicionada em algum lugar.
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [])])] });

    const ok = useReportStore.getState().addActivitiesFromIssues("grupo-de-outra-guia", "p1", [
      { description: "Recuperada", hours: 3.5 },
    ]);

    expect(ok).toBe(false);
    expect(useReportStore.getState().packages[0].groups[0].activities).toHaveLength(0);
  });

  it("devolve false quando a lista de itens está vazia", () => {
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [])])] });
    const ok = useReportStore.getState().addActivitiesFromIssues("g1", "p1", []);
    expect(ok).toBe(false);
  });
});

describe("mergeActivitiesIntoActivity", () => {
  it("soma as horas das atividades arrastadas na atividade-alvo, mantendo o nome dela", () => {
    const alvo = activity({ id: "alvo", description: "Nome que fica", hours: 10 });
    const arrastada = activity({ id: "arrastada", description: "Nome que some", hours: 4 });
    const g = group("g1", [alvo, arrastada]);
    useReportStore.setState({ packages: [pkg("p1", [g])] });

    useReportStore.getState().mergeActivitiesIntoActivity(
      "p1", [{ groupId: "g1", activityId: "arrastada" }], "p1", "g1", "alvo"
    );

    const activities = useReportStore.getState().packages[0].groups[0].activities;
    expect(activities).toHaveLength(1);
    expect(activities[0].description).toBe("Nome que fica");
    expect(activities[0].hours).toBe(14);
  });

  it("soma atividades vindas de grupos de origem diferentes", () => {
    const alvo = activity({ id: "alvo", description: "Destino", hours: 5 });
    const g1 = group("g1", [alvo]);
    const g2 = group("g2", [activity({ id: "b", description: "De outro grupo", hours: 3 })]);
    useReportStore.setState({ packages: [pkg("p1", [g1, g2])] });

    useReportStore.getState().mergeActivitiesIntoActivity(
      "p1", [{ groupId: "g2", activityId: "b" }], "p1", "g1", "alvo"
    );

    const pkgAfter = useReportStore.getState().packages[0];
    expect(pkgAfter.groups[0].activities).toEqual([expect.objectContaining({ id: "alvo", hours: 8 })]);
    expect(pkgAfter.groups[1].activities).toHaveLength(0);
  });

  it("ignora a própria atividade-alvo se ela estiver entre as arrastadas (seleção múltipla), mas ainda soma as demais", () => {
    const alvo = activity({ id: "alvo", description: "Destino", hours: 5 });
    const outra = activity({ id: "outra", description: "Também arrastada", hours: 2 });
    const g = group("g1", [alvo, outra]);
    useReportStore.setState({ packages: [pkg("p1", [g])] });

    useReportStore.getState().mergeActivitiesIntoActivity(
      "p1",
      [{ groupId: "g1", activityId: "alvo" }, { groupId: "g1", activityId: "outra" }],
      "p1", "g1", "alvo"
    );

    const activities = useReportStore.getState().packages[0].groups[0].activities;
    expect(activities).toHaveLength(1);
    expect(activities[0].id).toBe("alvo");
    expect(activities[0].hours).toBe(7); // 5 + 2, "alvo" não somou nela mesma
  });
});

describe("moveActivitiesToPosition", () => {
  it("insere a atividade arrastada ANTES de beforeActivityId", () => {
    const a = activity({ id: "a", description: "A", hours: 1 });
    const b = activity({ id: "b", description: "B", hours: 2 });
    const c = activity({ id: "c", description: "C", hours: 3 });
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [a, b, c])])] });

    // arrasta "c" pra antes de "a"
    useReportStore.getState().moveActivitiesToPosition("p1", [{ groupId: "g1", activityId: "c" }], "p1", "g1", "a");

    const ids = useReportStore.getState().packages[0].groups[0].activities.map((x) => x.id);
    expect(ids).toEqual(["c", "a", "b"]);
  });

  it("beforeActivityId null insere no fim do grupo", () => {
    const a = activity({ id: "a", description: "A", hours: 1 });
    const b = activity({ id: "b", description: "B", hours: 2 });
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [a, b])])] });

    useReportStore.getState().moveActivitiesToPosition("p1", [{ groupId: "g1", activityId: "a" }], "p1", "g1", null);

    const ids = useReportStore.getState().packages[0].groups[0].activities.map((x) => x.id);
    expect(ids).toEqual(["b", "a"]);
  });

  it("beforeActivityId sendo uma das próprias atividades arrastadas cai no fallback de inserir no fim, sem duplicar nem perder atividade", () => {
    const a = activity({ id: "a", description: "A", hours: 1 });
    const b = activity({ id: "b", description: "B", hours: 2 });
    const c = activity({ id: "c", description: "C", hours: 3 });
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [a, b, c])])] });

    // arrasta "a" e "b" juntas, soltando "depois de b" -- mas como "b"
    // também está sendo arrastada, ela já não existe mais em
    // toGroup.activities no momento em que o índice é procurado.
    useReportStore.getState().moveActivitiesToPosition(
      "p1", [{ groupId: "g1", activityId: "a" }, { groupId: "g1", activityId: "b" }], "p1", "g1", "b"
    );

    const ids = useReportStore.getState().packages[0].groups[0].activities.map((x) => x.id);
    expect(ids).toEqual(["c", "a", "b"]); // nada duplicado, nada perdido
  });

  it("reordena dentro do mesmo grupo preservando a ordem relativa das arrastadas, não a ordem de seleção", () => {
    const a = activity({ id: "a", description: "A", hours: 1 });
    const b = activity({ id: "b", description: "B", hours: 2 });
    const c = activity({ id: "c", description: "C", hours: 3 });
    const d = activity({ id: "d", description: "D", hours: 4 });
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [a, b, c, d])])] });

    // seleciona "c" antes de "a" na lista de items (ordem de seleção do
    // usuário), mas a ordem final deve seguir a posição ORIGINAL nos grupos
    // de origem (a antes de c), não a ordem em que aparecem em `items`.
    useReportStore.getState().moveActivitiesToPosition(
      "p1", [{ groupId: "g1", activityId: "c" }, { groupId: "g1", activityId: "a" }], "p1", "g1", "d"
    );

    const ids = useReportStore.getState().packages[0].groups[0].activities.map((x) => x.id);
    expect(ids).toEqual(["b", "a", "c", "d"]);
  });
});

describe("moveGroupToPosition", () => {
  it("insere o grupo arrastado ANTES de beforeGroupId, dentro do mesmo pacote", () => {
    const g1 = group("g1", [activity({ id: "a1" })]);
    const g2 = group("g2", [activity({ id: "a2" })]);
    const g3 = group("g3", [activity({ id: "a3" })]);
    useReportStore.setState({ packages: [pkg("p1", [g1, g2, g3])] });

    // arrasta "g3" pra antes de "g1"
    useReportStore.getState().moveGroupToPosition("p1", "g3", "p1", "g1");

    const ids = useReportStore.getState().packages[0].groups.map((g) => g.id);
    expect(ids).toEqual(["g3", "g1", "g2"]);
  });

  it("beforeGroupId null insere no fim do pacote", () => {
    const g1 = group("g1", [activity()]);
    const g2 = group("g2", [activity()]);
    useReportStore.setState({ packages: [pkg("p1", [g1, g2])] });

    useReportStore.getState().moveGroupToPosition("p1", "g1", "p1", null);

    const ids = useReportStore.getState().packages[0].groups.map((g) => g.id);
    expect(ids).toEqual(["g2", "g1"]);
  });

  it("beforeGroupId sendo o próprio grupo arrastado cai no fallback de inserir no fim", () => {
    const g1 = group("g1", [activity()]);
    const g2 = group("g2", [activity()]);
    useReportStore.setState({ packages: [pkg("p1", [g1, g2])] });

    useReportStore.getState().moveGroupToPosition("p1", "g1", "p1", "g1");

    const ids = useReportStore.getState().packages[0].groups.map((g) => g.id);
    expect(ids).toEqual(["g2", "g1"]);
  });

  it("move o grupo pra outro pacote sem mesclar, mesmo com nome igual a um grupo existente lá", () => {
    // diferente de moveGroupToPackage: reordenar não deve mesclar por nome
    const gOrigem = group("gOrigem", [activity({ id: "a1", description: "Origem" })], { name: "ENG" });
    const gDestino = group("gDestino", [activity({ id: "a2", description: "Destino" })], { name: "ENG" });
    useReportStore.setState({ packages: [pkg("p1", [gOrigem]), pkg("p2", [gDestino])] });

    useReportStore.getState().moveGroupToPosition("p1", "gOrigem", "p2", null);

    const p1Groups = useReportStore.getState().packages[0].groups;
    const p2Groups = useReportStore.getState().packages[1].groups;
    expect(p1Groups).toHaveLength(0);
    expect(p2Groups.map((g) => g.id)).toEqual(["gDestino", "gOrigem"]); // dois grupos "ENG" distintos, não mesclados
  });
});
