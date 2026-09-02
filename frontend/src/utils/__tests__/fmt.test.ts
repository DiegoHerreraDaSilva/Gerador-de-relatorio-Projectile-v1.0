import { describe, it, expect } from "vitest";
import { fmtNum, parseLocaleNumber, parseExtraHoursInput } from "../fmt";

describe("fmtNum", () => {
  it("formata número com casa decimal usando vírgula (pt-BR)", () => {
    expect(fmtNum(2.5)).toBe("2,5");
  });

  it("não deixa vírgula sobrando quando o valor é inteiro", () => {
    expect(fmtNum(2)).toBe("2");
    expect(fmtNum(0)).toBe("0");
  });

  it("preserva o sinal negativo", () => {
    expect(fmtNum(-3.5)).toBe("-3,5");
  });

  it("arredonda para 2 casas decimais", () => {
    expect(fmtNum(3.14159)).toBe("3,14");
    expect(fmtNum(10.1)).toBe("10,1");
  });
});

describe("parseLocaleNumber", () => {
  it("interpreta vírgula como separador decimal pt-BR", () => {
    expect(parseLocaleNumber("2,5")).toBe(2.5);
  });

  it("aceita ponto como separador decimal quando não há vírgula", () => {
    expect(parseLocaleNumber("2.5")).toBe(2.5);
  });

  it("ignora espaços nas bordas", () => {
    expect(parseLocaleNumber("  3,25  ")).toBe(3.25);
  });

  it("aceita number diretamente (não-string) via String()+parseFloat", () => {
    expect(parseLocaleNumber(5)).toBe(5);
  });

  it("retorna NaN para texto não numérico", () => {
    expect(Number.isNaN(parseLocaleNumber("abc"))).toBe(true);
  });

  // Comportamento real (não o ideal) documentado aqui de propósito: quando a
  // string tem PONTO e VÍRGULA junto (ex: separador de milhar "1.234,56"), a
  // condição `includes(",") && !includes(".")` é falsa, então a função NÃO
  // troca a vírgula por ponto — cai direto em parseFloat, que para no primeiro
  // caractere inválido (a vírgula) e retorna só a parte antes dela. Ou seja,
  // parseLocaleNumber NÃO faz parsing de separador de milhar pt-BR completo.
  // Uma tarefa futura que queira números tipo "1.234,56" precisa tratar isso
  // separadamente antes de chamar esta função.
  it("NÃO interpreta corretamente separador de milhar junto com vírgula decimal (comportamento atual, não ideal)", () => {
    expect(parseLocaleNumber("1.234,56")).toBe(1.234);
  });
});

describe("parseExtraHoursInput", () => {
  it("retorna null para string vazia", () => {
    expect(parseExtraHoursInput("")).toBeNull();
  });

  it("faz parsing de número pt-BR válido", () => {
    expect(parseExtraHoursInput("2,5")).toBe(2.5);
  });

  it("faz parsing de número inteiro", () => {
    expect(parseExtraHoursInput("3")).toBe(3);
  });

  it("retorna null (não NaN) para texto inválido", () => {
    expect(parseExtraHoursInput("abc")).toBeNull();
  });
});
