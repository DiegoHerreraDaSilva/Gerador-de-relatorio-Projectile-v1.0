import { describe, expect, it } from "vitest";
import { buildPeriodLabel, getReportYearOptions, lastClosedMonthsRange, parsePeriodLabelForControls } from "../period";

describe("getReportYearOptions", () => {
  it("lista de 2008 até o ano atual, do mais recente para o mais antigo", () => {
    expect(getReportYearOptions(2026)).toEqual([
      "2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017",
      "2016", "2015", "2014", "2013", "2012", "2011", "2010", "2009", "2008",
    ]);
  });
});

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

describe("parsePeriodLabelForControls", () => {
  it("preserva um intervalo no mesmo ano durante o rerender", () => {
    expect(parsePeriodLabelForControls("Agosto a Setembro/2026")).toEqual({
      startMonth: "Agosto",
      startYear: "2026",
      endMonth: "Setembro",
      endYear: "2026",
    });
  });

  it("continua aceitando intervalos entre anos salvos por versões anteriores", () => {
    expect(parsePeriodLabelForControls("Dezembro/2025 a Fevereiro/2026")).toEqual({
      startMonth: "Dezembro",
      startYear: "2025",
      endMonth: "Fevereiro",
      endYear: "2026",
    });
  });

  it("usa o mês final separado ao iniciar um intervalo a partir de mês único", () => {
    expect(parsePeriodLabelForControls("Agosto/2026", "Outubro/2026")).toEqual({
      startMonth: "Agosto",
      startYear: "2026",
      endMonth: "Outubro",
      endYear: "2026",
    });
  });
});
