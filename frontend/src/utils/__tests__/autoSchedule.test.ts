import { describe, expect, it } from "vitest";
import { describeSchedule, formatScheduleAt, type ScheduleInfo } from "../autoSchedule";

const ON: ScheduleInfo = {
  enabled: true, day: 1, time: "06:00", next_at: "2026-10-01T06:00:00-03:00", target: "2026-09", target_label: "Setembro/2026",
};

describe("agendador da geração automática", () => {
  it("lê data e hora do próprio texto, sem depender do fuso do navegador", () => {
    expect(formatScheduleAt("2026-10-01T06:00:00-03:00")).toBe("01/10/2026 às 06:00");
    expect(formatScheduleAt("2027-01-01T23:05:00-03:00")).toBe("01/01/2027 às 23:05");
    expect(formatScheduleAt("lixo")).toBe("lixo");
  });

  it("descreve a próxima geração e o mês que ela vai gerar", () => {
    expect(describeSchedule(ON)).toBe("Próxima geração automática: 01/10/2026 às 06:00 · rascunhos de Setembro/2026.");
  });

  it("desligado avisa que só sai pelo botão", () => {
    expect(describeSchedule({ ...ON, enabled: false })).toMatch(/desligada/);
    expect(describeSchedule({ ...ON, enabled: false })).toMatch(/Gerar rascunhos/);
  });

  it("sem dado não mostra nada", () => {
    expect(describeSchedule(null)).toBe("");
    expect(describeSchedule(undefined)).toBe("");
  });
});
