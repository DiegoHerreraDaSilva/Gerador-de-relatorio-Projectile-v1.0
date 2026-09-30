import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ROLLING_PERIOD,
  applyLastMonthDefault,
  lastMonthKey,
  periodOptionsFor,
  useManagementStore,
} from "../useManagementStore";

describe("periodOptionsFor", () => {
  it("gerente vê todos os anos desde 2008, do mais novo pro mais antigo", () => {
    const options = periodOptionsFor(true, 2026);
    expect(options[0]).toBe(ROLLING_PERIOD);
    expect(options[1]).toBe("2026");
    expect(options[options.length - 1]).toBe("2008");
    expect(options).toHaveLength(1 + 19);
  });

  it("coordenador vê só os últimos 12 meses e o ano atual", () => {
    expect(periodOptionsFor(false, 2026)).toEqual([ROLLING_PERIOD, "2026"]);
  });
});

describe("mês passado como padrão do Diagnóstico", () => {
  const load = vi.fn();
  beforeEach(() => {
    load.mockReset();
    useManagementStore.setState({ period: ROLLING_PERIOD, selectedMonths: [], load });
  });

  it("lastMonthKey: mês anterior, inclusive na virada do ano", () => {
    expect(lastMonthKey(new Date(2026, 8, 30))).toBe("2026-08");
    expect(lastMonthKey(new Date(2026, 0, 15))).toBe("2025-12");
    expect(lastMonthKey(new Date(2026, 2, 31))).toBe("2026-02");
  });

  it("aplica quando ninguém escolheu nada e busca de novo", () => {
    const { applied } = applyLastMonthDefault(new Date(2026, 8, 30));
    expect(applied).toBe(true);
    expect(useManagementStore.getState().selectedMonths).toEqual(["2026-08"]);
    expect(load).toHaveBeenCalledWith(true);
  });

  it("não mexe se já há competência escolhida ou outro período (respeita a escolha)", () => {
    useManagementStore.setState({ selectedMonths: ["2026-05"] });
    expect(applyLastMonthDefault(new Date(2026, 8, 30)).applied).toBe(false);
    expect(useManagementStore.getState().selectedMonths).toEqual(["2026-05"]);

    useManagementStore.setState({ period: "2025", selectedMonths: [] });
    expect(applyLastMonthDefault(new Date(2026, 8, 30)).applied).toBe(false);
    expect(useManagementStore.getState().selectedMonths).toEqual([]);
  });

  it("ao sair, desfaz só se a competência continua a aplicada (o Painel não herda o recorte)", () => {
    const { restore } = applyLastMonthDefault(new Date(2026, 8, 30));
    restore();
    expect(useManagementStore.getState().selectedMonths).toEqual([]);

    const again = applyLastMonthDefault(new Date(2026, 8, 30));
    useManagementStore.setState({ selectedMonths: ["2026-03", "2026-04"] }); // o usuário mudou na tela
    again.restore();
    expect(useManagementStore.getState().selectedMonths).toEqual(["2026-03", "2026-04"]);
  });
});
