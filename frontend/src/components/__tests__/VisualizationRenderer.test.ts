import { describe, expect, it } from "vitest";
import { axisLabel, formatCell, sortRows } from "../analytics/VisualizationRenderer";

describe("axisLabel", () => {
  it("abrevia mês/ano do eixo do gráfico de linha", () => {
    expect(axisLabel("setembro/2025")).toBe("set/25");
    expect(axisLabel("março/2026")).toBe("mar/26");
  });

  it("mantém categorias que não são mês/ano", () => {
    expect(axisLabel("PDF")).toBe("PDF");
    expect(axisLabel("2026-09")).toBe("2026-09");
  });
});

describe("formatCell", () => {
  it("formata pelo tipo da coluna, no padrão brasileiro", () => {
    expect(formatCell(1234.567, "hours")).toBe("1.234,57");
    expect(formatCell(76.9, "percent")).toBe("76,9%");
    expect(formatCell(3, "count")).toBe("3");
    expect(formatCell(1500, "ms")).toBe("1.500 ms");
    expect(formatCell("ACME", "text")).toBe("ACME");
  });

  it("vazio vira travessão, nunca zero inventado", () => {
    expect(formatCell(null, "hours")).toBe("—");
    expect(formatCell("", "text")).toBe("—");
  });
});

describe("sortRows", () => {
  const rows = [
    ["Beta", 3, null],
    ["ACME", 10, -10],
    ["Árvore", 5, 2],
  ];

  it("ordena números e deixa vazio sempre por último", () => {
    expect(sortRows(rows, { column: 2, descending: true }).map((r) => r[0])).toEqual(["Árvore", "ACME", "Beta"]);
    expect(sortRows(rows, { column: 2, descending: false }).map((r) => r[0])).toEqual(["ACME", "Árvore", "Beta"]);
  });

  it("ordena texto sem diferenciar acento e não mexe no original", () => {
    expect(sortRows(rows, { column: 0, descending: false }).map((r) => r[0])).toEqual(["ACME", "Árvore", "Beta"]);
    expect(rows[0][0]).toBe("Beta");
    expect(sortRows(rows, null)).toBe(rows);
  });
});
