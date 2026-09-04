import { describe, it, expect } from "vitest";
import { aggregateByProject, aggregateByDay, billableSplit, totalHours, distinctDaysWorked } from "../myHours";
import type { MyHoursEntry } from "../myHours";

function entry(overrides: Partial<MyHoursEntry> = {}): MyHoursEntry {
  return {
    date: "2026-08-01",
    hours: 1,
    pacote: "pacote",
    observacao: "atividade",
    project_id: "p1",
    project_name: "Projeto A",
    cost_center: "CAD",
    billable: true,
    ...overrides,
  };
}

describe("totalHours", () => {
  it("soma as horas de todos os lançamentos", () => {
    expect(totalHours([entry({ hours: 2.5 }), entry({ hours: 1.25 })])).toBe(3.75);
  });

  it("retorna 0 pra lista vazia", () => {
    expect(totalHours([])).toBe(0);
  });
});

describe("distinctDaysWorked", () => {
  it("conta dias distintos, não lançamentos", () => {
    const entries = [
      entry({ date: "2026-08-01" }),
      entry({ date: "2026-08-01" }), // mesmo dia, 2 lançamentos
      entry({ date: "2026-08-02" }),
    ];
    expect(distinctDaysWorked(entries)).toBe(2);
  });
});

describe("aggregateByProject", () => {
  it("soma horas de lançamentos do mesmo projeto e ordena do maior pro menor", () => {
    const entries = [
      entry({ project_name: "Projeto A", hours: 3 }),
      entry({ project_name: "Projeto B", hours: 10 }),
      entry({ project_name: "Projeto A", hours: 2 }),
    ];
    const result = aggregateByProject(entries);
    expect(result).toEqual([
      { name: "Projeto B", hours: 10 },
      { name: "Projeto A", hours: 5 },
    ]);
  });

  it("retorna lista vazia sem lançamentos", () => {
    expect(aggregateByProject([])).toEqual([]);
  });
});

describe("aggregateByDay", () => {
  it("soma horas por dia e ordena cronologicamente", () => {
    const entries = [
      entry({ date: "2026-08-03", hours: 4 }),
      entry({ date: "2026-08-01", hours: 5 }),
      entry({ date: "2026-08-01", hours: 3 }),
    ];
    const result = aggregateByDay(entries);
    expect(result).toEqual([
      { date: "2026-08-01", hours: 8 },
      { date: "2026-08-03", hours: 4 },
    ]);
  });

  it("dia sem lançamento não aparece na série (nunca inventa zero)", () => {
    // só 01 e 03 têm lançamento — 02 não deve aparecer como {date: "...-02", hours: 0}
    const entries = [entry({ date: "2026-08-01" }), entry({ date: "2026-08-03" })];
    const result = aggregateByDay(entries);
    expect(result.map((d) => d.date)).toEqual(["2026-08-01", "2026-08-03"]);
  });
});

describe("billableSplit", () => {
  it("separa horas faturáveis de não faturáveis e calcula o percentual", () => {
    const entries = [
      entry({ billable: true, hours: 7 }),
      entry({ billable: false, hours: 3 }),
    ];
    const result = billableSplit(entries);
    expect(result.billableHours).toBe(7);
    expect(result.nonBillableHours).toBe(3);
    expect(result.billablePct).toBeCloseTo(0.7, 9);
  });

  it("billablePct é null quando não há nenhum lançamento (evita divisão por zero)", () => {
    expect(billableSplit([]).billablePct).toBeNull();
  });

  it("100% faturável quando não há nenhuma hora não faturável", () => {
    const result = billableSplit([entry({ billable: true, hours: 5 })]);
    expect(result.billablePct).toBe(1);
    expect(result.nonBillableHours).toBe(0);
  });
});
