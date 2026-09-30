import { describe, expect, it } from "vitest";
import { HINT_MAX_VALUES, hintText } from "../hint";

describe("hintText", () => {
  it("monta 'Rótulo: valor'", () => {
    expect(hintText("Período", ["Agosto/2026"])).toBe("Período: Agosto/2026");
  });

  it("sem rótulo devolve só o valor", () => {
    expect(hintText(undefined, ["Mercedes"])).toBe("Mercedes");
  });

  it("lista todos os valores de um filtro de vários (o botão só diz 'N selecionados')", () => {
    expect(hintText("Clientes", ["Mercedes", "Lauer", "MBB"])).toBe("Clientes: Mercedes, Lauer, MBB");
  });

  it("corta a lista longa e diz quantos ficaram de fora", () => {
    const values = Array.from({ length: HINT_MAX_VALUES + 3 }, (_, i) => `C${i}`);
    const text = hintText("Clientes", values);
    expect(text.endsWith("e mais 3")).toBe(true);
    expect(text).toContain(`C${HINT_MAX_VALUES - 1}`);
    expect(text).not.toContain(`C${HINT_MAX_VALUES},`);
  });

  it("sem valor usa o texto de vazio, e sem nada devolve só o rótulo", () => {
    expect(hintText("Cliente", [""], "Selecione um cliente")).toBe("Cliente: Selecione um cliente");
    expect(hintText("Cliente", [])).toBe("Cliente");
    expect(hintText(undefined, [])).toBe("");
  });

  it("ignora valores em branco no meio", () => {
    expect(hintText("Projetos", ["A", "  ", "B"])).toBe("Projetos: A, B");
  });
});
