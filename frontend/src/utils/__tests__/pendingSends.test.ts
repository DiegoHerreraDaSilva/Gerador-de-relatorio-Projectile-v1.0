import { describe, expect, it } from "vitest";
import type { ProjectSendStatusRow } from "../../store/useManagementStore";
import { LATE_AFTER_DAYS, daysSinceMonthEnd, summarizePending } from "../pendingSends";

const TODAY = new Date(2026, 8, 30); // 30/09/2026

function row(patch: Partial<ProjectSendStatusRow>): ProjectSendStatusRow {
  return {
    month: "2026-08",
    project_id: "p1",
    project_name: "Projeto 1",
    client: "ACME",
    status: "none",
    missing_pacotes: [],
    manual_send_marker_id: null,
    manual_send_marker_removable: false,
    ...patch,
  };
}

describe("daysSinceMonthEnd", () => {
  it("conta dias corridos desde o último dia do mês", () => {
    expect(daysSinceMonthEnd("2026-08", TODAY)).toBe(30); // 31/08 -> 30/09
    expect(daysSinceMonthEnd("2026-02", new Date(2026, 2, 5))).toBe(5); // fevereiro de 28 dias
    expect(daysSinceMonthEnd("2028-02", new Date(2028, 2, 1))).toBe(1); // bissexto: 29/02
  });

  it("mês em andamento (ou futuro) não tem atraso", () => {
    expect(daysSinceMonthEnd("2026-09", TODAY)).toBeLessThan(1);
    expect(daysSinceMonthEnd("2026-10", TODAY)).toBeLessThan(1);
  });

  it("mês malformado vale 0", () => {
    expect(daysSinceMonthEnd("agosto", TODAY)).toBe(0);
  });
});

describe("summarizePending", () => {
  it("só conta nada enviado ou parcial; enviado e fechado ficam de fora", () => {
    const summary = summarizePending(
      [
        row({ project_id: "a", status: "none" }),
        row({ project_id: "b", status: "partial", missing_pacotes: ["x", "y"] }),
        row({ project_id: "c", status: "sent" }),
        row({ project_id: "d", status: "closed" }),
      ],
      null,
      TODAY,
    );
    expect(summary.total).toBe(2);
    expect(summary.clients[0].items.map((i) => i.project_id).sort()).toEqual(["a", "b"]);
  });

  it("o mês corrente ainda está em andamento: não é pendência", () => {
    expect(summarizePending([row({ month: "2026-09" })], null, TODAY).total).toBe(0);
  });

  it("respeita os meses filtrados (conjunto vazio = todos)", () => {
    const rows = [row({ month: "2026-07", project_id: "a" }), row({ month: "2026-08", project_id: "b" })];
    expect(summarizePending(rows, new Set(["2026-08"]), TODAY).total).toBe(1);
    expect(summarizePending(rows, new Set(), TODAY).total).toBe(2);
  });

  it("atrasado só depois de LATE_AFTER_DAYS dias", () => {
    const fresh = summarizePending([row({ month: "2026-08" })], null, new Date(2026, 8, 5)); // 5 dias
    expect(fresh.clients[0].items[0].late).toBe(false);
    expect(fresh.late).toBe(0);
    const edge = summarizePending([row({ month: "2026-08" })], null, new Date(2026, 8, LATE_AFTER_DAYS + 1));
    expect(edge.clients[0].items[0].daysLate).toBe(LATE_AFTER_DAYS + 1);
    expect(edge.late).toBe(1);
  });

  it("agrupa por cliente e ordena o mais atrasado primeiro", () => {
    const summary = summarizePending(
      [
        row({ client: "Beta", project_id: "b1", month: "2026-08" }),
        row({ client: "Alfa", project_id: "a1", month: "2026-07" }),
        row({ client: "Alfa", project_id: "a2", month: "2026-08" }),
      ],
      null,
      TODAY,
    );
    expect(summary.clients.map((c) => c.client)).toEqual(["Alfa", "Beta"]);
    expect(summary.clients[0].items.map((i) => i.project_id)).toEqual(["a1", "a2"]); // julho (mais velho) antes
    expect(summary.clients[0].oldestDays).toBe(daysSinceMonthEnd("2026-07", TODAY));
    expect(summary.clients[0].lateCount).toBe(2);
    expect(summary).toMatchObject({ total: 3, late: 3 });
  });

  it("sem linhas, sem pendência", () => {
    expect(summarizePending([], null, TODAY)).toEqual({ clients: [], total: 0, late: 0 });
  });
});
