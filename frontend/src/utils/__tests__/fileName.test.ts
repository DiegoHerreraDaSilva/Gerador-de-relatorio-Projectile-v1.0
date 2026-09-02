import { describe, it, expect } from "vitest";
import {
  sanitizeForFileName,
  computeDefaultFileName,
  computeDefaultFileNameFor,
} from "../fileName";

describe("sanitizeForFileName", () => {
  it("troca cada caractere proibido em nome de arquivo por hífen", () => {
    // proibidos: \ / : * ? " < > |
    expect(sanitizeForFileName('A/B:C*D?E"F<G>H|I')).toBe("A-B-C-D-E-F-G-H-I");
  });

  it("preserva acentos e espaços (não são sanitizados, só os caracteres de path)", () => {
    expect(sanitizeForFileName("Projeto Configuração Ção")).toBe("Projeto Configuração Ção");
  });

  it("faz trim de espaços nas bordas", () => {
    expect(sanitizeForFileName("  Projeto X  ")).toBe("Projeto X");
  });

  it("trata null/undefined/string vazia como string vazia", () => {
    expect(sanitizeForFileName("")).toBe("");
    expect(sanitizeForFileName(undefined as unknown as string)).toBe("");
    expect(sanitizeForFileName(null as unknown as string)).toBe("");
  });
});

describe("computeDefaultFileName", () => {
  it("monta nome com código do projeto como prefixo, mês/ano com ponto e nome do projeto (pacote único)", () => {
    const name = computeDefaultFileName("08/2026", [
      { projectCode: "PRJ001", projectName: "Projeto Teste" },
    ]);
    expect(name).toBe("PRJ001_Relatório_Horas-08.2026-Projeto Teste");
  });

  it("omite o prefixo (e o underscore) quando o código do projeto é vazio", () => {
    const name = computeDefaultFileName("08/2026", [{ projectCode: "", projectName: "Proj" }]);
    expect(name).toBe("Relatório_Horas-08.2026-Proj");
  });

  it("usa nome genérico no plural quando há mais de um pacote (sem código/nome individual)", () => {
    const name = computeDefaultFileName("08/2026", [
      { projectCode: "A", projectName: "B" },
      { projectCode: "C", projectName: "D" },
    ]);
    expect(name).toBe("Relatórios_Horas-08.2026");
  });

  it("sanitiza caracteres especiais em projectCode e projectName", () => {
    const name = computeDefaultFileName("08/2026", [
      { projectCode: "PRJ/001", projectName: 'Projeto: "Teste" <X>' },
    ]);
    expect(name).toBe("PRJ-001_Relatório_Horas-08.2026-Projeto- -Teste- -X-");
  });
});

describe("computeDefaultFileNameFor", () => {
  it("monta o nome para um pacote específico igual ao caso de pacote único de computeDefaultFileName", () => {
    const name = computeDefaultFileNameFor(
      { projectCode: "PRJ001", projectName: "Projeto Teste" },
      "08/2026"
    );
    expect(name).toBe("PRJ001_Relatório_Horas-08.2026-Projeto Teste");
  });

  it("sanitiza caracteres especiais e barras no código/nome do projeto", () => {
    const name = computeDefaultFileNameFor(
      { projectCode: "PRJ/001", projectName: 'Projeto: "Teste" <X>' },
      "08/2026"
    );
    expect(name).toBe("PRJ-001_Relatório_Horas-08.2026-Projeto- -Teste- -X-");
  });

  it("omite prefixo quando projectCode é vazio", () => {
    const name = computeDefaultFileNameFor({ projectCode: "", projectName: "Proj" }, "08/2026");
    expect(name).toBe("Relatório_Horas-08.2026-Proj");
  });
});
