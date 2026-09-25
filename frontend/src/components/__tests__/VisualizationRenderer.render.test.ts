import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { AnalyticsTableView, KpiGrid, VisualizationRenderer } from "../analytics/VisualizationRenderer";
import type { AnalyticsTable, Visualization } from "../../store/useAnalyticsChatStore";

/** Cada tipo do contrato (`backend/app/analytics/cross_output.py`) renderiza
 * sem erro e mostra o que importa — sem navegador, HTML estático. */
const render = (v: Visualization) => renderToStaticMarkup(createElement(VisualizationRenderer, { visualization: v }));

describe("VisualizationRenderer", () => {
  it("barras empilhadas com legenda e série 'Outros'", () => {
    const html = render({
      type: "horizontal_bar", stacked: true, title: "Horas por cliente e colaborador", unit: "h",
      categories: ["ACME", "Beta"],
      series: [{ name: "Ana", data: [13, 0] }, { name: "Outros", data: [2, 3], tail: true }],
    });
    expect(html).toContain("achat-hbar-seg achat-s0");
    expect(html).toContain("achat-s-tail");
    expect(html).toContain("15 h"); // total da barra empilhada
    expect(html).toContain("achat-legend");
  });

  it("barras agrupadas (várias medidas) e negativo divergente", () => {
    const grouped = render({
      type: "horizontal_bar", title: "Trabalhadas x Faturadas", unit: "h", categories: ["P1"],
      series: [{ name: "Trabalhadas", data: [10] }, { name: "Faturadas", data: [9] }],
    });
    expect(grouped).toContain("is-grouped");
    expect(grouped).toContain("10 h · 9 h");
    const diverging = render({
      type: "horizontal_bar", title: "Variação", unit: "h", categories: ["A", "B"],
      series: [{ name: "Variação", data: [5, -3] }],
    });
    expect(diverging).toContain("is-diverging");
    expect(diverging).toContain("+5 h");
  });

  it("linha multissérie com falha no meio não inventa zero", () => {
    const html = render({
      type: "line", title: "Performance por mês", unit: "%", categories: ["julho/2026", "agosto/2026", "setembro/2026"],
      series: [{ name: "A", data: [10, null, 12] }, { name: "B", data: [-5, 4, 3] }],
    });
    expect(html).toContain("jul/26");
    // A tem só pontos isolados (null no meio) → nenhuma polyline pra A; B tem uma
    expect((html.match(/<polyline/g) ?? []).length).toBe(1);
  });

  it("linha tem eixo Y com marcas redondas, grade e unidade", () => {
    const html = render({
      type: "line", title: "Horas por mês", unit: "h", categories: ["julho/2026", "agosto/2026"],
      series: [{ name: "A", data: [120, 387.4] }, { name: "B", data: [80, 200] }],
    });
    for (const tick of [">0<", ">100<", ">200<", ">300<", ">400<"]) expect(html).toContain(tick);
    expect(html).toContain("achat-line-grid");
    expect(html).toContain("achat-line-unit");
  });

  it("barras verticais com eixo Y e negativo descendo do zero", () => {
    const html = render({
      type: "bar", title: "Performance — julho x agosto", unit: "%", categories: ["julho/2026", "agosto/2026"],
      series: [{ name: "Performance", data: [-11.5, 8] }],
    });
    expect(html).toContain("achat-vaxis-tick");
    expect(html).toContain("achat-vgrid is-zero");
    expect(html).toContain("has-negative");
    expect(html).toMatch(/achat-vbar-fill\s+is-negative" style="top:/);
    expect(html).toContain("-11,5%");
  });

  it("rosca com participação e fatia de 100%", () => {
    const html = render({
      type: "donut", title: "Horas por tipo", unit: "h", categories: ["Faturável", "Não faturável"],
      series: [{ name: "Horas", data: [30, 10] }],
    });
    expect(html).toContain("75%");
    expect(html).toContain("40 h");
    const full = render({ type: "donut", title: "x", unit: "h", categories: ["Só"], series: [{ name: "H", data: [5] }] });
    expect(full).toContain("<circle class=\"achat-donut-arc");
  });

  it("mapa de calor com vazio e negativo", () => {
    const html = render({
      type: "heatmap", title: "Horas por colaborador e mês", unit: "h",
      rows: ["Ana", "Bruno"], columns: ["agosto/2026", "setembro/2026"], values: [[5, 8], [null, -2]],
    });
    expect(html).toContain("ago/26");
    expect(html).toContain("—");
    expect(html).toContain("var(--bad)");
  });

  it("vários KPIs lado a lado", () => {
    const html = renderToStaticMarkup(createElement(KpiGrid, {
      items: [{ type: "kpi", title: "Faturadas — agosto/2026", value: 2728.82, unit: "h" }],
    }));
    expect(html).toContain("Faturadas");
    expect(html).toContain("2.728,8");
  });
});

describe("AnalyticsTableView", () => {
  it("formata por tipo de coluna, mostra total e botão de Excel", () => {
    const table: AnalyticsTable = {
      title: "Cliente — agosto/2026", columns: ["Cliente", "Horas", "% do total"],
      column_types: ["text", "hours", "percent"], rows: [["ACME", 1234.5, 76.9]],
      totals: ["Total", 1234.5, 100], truncated: false,
    };
    const html = renderToStaticMarkup(createElement(AnalyticsTableView, { table, defaultOpen: true }));
    expect(html).toContain("1.234,5");
    expect(html).toContain("76,9%");
    expect(html).toContain("<tfoot>");
    expect(html).toContain("Baixar Excel");
    expect(html).toContain("open=\"\"");
  });
});

describe("paleta de séries", () => {
  it("nunca repete cor: da 6ª série em diante vai pro cinza de Outros", () => {
    const html = render({
      type: "line", title: "Horas", unit: "h", categories: ["julho/2026", "agosto/2026"],
      series: Array.from({ length: 7 }, (_, i) => ({ name: `P${i}`, data: [i, i + 1] })),
    });
    for (let i = 0; i < 5; i++) expect(html).toContain(`achat-s${i}`);
    expect(html).not.toContain("achat-s5");
    expect((html.match(/achat-s-tail/g) ?? []).length).toBeGreaterThanOrEqual(2);
  });
});
