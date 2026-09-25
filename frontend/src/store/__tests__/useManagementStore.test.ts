import { describe, expect, it } from "vitest";
import { ROLLING_PERIOD, periodOptionsFor } from "../useManagementStore";

describe("periodOptionsFor", () => {
  it("gerente vê todos os anos desde 2008, do mais novo pro mais antigo", () => {
    const options = periodOptionsFor(true, 2026);
    expect(options[0]).toBe(ROLLING_PERIOD);
    expect(options[1]).toBe("2026");
    expect(options[options.length - 1]).toBe("2008");
    expect(options).toHaveLength(1 + 19);
  });

  it("coordenador vê só os últimos 12 meses e o ano passado", () => {
    expect(periodOptionsFor(false, 2026)).toEqual([ROLLING_PERIOD, "2025"]);
  });
});
