import { describe, expect, it } from "vitest";
import {
  buildPeriodLabel,
  getReportYearOptions,
  lastClosedMonthsRange,
  monthOptionsFor,
  normalizeRange,
  parsePeriodLabelForControls,
  periodWindow,
  reportYearOptionsFor,
} from "../period";

describe("getReportYearOptions", () => {
  it("lista de 2008 até o ano atual, do mais recente para o mais antigo", () => {
    expect(getReportYearOptions(2026)).toEqual([
      "2026",
      "2025",
      "2024",
      "2023",
      "2022",
      "2021",
      "2020",
      "2019",
      "2018",
      "2017",
      "2016",
      "2015",
      "2014",
      "2013",
      "2012",
      "2011",
      "2010",
      "2009",
      "2008",
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

describe("janela de quem não é gerente (últimos 12 meses e o ano atual)", () => {
  it("em setembro/2026: outubro/2025 a dezembro/2026", () => {
    const today = new Date(2026, 8, 28);
    expect(periodWindow(today)).toEqual({ startYear: 2025, startMonth: 9, endYear: 2026 });
    expect(reportYearOptionsFor(false, today)).toEqual(["2026", "2025"]);
    expect(monthOptionsFor(false, "2025", today)).toEqual(["Outubro", "Novembro", "Dezembro"]);
    expect(monthOptionsFor(false, "2026", today)).toHaveLength(12);
    expect(monthOptionsFor(false, "2024", today)).toEqual([]);
  });

  it("em dezembro a janela é só o ano atual; gerente não tem limite", () => {
    const today = new Date(2026, 11, 10);
    expect(reportYearOptionsFor(false, today)).toEqual(["2026"]);
    expect(reportYearOptionsFor(true, today)).toHaveLength(19);
    expect(monthOptionsFor(true, "2010", today)).toHaveLength(12);
  });
});

describe("normalizeRange (mês e ano inicial, mês e ano final)", () => {
  const today = new Date(2026, 8, 28);
  const range = (startMonth: string, startYear: string, endMonth: string, endYear: string) => ({
    startMonth,
    startYear,
    endMonth,
    endYear,
  });

  it("deixa como está um período válido, inclusive cruzando o ano", () => {
    expect(normalizeRange(range("Dezembro", "2025", "Fevereiro", "2026"), true, today)).toEqual(
      range("Dezembro", "2025", "Fevereiro", "2026"),
    );
  });

  it("o fim nunca fica antes do início: vira o início", () => {
    expect(normalizeRange(range("Agosto", "2026", "Março", "2026"), true, today)).toEqual(
      range("Agosto", "2026", "Agosto", "2026"),
    );
    expect(normalizeRange(range("Março", "2026", "Dezembro", "2025"), true, today)).toEqual(
      range("Março", "2026", "Março", "2026"),
    );
  });

  it("subir o ano inicial acima do final arrasta o final", () => {
    expect(normalizeRange(range("Junho", "2027", "Agosto", "2026"), true, today)).toEqual(
      range("Junho", "2027", "Junho", "2027"),
    );
  });

  it("quem não é gerente: mês fora da janela vai pro primeiro que vale naquele ano", () => {
    // em set/2026 a janela de 2025 é out–dez
    expect(normalizeRange(range("Janeiro", "2025", "Março", "2026"), false, today)).toEqual(
      range("Outubro", "2025", "Março", "2026"),
    );
  });
});
