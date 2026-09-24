import { describe, expect, it } from "vitest";
import { axisLabel } from "../analytics/VisualizationRenderer";

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
