import { describe, expect, it } from "vitest";
import { buildPeriodLabel, lastClosedMonthsRange } from "../period";

describe("buildPeriodLabel", () => {
  it("colapsa pra mês único quando início e fim são o mesmo mês/ano", () => {
    expect(buildPeriodLabel("Julho", "2026", "Julho", "2026")).toBe("Julho/2026");
  });

  it("mesmo ano: só o ano do fim aparece, junto com 'a'", () => {
    expect(buildPeriodLabel("Julho", "2026", "Novembro", "2026")).toBe("Julho a Novembro/2026");
  });

  it("cruzando ano: os dois meses vêm com o próprio ano", () => {
    expect(buildPeriodLabel("Dezembro", "2025", "Fevereiro", "2026")).toBe("Dezembro/2025 a Fevereiro/2026");
  });
});

describe("lastClosedMonthsRange", () => {
  it("últimos 3 meses fechados nunca incluem o mês corrente", () => {
    const now = new Date(2026, 8, 21); // 21/setembro/2026 (mês 8 = setembro, 0-indexado)

    const range = lastClosedMonthsRange(3, now);

    expect(range).toEqual({ startMonth: "Junho", startYear: "2026", endMonth: "Agosto", endYear: "2026" });
  });

  it("cruza o ano quando os 3 meses fechados incluem dezembro do ano anterior", () => {
    const now = new Date(2026, 1, 10); // 10/fevereiro/2026

    const range = lastClosedMonthsRange(3, now);

    expect(range).toEqual({ startMonth: "Novembro", startYear: "2025", endMonth: "Janeiro", endYear: "2026" });
  });
});
