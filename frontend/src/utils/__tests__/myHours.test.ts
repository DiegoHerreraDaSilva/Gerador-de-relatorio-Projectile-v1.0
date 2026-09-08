import { describe, expect, it } from "vitest";
import {
  aggregateByPacote,
  billingSplit,
  dailyTotals,
  distinctDaysWorked,
  totalHours,
  weekdayProfile,
  type MyHoursEntry,
} from "../myHours";

let seq = 0;

function entry(partial: Partial<MyHoursEntry> = {}): MyHoursEntry {
  seq += 1;
  return {
    id: `e${seq}`,
    date: "2026-08-03",
    start: "09:00",
    end: "12:00",
    hours: 3,
    pacote: "TCI_Suporte",
    observacao: "Atendimento",
    project_id: "1462.3.1",
    project_name: "TCI",
    top_project: "1471 INT_Administrativo",
    cost_center: "ADM",
    billing_class: "interno",
    ...partial,
  };
}

describe("totalHours / distinctDaysWorked", () => {
  it("soma as horas", () => {
    expect(totalHours([entry({ hours: 2 }), entry({ hours: 0.17 })])).toBe(2.17);
  });

  it("lista vazia soma zero", () => {
    expect(totalHours([])).toBe(0);
  });

  it("conta dias distintos, não lançamentos", () => {
    const entries = [
      entry({ date: "2026-08-03" }),
      entry({ date: "2026-08-03" }),
      entry({ date: "2026-08-04" }),
    ];
    expect(distinctDaysWorked(entries)).toBe(2);
  });
});

describe("aggregateByPacote", () => {
  it("agrupa por pacote e ordena pelo maior", () => {
    const result = aggregateByPacote([
      entry({ pacote: "TCI_Suporte", hours: 1 }),
      entry({ pacote: "TCI_Infraestrutura", hours: 4 }),
      entry({ pacote: "TCI_Suporte", hours: 2 }),
    ]);
    expect(result.map((r) => r.name)).toEqual(["TCI_Infraestrutura", "TCI_Suporte"]);
    expect(result[0].hours).toBe(4);
    expect(result[1].hours).toBe(3);
  });

  it("share é fração do TOTAL do período, não do maior item", () => {
    // com um item só, normalizar pelo máximo daria 100% sempre — auto-referente
    const result = aggregateByPacote([
      entry({ pacote: "A", hours: 3 }),
      entry({ pacote: "B", hours: 1 }),
    ]);
    expect(result[0].share).toBeCloseTo(0.75);
    expect(result[1].share).toBeCloseTo(0.25);
  });

  it("shares somam 1", () => {
    const result = aggregateByPacote([
      entry({ pacote: "A", hours: 2 }),
      entry({ pacote: "B", hours: 3 }),
      entry({ pacote: "C", hours: 5 }),
    ]);
    expect(result.reduce((s, r) => s + r.share, 0)).toBeCloseTo(1);
  });

  it("pacote vazio recebe rótulo em vez de string vazia", () => {
    expect(aggregateByPacote([entry({ pacote: "" })])[0].name).toBe("Sem pacote");
  });

  it("lista vazia devolve lista vazia", () => {
    expect(aggregateByPacote([])).toEqual([]);
  });
});

describe("dailyTotals", () => {
  it("soma por dia", () => {
    const totals = dailyTotals([
      entry({ date: "2026-08-03", hours: 2 }),
      entry({ date: "2026-08-03", hours: 4 }),
      entry({ date: "2026-08-04", hours: 6 }),
    ]);
    expect(totals.get("2026-08-03")).toBe(6);
    expect(totals.get("2026-08-04")).toBe(6);
  });

  it("dia sem lançamento não é inventado como zero", () => {
    const totals = dailyTotals([entry({ date: "2026-08-03" })]);
    expect(totals.has("2026-08-04")).toBe(false);
    expect(totals.size).toBe(1);
  });
});

describe("billingSplit", () => {
  it("separa as três classes", () => {
    const split = billingSplit([
      entry({ billing_class: "externo", hours: 6 }),
      entry({ billing_class: "interno", hours: 3 }),
      entry({ billing_class: "nao_classificado", hours: 1 }),
    ]);
    expect(split.externo).toBe(6);
    expect(split.interno).toBe(3);
    expect(split.nao_classificado).toBe(1);
    expect(split.total).toBe(10);
  });

  it("100% de uma classe não vale desenhar", () => {
    // é o caso real do usuário: todo trabalho interno. Um donut 0%/100%
    // gastava um terço da largura pra não dizer nada.
    const split = billingSplit([entry({ billing_class: "interno", hours: 6 })]);
    expect(split.worthShowing).toBe(false);
  });

  it("mistura real vale desenhar", () => {
    const split = billingSplit([
      entry({ billing_class: "externo", hours: 6 }),
      entry({ billing_class: "interno", hours: 4 }),
    ]);
    expect(split.worthShowing).toBe(true);
  });

  it("classe abaixo de 5% não conta como segunda classe", () => {
    const split = billingSplit([
      entry({ billing_class: "interno", hours: 99 }),
      entry({ billing_class: "externo", hours: 1 }),
    ]);
    expect(split.worthShowing).toBe(false);
  });

  it("lista vazia não quebra", () => {
    const split = billingSplit([]);
    expect(split.total).toBe(0);
    expect(split.worthShowing).toBe(false);
  });
});

describe("weekdayProfile", () => {
  it("índice 0 é segunda", () => {
    // 2026-08-03 é segunda, 2026-08-07 é sexta
    const profile = weekdayProfile([
      entry({ date: "2026-08-03", hours: 6 }),
      entry({ date: "2026-08-07", hours: 4 }),
    ]);
    expect(profile.averages[0]).toBe(6);
    expect(profile.averages[4]).toBe(4);
    expect(profile.averages[5]).toBeNull();
  });

  it("amplitude pequena é o sinal de que não há padrão semanal", () => {
    // reproduz o medido: seg 5,76 ... sex 5,87 -> amplitude 0,16h
    const profile = weekdayProfile([
      entry({ date: "2026-08-03", hours: 5.76 }),
      entry({ date: "2026-08-04", hours: 5.82 }),
      entry({ date: "2026-08-05", hours: 5.82 }),
      entry({ date: "2026-08-06", hours: 5.92 }),
      entry({ date: "2026-08-07", hours: 5.87 }),
    ]);
    expect(profile.amplitude).toBeCloseTo(0.16, 2);
  });

  it("amplitude zero com um dia só", () => {
    expect(weekdayProfile([entry({ date: "2026-08-03" })]).amplitude).toBe(0);
  });

  it("conta ocorrências por dia da semana", () => {
    const profile = weekdayProfile([
      entry({ date: "2026-08-03", hours: 6 }),
      entry({ date: "2026-08-10", hours: 4 }),
    ]);
    expect(profile.counts[0]).toBe(2);
    expect(profile.averages[0]).toBe(5);
  });
});
