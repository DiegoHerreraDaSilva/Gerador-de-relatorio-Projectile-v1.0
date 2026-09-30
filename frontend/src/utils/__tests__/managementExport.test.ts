import { describe, expect, it } from "vitest";
import type { MonthRow } from "../../store/useManagementStore";
import { buildMonthlyTable, formatDelta, periodTitle, previousMonthDeltas } from "../managementExport";

function month(patch: Partial<MonthRow> & { month: string }): MonthRow {
  return {
    worked_hours: 100,
    billed_hours: 110,
    billed_hours_source: "auto",
    perf_hours: 10,
    perf_kpi_pct: 0.1,
    elaboration_days: 4,
    elaboration_days_source: "auto",
    nonbillable_hours: 20,
    nonbillable_kpi_pct: 0.2,
    ...patch,
  };
}

describe("periodTitle", () => {
  it("rolling vira 'Últimos 12 meses'; ano fica como está", () => {
    expect(periodTitle("rolling", [])).toBe("Últimos 12 meses");
    expect(periodTitle("2026", [])).toBe("2026");
  });

  it("competência: um mês, ou do primeiro ao último em ordem", () => {
    expect(periodTitle("rolling", ["2026-08"])).toBe("2026-08");
    expect(periodTitle("rolling", ["2026-08", "2026-06", "2026-07"])).toBe("2026-06 a 2026-08");
  });
});

describe("buildMonthlyTable", () => {
  it("meses em ordem cronológica, percentuais em pontos e números como números", () => {
    const table = buildMonthlyTable(
      [month({ month: "2026-08", perf_kpi_pct: 0.123 }), month({ month: "2026-07", worked_hours: 80.456 })],
      "Painel",
    );
    expect(table.rows.map((r) => r[0])).toEqual(["2026-07", "2026-08"]);
    expect(table.rows[0][1]).toBe(80.46);
    expect(table.rows[1][4]).toBe(12.3); // fração 0,123 -> 12,3 pontos
    expect(table.columns).toHaveLength(table.column_types?.length ?? -1);
    expect(table.rows.every((r) => r.length === table.columns.length)).toBe(true);
  });

  it("totais seguem a regra da tela: faturadas e performance só somam meses com 'Faturadas' preenchida", () => {
    const table = buildMonthlyTable(
      [
        month({ month: "2026-06", worked_hours: 100, billed_hours: 110 }),
        month({ month: "2026-07", worked_hours: 200, billed_hours: null, perf_hours: null, perf_kpi_pct: null }),
      ],
      "Painel",
    );
    const totals = table.totals as (string | number | null)[];
    expect(totals[0]).toBe("Total");
    expect(totals[1]).toBe(300); // trabalhadas soma todos os meses
    expect(totals[2]).toBe(110); // faturadas só o mês preenchido
    expect(totals[3]).toBe(10); // 110 - 100
    expect(totals[4]).toBe(10); // 10 / 100 = 10%
  });

  it("valor ausente continua vazio (não vira 0) e o filtro de Pessoa deixa faturado/performance/prazo em branco", () => {
    const row = month({
      month: "2026-08",
      billed_hours: null,
      perf_hours: null,
      perf_kpi_pct: null,
      elaboration_days: null,
    });
    const table = buildMonthlyTable([row], "Painel", true);
    expect(table.rows[0].slice(2, 5)).toEqual([null, null, null]);
    expect(table.rows[0][7]).toBeNull();
    const totals = table.totals as (string | number | null)[];
    expect([totals[2], totals[3], totals[4], totals[7]]).toEqual([null, null, null, null]);
  });

  it("sem nenhuma linha gera tabela vazia com totais zerados, sem quebrar", () => {
    const table = buildMonthlyTable([], "Painel");
    expect(table.rows).toEqual([]);
    expect((table.totals as unknown[])[1]).toBe(0);
  });
});

describe("previousMonthDeltas", () => {
  it("compara com o mês calendário anterior (horas em %, performance em pontos)", () => {
    const deltas = previousMonthDeltas([
      month({ month: "2026-07", worked_hours: 100, perf_kpi_pct: 0.1 }),
      month({ month: "2026-08", worked_hours: 120, perf_kpi_pct: 0.14 }),
    ]);
    expect(deltas.get("2026-08")).toEqual({ workedPct: 20, perfPoints: 4 });
  });

  it("primeiro mês, mês anterior ausente ou zerado não viram 0: ficam nulos", () => {
    const deltas = previousMonthDeltas([
      month({ month: "2026-05" }),
      month({ month: "2026-07", worked_hours: 100 }), // junho não existe
      month({ month: "2026-09", worked_hours: 50 }),
      month({ month: "2026-08", worked_hours: 0 }),
    ]);
    expect(deltas.get("2026-05")).toEqual({ workedPct: null, perfPoints: null });
    expect(deltas.get("2026-07")).toEqual({ workedPct: null, perfPoints: null });
    expect(deltas.get("2026-09")?.workedPct).toBeNull(); // agosto foi 0
  });

  it("vira o ano: janeiro compara com dezembro", () => {
    const deltas = previousMonthDeltas([
      month({ month: "2025-12", worked_hours: 50 }),
      month({ month: "2026-01", worked_hours: 75 }),
    ]);
    expect(deltas.get("2026-01")?.workedPct).toBe(50);
  });

  it("performance sem um dos dois meses não compara", () => {
    const deltas = previousMonthDeltas([
      month({ month: "2026-07", perf_kpi_pct: null }),
      month({ month: "2026-08", perf_kpi_pct: 0.1 }),
    ]);
    expect(deltas.get("2026-08")?.perfPoints).toBeNull();
  });
});

describe("formatDelta", () => {
  it("seta, número e unidade", () => {
    expect(formatDelta(5.25, "%")).toBe("▲ 5,3%");
    expect(formatDelta(-3.1, "pts")).toBe("▼ 3,1 pts");
    expect(formatDelta(0, "%")).toBe("= 0");
    expect(formatDelta(null, "%")).toBe("");
  });
});
