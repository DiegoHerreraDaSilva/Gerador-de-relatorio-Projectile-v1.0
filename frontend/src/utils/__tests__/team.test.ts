import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchTeam, gapSummary, teamMonthOptions } from "../team";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      return { ok: status >= 200 && status < 300, status, json: async () => body };
    }),
  );
  return calls;
}

describe("teamMonthOptions", () => {
  it("o mês atual e os 5 anteriores, do mais novo ao mais antigo", () => {
    expect(teamMonthOptions(new Date(2026, 8, 30))).toEqual([
      "2026-09",
      "2026-08",
      "2026-07",
      "2026-06",
      "2026-05",
      "2026-04",
    ]);
  });

  it("vira o ano", () => {
    expect(teamMonthOptions(new Date(2026, 1, 10), 4)).toEqual(["2026-02", "2026-01", "2025-12", "2025-11"]);
  });
});

describe("gapSummary", () => {
  it("formata dia/mês, do mais recente ao mais antigo, com 'e' antes do último", () => {
    expect(gapSummary(["2026-09-29"])).toBe("29/09");
    expect(gapSummary(["2026-09-29", "2026-09-28"])).toBe("29/09 e 28/09");
    expect(gapSummary(["2026-09-29", "2026-09-28", "2026-09-25"])).toBe("29/09, 28/09 e 25/09");
  });

  it("corta a lista longa e diz quantos ficaram de fora", () => {
    const days = Array.from({ length: 9 }, (_, i) => `2026-09-${String(29 - i).padStart(2, "0")}`);
    expect(gapSummary(days, 3)).toBe("29/09, 28/09, 27/09 e mais 6");
  });

  it("sem dias, texto vazio", () => {
    expect(gapSummary([])).toBe("");
  });
});

describe("fetchTeam", () => {
  it("pede o mês e devolve o time", async () => {
    const team = { month: "2026-09", people: [], totals: { people: 0, with_gaps: 0, hours: 0, overloaded: 0 } };
    const calls = stubFetch(200, team);
    await expect(fetchTeam("2026-09")).resolves.toEqual(team);
    expect(calls[0]).toBe("/my-hours/team?month=2026-09");
  });

  it("400 usa a mensagem do servidor", async () => {
    stubFetch(400, { detail: "Esse mês ainda não começou." });
    await expect(fetchTeam("2027-01")).rejects.toThrow("ainda não começou");
  });

  it("401, 403 e erro do servidor viram mensagem pronta pra tela", async () => {
    stubFetch(401, {});
    await expect(fetchTeam("2026-09")).rejects.toThrow("Sessão expirada");
    stubFetch(403, {});
    await expect(fetchTeam("2026-09")).rejects.toThrow("não tem acesso");
    stubFetch(502, {});
    await expect(fetchTeam("2026-09")).rejects.toThrow("Tenta de novo");
  });
});
