import { describe, expect, it } from "vitest";
import type { ExternalRow, WorkPackage } from "../../api/types";
import {
  existingKeys,
  externalDescription,
  norm,
  periodBounds,
  planExternalMerge,
  resolvePending,
  rowKey,
  totalHours,
} from "../externalHours";

function row(overrides: Partial<ExternalRow> = {}): ExternalRow {
  return {
    row: 2,
    date: "2026-08-12",
    collaborator: "Fulano de Tal",
    project: "Projeto A 08.2026",
    package: "Pacote 1",
    description: "Revisão do desenho",
    hours: 3.5,
    ...overrides,
  };
}

function pkg(
  id: string,
  projectName: string,
  groups: Array<{ id: string; name: string; keys?: string[][] }>,
): WorkPackage {
  return {
    id,
    key: id,
    projectCode: "",
    projectName,
    groups: groups.map((g) => ({
      id: g.id,
      name: g.name,
      performance: 1,
      activities: (g.keys ?? []).map((keys, i) => ({
        id: `${g.id}-a${i}`,
        description: "x",
        hours: 1,
        extra: false,
        externalKeys: keys,
      })),
    })),
    collapsedGroupIds: new Set(),
    fileName: "",
    fileNameEdited: false,
    chartBar: false,
    chartPie: false,
    pacoteScope: null,
    language: "pt",
  };
}

const PERIOD = "Agosto/2026";

describe("norm / rowKey / externalDescription", () => {
  it("ignora acento, caixa e espaço duplo", () => {
    expect(norm("  Pacote  de TRABALHO  ")).toBe("pacote de trabalho");
    expect(norm("Revisão")).toBe("revisao");
  });

  it("a descrição leva o nome do colaborador na frente", () => {
    expect(externalDescription(row())).toBe("Fulano de Tal – Revisão do desenho");
  });

  it("a chave não muda com acento ou caixa, mas muda com data, pessoa ou horas", () => {
    const base = rowKey(row());
    expect(rowKey(row({ collaborator: "FULANO DE TAL", description: "revisao do desenho" }))).toBe(base);
    expect(rowKey(row({ date: "2026-08-13" }))).not.toBe(base);
    expect(rowKey(row({ collaborator: "Beltrana" }))).not.toBe(base);
    expect(rowKey(row({ hours: 4 }))).not.toBe(base);
  });
});

describe("periodBounds", () => {
  it("mês único, intervalo no mesmo ano e intervalo que cruza o ano", () => {
    expect(periodBounds("Agosto/2026")).toEqual({ start: "2026-08-01", end: "2026-08-31" });
    expect(periodBounds("Julho a Novembro/2026")).toEqual({ start: "2026-07-01", end: "2026-11-30" });
    expect(periodBounds("Dezembro/2025 a Fevereiro/2026")).toEqual({ start: "2025-12-01", end: "2026-02-28" });
    expect(periodBounds("Março/2024")).toEqual({ start: "2024-03-01", end: "2024-03-31" });
  });

  it("rótulo desconhecido não confere data", () => {
    expect(periodBounds("")).toBeNull();
    expect(periodBounds("Abril de 2026")).toBeNull();
    expect(periodBounds("Foo/2026")).toBeNull();
  });
});

describe("planExternalMerge", () => {
  const packages = [
    pkg("p1", "Projeto A 08.2026", [
      { id: "g1", name: "Pacote 1" },
      { id: "g2", name: "Pacote 2" },
    ]),
  ];

  it("casa pacote pelo nome do projeto e grupo pelo pacote de trabalho, sem diferenciar acento nem caixa", () => {
    const plan = planExternalMerge(packages, [row({ project: "projeto a 08.2026", package: "PACOTE 2" })], PERIOD);
    expect(plan.pending).toEqual([]);
    expect(plan.placements).toEqual([
      {
        packageId: "p1",
        groupId: "g2",
        description: "Fulano de Tal – Revisão do desenho",
        hours: 3.5,
        key: rowKey(row({ project: "projeto a 08.2026", package: "PACOTE 2" })),
      },
    ]);
  });

  it("também casa pela chave do pacote", () => {
    const keyed = [{ ...pkg("p1", "Outro nome", [{ id: "g1", name: "Pacote 1" }]), key: "PRJ-77" }];
    expect(planExternalMerge(keyed, [row({ project: "prj-77" })], PERIOD).placements).toHaveLength(1);
  });

  it("projeto inexistente e grupo inexistente ficam pendentes, agrupados por (projeto, pacote)", () => {
    const rows = [
      row({ row: 2, project: "Projeto Z", package: "Pacote 1", hours: 1 }),
      row({ row: 3, project: "Projeto Z", package: "Pacote 1", description: "Outra", hours: 2 }),
      row({ row: 4, project: "Projeto A 08.2026", package: "Pacote 9", hours: 4 }),
    ];
    const plan = planExternalMerge(packages, rows, PERIOD);
    expect(plan.placements).toEqual([]);
    expect(plan.pending.map((b) => [b.project, b.workPackage, b.missing, b.rows.length, b.hours])).toEqual([
      ["Projeto Z", "Pacote 1", "projeto", 2, 3],
      ["Projeto A 08.2026", "Pacote 9", "grupo", 1, 4],
    ]);
  });

  it("linha que o relatório já tem é descartada como duplicada (anexo repetido)", () => {
    const already = rowKey(row());
    const withKeys = [pkg("p1", "Projeto A 08.2026", [{ id: "g1", name: "Pacote 1", keys: [[already]] }])];
    const plan = planExternalMerge(withKeys, [row(), row({ row: 3, hours: 1 })], PERIOD);
    expect(plan.duplicates.map((r) => r.row)).toEqual([2]);
    expect(plan.placements).toHaveLength(1);
  });

  it("linhas idênticas dentro do mesmo arquivo valem como lançamentos distintos", () => {
    const plan = planExternalMerge(packages, [row({ row: 2 }), row({ row: 3 })], PERIOD);
    expect(plan.placements).toHaveLength(2);
    expect(plan.duplicates).toEqual([]);
  });

  it("data fora do período do relatório é descartada e listada", () => {
    const plan = planExternalMerge(packages, [row({ date: "2026-09-01" }), row({ date: "2026-07-31" }), row()], PERIOD);
    expect(plan.outOfPeriod.map((r) => r.date)).toEqual(["2026-09-01", "2026-07-31"]);
    expect(plan.placements).toHaveLength(1);
  });

  it("período não reconhecido não descarta nada por data", () => {
    const plan = planExternalMerge(packages, [row({ date: "2020-01-01" })], "???");
    expect(plan.outOfPeriod).toEqual([]);
    expect(plan.placements).toHaveLength(1);
  });

  it("duplicada vem antes de fora do período", () => {
    const old = row({ date: "2026-09-10" });
    const withKeys = [pkg("p1", "Projeto A 08.2026", [{ id: "g1", name: "Pacote 1", keys: [[rowKey(old)]] }])];
    const plan = planExternalMerge(withKeys, [old], PERIOD);
    expect(plan.duplicates).toHaveLength(1);
    expect(plan.outOfPeriod).toHaveLength(0);
  });
});

describe("resolvePending / totalHours / existingKeys", () => {
  const packages = [pkg("p1", "Projeto A 08.2026", [{ id: "g1", name: "Pacote 1" }])];
  const rows = [
    row({ project: "Projeto Z", hours: 1.5 }),
    row({ project: "Projeto Z", description: "Outra", hours: 2 }),
  ];

  it("pendente com destino escolhido entra; sem escolha (ou vazio) é descartado", () => {
    const plan = planExternalMerge(packages, rows, PERIOD);
    const [bucket] = plan.pending;
    expect(resolvePending(plan, {})).toEqual([]);
    expect(resolvePending(plan, { [bucket.id]: "" })).toEqual([]);
    const placed = resolvePending(plan, { [bucket.id]: "p1::g1" });
    expect(placed.map((p) => [p.packageId, p.groupId, p.hours])).toEqual([
      ["p1", "g1", 1.5],
      ["p1", "g1", 2],
    ]);
    expect(totalHours(placed)).toBe(3.5);
  });

  it("junta os automáticos com os resolvidos", () => {
    const plan = planExternalMerge(packages, [row(), ...rows], PERIOD);
    expect(resolvePending(plan, { [plan.pending[0].id]: "p1::g1" })).toHaveLength(3);
  });

  it("existingKeys junta as chaves de todas as atividades do relatório", () => {
    const withKeys = [
      pkg("p1", "A", [{ id: "g1", name: "G", keys: [["k1", "k2"], ["k3"]] }]),
      pkg("p2", "B", [{ id: "g2", name: "G", keys: [["k4"]] }]),
    ];
    expect([...existingKeys(withKeys)].sort()).toEqual(["k1", "k2", "k3", "k4"]);
  });
});
