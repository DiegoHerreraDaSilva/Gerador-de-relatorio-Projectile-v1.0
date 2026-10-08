import { beforeEach, describe, expect, it } from "vitest";
import type { Activity, Group, WorkPackage } from "../../api/types";
import { useReportStore } from "../useReportStore";

function activity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: overrides.id ?? "a1",
    description: overrides.description ?? "Atividade",
    hours: overrides.hours ?? 5,
    extra: overrides.extra ?? false,
    ...(overrides.externalKeys ? { externalKeys: overrides.externalKeys } : {}),
  };
}

function group(id: string, activities: Activity[]): Group {
  return { id, name: `Grupo ${id}`, performance: 1, activities };
}

function pkg(id: string, groups: Group[]): WorkPackage {
  return {
    id,
    key: id,
    projectCode: "",
    projectName: "Projeto",
    groups,
    collapsedGroupIds: new Set(),
    fileName: "",
    fileNameEdited: false,
    chartBar: false,
    chartPie: false,
    pacoteScope: null,
    language: "pt",
  };
}

const state = () => useReportStore.getState();

beforeEach(() => {
  useReportStore.setState({
    packages: [],
    activePackageId: null,
    undoStack: [],
    hasGeneratedOnce: true,
    selectedByPane: { "0": new Set(), "1": new Set() },
  });
});

describe("applyExternalHours", () => {
  it("cria a atividade fixa (extra: false) com a descrição, as horas e a chave de origem", () => {
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [activity({ id: "a0", hours: 10 })])])] });

    const ok = state().applyExternalHours([
      { packageId: "p1", groupId: "g1", description: "Fulano – Revisão", hours: 3.5, key: "k1" },
    ]);

    expect(ok).toBe(true);
    const created = state().packages[0].groups[0].activities.find((a) => a.description === "Fulano – Revisão");
    expect(created).toMatchObject({ hours: 3.5, extra: false, externalKeys: ["k1"] });
    expect(state().hasGeneratedOnce).toBe(false);
    expect(state().undoStack).toHaveLength(1);
  });

  it("soma na atividade de mesma descrição e une as chaves, sem duplicar a atividade", () => {
    useReportStore.setState({
      packages: [
        pkg("p1", [
          group("g1", [activity({ id: "a0", description: "Fulano – Revisão", hours: 2, externalKeys: ["k0"] })]),
        ]),
      ],
    });

    state().applyExternalHours([
      { packageId: "p1", groupId: "g1", description: "fulano – revisão", hours: 3, key: "k1" },
      { packageId: "p1", groupId: "g1", description: "Fulano – Revisão", hours: 1, key: "k2" },
    ]);

    const activities = state().packages[0].groups[0].activities;
    expect(activities).toHaveLength(1);
    expect(activities[0].hours).toBe(6);
    expect(activities[0].externalKeys).toEqual(["k0", "k1", "k2"]);
  });

  it("vários destinos num só Desfazer", () => {
    useReportStore.setState({ packages: [pkg("p1", [group("g1", []), group("g2", [])])] });

    state().applyExternalHours([
      { packageId: "p1", groupId: "g1", description: "A", hours: 1, key: "k1" },
      { packageId: "p1", groupId: "g2", description: "B", hours: 2, key: "k2" },
    ]);
    expect(state().undoStack).toHaveLength(1);

    state().undo();
    expect(state().packages[0].groups.flatMap((g) => g.activities)).toEqual([]);
  });

  it("ignora destino que não existe mais, aplica os demais e devolve false se nada couber", () => {
    useReportStore.setState({ packages: [pkg("p1", [group("g1", [])])] });

    expect(
      state().applyExternalHours([
        { packageId: "p1", groupId: "g1", description: "A", hours: 1, key: "k1" },
        { packageId: "p1", groupId: "sumiu", description: "B", hours: 2, key: "k2" },
      ]),
    ).toBe(true);
    expect(state().packages[0].groups[0].activities).toHaveLength(1);

    const before = state().undoStack.length;
    expect(state().applyExternalHours([{ packageId: "x", groupId: "y", description: "C", hours: 1, key: "k3" }])).toBe(
      false,
    );
    expect(state().applyExternalHours([])).toBe(false);
    expect(state().undoStack).toHaveLength(before);
  });
});

describe("chaves de horas externas sobrevivem às outras edições", () => {
  it("arrastar atividades uma sobre a outra une as chaves", () => {
    useReportStore.setState({
      packages: [
        pkg("p1", [
          group("g1", [
            activity({ id: "alvo", description: "Alvo", hours: 1, externalKeys: ["k1"] }),
            activity({ id: "mov", description: "Movida", hours: 2, externalKeys: ["k2"] }),
          ]),
        ]),
      ],
    });

    state().mergeActivitiesIntoActivity("p1", [{ groupId: "g1", activityId: "mov" }], "p1", "g1", "alvo");

    const [alvo] = state().packages[0].groups[0].activities;
    expect(alvo.hours).toBe(3);
    expect(alvo.externalKeys).toEqual(["k1", "k2"]);
  });

  it("mover atividade pra grupo que já tem a mesma descrição une as chaves", () => {
    useReportStore.setState({
      packages: [
        pkg("p1", [
          group("g1", [activity({ id: "a", description: "Igual", hours: 1, externalKeys: ["k1"] })]),
          group("g2", [activity({ id: "b", description: "Igual", hours: 2, externalKeys: ["k2"] })]),
        ]),
      ],
    });

    state().moveActivitiesToGroup("p1", [{ groupId: "g1", activityId: "a" }], "p1", "g2");

    const [only] = state().packages[0].groups[1].activities;
    expect(only.hours).toBe(3);
    expect(only.externalKeys).toEqual(["k2", "k1"]);
  });

  it("edição pelo chat mantém as chaves da atividade que já existia", () => {
    useReportStore.setState({
      packages: [
        pkg("p1", [group("g1", [activity({ id: "a0", description: "Fulano – X", hours: 2, externalKeys: ["k1"] })])]),
      ],
    });

    state().applyChatState({
      packages: [
        {
          projectCode: "",
          projectName: "Projeto",
          groups: [
            {
              id: "g1",
              name: "Grupo g1",
              performance: 1,
              activities: [{ id: "a0", description: "Fulano – X (revisado)", hours: 2 }],
            },
          ],
        },
      ],
      locationDate: "",
      monthLabel: "Agosto/2026",
      signer1Name: "",
      signer1Company: "",
      signer2Name: "",
      signer2Company: "",
    } as never);

    const [a] = state().packages[0].groups[0].activities;
    expect(a.description).toBe("Fulano – X (revisado)");
    expect(a.externalKeys).toEqual(["k1"]);
  });

  it("atividade comum nunca ganha o campo externalKeys", () => {
    useReportStore.setState({
      packages: [pkg("p1", [group("g1", [activity({ id: "a", description: "Igual", hours: 1 })])])],
    });
    state().applyExternalHours([{ packageId: "p1", groupId: "g1", description: "Igual", hours: 1, key: "k1" }]);
    expect(state().packages[0].groups[0].activities[0].externalKeys).toEqual(["k1"]);

    useReportStore.setState({
      packages: [pkg("p1", [group("g1", [activity({ id: "a", description: "Igual", hours: 1 })])])],
    });
    expect("externalKeys" in state().packages[0].groups[0].activities[0]).toBe(false);
  });
});
