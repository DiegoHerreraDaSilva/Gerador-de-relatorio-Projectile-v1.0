import { describe, it, expect } from "vitest";
import { computeGroupTotals, computeGrandTotalFor, computeGrandBruto } from "../calc";
import type { Group, Activity } from "../../api/types";

// Estes testes existem pra travar a fórmula que precisa espelhar EXATAMENTE
// backend/app/generator.py:_build_groups_xml:
//   bruto_total = sum(a.hours for a in real_activities)              (linha 335)
//   resultado (célula C, via fórmula "=E*F")   = bruto_total * group.performance   (linha 360)
// Atividades "extra" (hours None/null/undefined) NUNCA entram na soma do bruto —
// elas só aparecem no relatório como linhas de texto sem valor.
// Se alguém alterar computeGroupTotals sem também alterar generator.py (ou
// vice-versa), o número mostrado na tela da UI diverge do que é impresso no
// .xlsx entregue ao cliente.

function activity(hours: number | null | undefined, overrides: Partial<Activity> = {}): Activity {
  return {
    id: overrides.id ?? "a",
    description: overrides.description ?? "atividade",
    // cast: no runtime o código defende explicitamente contra `undefined`
    // (`a.hours !== null && a.hours !== undefined`) mesmo o tipo declarado
    // sendo `number | null` — provavelmente por dados vindos de fontes menos
    // estritas (JSON antigo, import). Testamos os dois casos de propósito.
    hours: hours as number | null,
    extra: overrides.extra ?? false,
  };
}

function group(performance: number, hours: Array<number | null | undefined>): Group {
  return {
    id: "g",
    name: "Grupo",
    performance,
    activities: hours.map((h, i) => activity(h, { id: `a${i}` })),
  };
}

describe("computeGroupTotals", () => {
  it("soma o bruto de duas atividades reais e aplica a performance do grupo", () => {
    // bruto = 10 + 5.5 = 15.5 ; resultado = 15.5 * 0.9 (cf. generator.py E*F)
    const g = group(0.9, [10, 5.5]);
    const totals = computeGroupTotals(g);
    expect(totals.bruto).toBe(15.5);
    expect(totals.performance).toBe(0.9);
    expect(totals.resultado).toBeCloseTo(13.95, 9);
    expect(totals.hasRealActivities).toBe(true);
  });

  it("ignora atividades com hours null OU undefined na soma do bruto (tratadas como 0)", () => {
    const g = group(1, [8, null, 2, undefined]);
    const totals = computeGroupTotals(g);
    expect(totals.bruto).toBe(10);
    expect(totals.resultado).toBe(10);
    expect(totals.hasRealActivities).toBe(true);
  });

  it("retorna bruto=0, resultado=0 e hasRealActivities=false quando só há atividades extra (null/undefined)", () => {
    const g = group(0.85, [null, undefined]);
    const totals = computeGroupTotals(g);
    expect(totals.bruto).toBe(0);
    expect(totals.resultado).toBe(0);
    expect(totals.hasRealActivities).toBe(false);
  });

  it("grupo sem nenhuma atividade também é bruto=0 / hasRealActivities=false", () => {
    const g = group(1, []);
    const totals = computeGroupTotals(g);
    expect(totals.bruto).toBe(0);
    expect(totals.hasRealActivities).toBe(false);
  });

  it("performance 0 zera o resultado mesmo com bruto positivo", () => {
    const g = group(0, [10, 20]);
    const totals = computeGroupTotals(g);
    expect(totals.bruto).toBe(30);
    expect(totals.resultado).toBe(0);
    expect(totals.hasRealActivities).toBe(true);
  });
});

describe("computeGrandTotalFor", () => {
  it("soma o resultado de múltiplos grupos, pulando grupos sem atividades reais", () => {
    const g1 = group(0.9, [10, 5.5]); // resultado ~= 13.95
    const g2 = group(1, [8, null, 2]); // bruto=10, resultado=10
    const g3 = group(0.85, [null, undefined]); // hasRealActivities=false -> não conta
    const total = computeGrandTotalFor([g1, g2, g3]);
    expect(total).toBeCloseTo(23.95, 9);
  });

  it("retorna 0 para lista vazia de grupos", () => {
    expect(computeGrandTotalFor([])).toBe(0);
  });

  it("grupo só com atividades extra soma 0 (equivalente a ser pulado)", () => {
    const g1 = group(1, [10]);
    const gExtraOnly = group(2, [null]); // bruto=0 -> resultado 0*2=0 de qualquer forma
    expect(computeGrandTotalFor([g1, gExtraOnly])).toBe(10);
  });
});

describe("computeGrandBruto", () => {
  it("soma o bruto de todos os grupos, mesmo os sem atividades reais (contam 0)", () => {
    const g1 = group(0.9, [10, 5.5]); // bruto 15.5
    const g2 = group(1, [8, null, 2]); // bruto 10
    const g3 = group(0.85, [null, undefined]); // bruto 0
    expect(computeGrandBruto([g1, g2, g3])).toBe(25.5);
  });

  it("retorna 0 para lista vazia de grupos", () => {
    expect(computeGrandBruto([])).toBe(0);
  });
});
