import { describe, expect, it } from "vitest";
import { sortEvolutionRows } from "../EvolutionChart";
import type { MonthRow } from "../../store/useManagementStore";

function monthRow(month: string): MonthRow {
  return {
    month,
    worked_hours: 10,
    billed_hours: null,
    billed_hours_source: null,
    perf_hours: null,
    perf_kpi_pct: null,
    elaboration_days: null,
    elaboration_days_source: null,
    nonbillable_hours: 0,
    nonbillable_kpi_pct: null,
  };
}

describe("sortEvolutionRows", () => {
  it("ordena os meses cronologicamente da esquerda para a direita", () => {
    const rows = [monthRow("2026-09"), monthRow("2025-12"), monthRow("2026-01")];

    expect(sortEvolutionRows(rows).map((row) => row.month)).toEqual(["2025-12", "2026-01", "2026-09"]);
    expect(rows.map((row) => row.month)).toEqual(["2026-09", "2025-12", "2026-01"]);
  });
});
