import { describe, expect, it } from "vitest";
import { matchesQuery, normalizeForSearch } from "../search";

describe("busca dos dropdowns", () => {
  it("ignora acento e maiúsculas", () => {
    expect(normalizeForSearch("Março")).toBe("marco");
    expect(matchesQuery("Plásticos Mauá", "plasticos maua")).toBe(true);
  });

  it("várias palavras em qualquer ordem", () => {
    expect(matchesQuery("Legislation Package - Estribo 08.2026", "estribo legislation")).toBe(true);
    expect(matchesQuery("Legislation Package - Estribo 08.2026", "estribo lauer")).toBe(false);
  });

  it("busca vazia ou só espaço casa tudo", () => {
    expect(matchesQuery("Qualquer", "")).toBe(true);
    expect(matchesQuery("Qualquer", "   ")).toBe(true);
  });
});
