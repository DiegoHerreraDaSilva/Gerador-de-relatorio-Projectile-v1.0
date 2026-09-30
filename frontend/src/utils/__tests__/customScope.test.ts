import { describe, expect, it } from "vitest";
import {
  blockProblem,
  buildCustomScope,
  describeBlock,
  describeBlockView,
  emptyBlock,
  monthToCompetence,
  periodForCompetence,
  periodLabelOf,
  periodProblem,
  type BlockDraft,
  type PeriodDraft,
} from "../customScope";

const AUGUST: PeriodDraft = { startMonth: "Agosto", startYear: "2026", endMonth: "Agosto", endYear: "2026" };

const block = (patch: Partial<BlockDraft>): BlockDraft => ({ ...emptyBlock("b1"), ...patch });

describe("período", () => {
  it("converte mês e ano pra competência", () => {
    expect(monthToCompetence("Agosto", "2026")).toBe("2026-08");
    expect(monthToCompetence("Janeiro", "2025")).toBe("2025-01");
    expect(monthToCompetence("Dezembro", "2025")).toBe("2025-12");
  });

  it("o período da geração personalizada é o mês atual, vindo da competência", () => {
    expect(periodForCompetence("2026-09")).toEqual({
      startMonth: "Setembro",
      startYear: "2026",
      endMonth: "Setembro",
      endYear: "2026",
    });
    expect(periodLabelOf(periodForCompetence("2026-01"))).toBe("Janeiro/2026");
    expect(
      buildCustomScope({
        period: periodForCompetence("2026-09"),
        blocks: [block({ clients: ["ACME"] })],
        splitBy: "nenhum",
        unit: "projeto",
        title: "",
        reviewerLogin: "",
      }).period,
    ).toEqual({ start: "2026-09", end: "2026-09" });
  });

  it("recusa mês final antes do inicial e período longo demais", () => {
    expect(periodProblem(AUGUST)).toBeNull();
    expect(periodProblem({ ...AUGUST, endMonth: "Julho" })).toMatch(/antes do inicial/);
    expect(
      periodProblem({ startMonth: "Dezembro", startYear: "2025", endMonth: "Fevereiro", endYear: "2026" }),
    ).toBeNull();
    expect(periodProblem({ startMonth: "Janeiro", startYear: "2020", endMonth: "Agosto", endYear: "2026" })).toMatch(
      /máximo é 36/,
    );
  });

  it("usa o mesmo rótulo que o backend lê de volta", () => {
    expect(periodLabelOf(AUGUST)).toBe("Agosto/2026");
    expect(periodLabelOf({ ...AUGUST, startMonth: "Julho", endMonth: "Novembro" })).toBe("Julho a Novembro/2026");
    expect(periodLabelOf({ startMonth: "Dezembro", startYear: "2025", endMonth: "Fevereiro", endYear: "2026" })).toBe(
      "Dezembro/2025 a Fevereiro/2026",
    );
  });
});

describe("recorte", () => {
  it("bloco sem filtro nenhum não vale", () => {
    expect(blockProblem(block({}))).toMatch(/Escolha cliente, projeto ou colaborador/);
    expect(blockProblem(block({ clients: ["Mercedes"] }))).toBeNull();
    expect(blockProblem(block({ employeeIds: ["10"] }))).toBeNull();
    expect(blockProblem(block({ projectIds: ["E8"] }))).toBeNull();
  });

  it("pacotes só valem com um único projeto", () => {
    expect(blockProblem(block({ projectIds: ["E8"], packages: ["1546.1-001"] }))).toBeNull();
    expect(blockProblem(block({ projectIds: ["E8", "P1"], packages: ["1546.1-001"] }))).toMatch(/único projeto/);
    expect(blockProblem(block({ clients: ["Mercedes"], packages: ["1546.1-001"] }))).toMatch(/único projeto/);
  });

  it("monta o pedido do servidor e não manda pacote sem exatamente um projeto", () => {
    const scope = buildCustomScope({
      period: { ...AUGUST, startMonth: "Julho" },
      blocks: [
        block({ clients: ["Mercedes"], employeeIds: ["10"] }),
        block({ key: "b2", projectIds: ["E8"], packages: ["1546.1-001"] }),
        block({ key: "b3", projectIds: ["E8", "P1"], packages: ["sobrou de antes"] }),
      ],
      splitBy: "colaborador",
      unit: "pacote",
      title: "  Fechamento  ",
      reviewerLogin: "lucca",
    });
    expect(scope.period).toEqual({ start: "2026-07", end: "2026-08" });
    expect(scope.blocks).toEqual([
      { clients: ["Mercedes"], project_ids: [], packages: [], employee_ids: ["10"] },
      { clients: [], project_ids: ["E8"], packages: ["1546.1-001"], employee_ids: [] },
      { clients: [], project_ids: ["E8", "P1"], packages: [], employee_ids: [] },
    ]);
    expect(scope).toMatchObject({
      split_by: "colaborador",
      package_unit: "pacote",
      title: "Fechamento",
      reviewer_login: "lucca",
    });
  });

  it("título e revisor vazios viram nulo", () => {
    const scope = buildCustomScope({
      period: AUGUST,
      blocks: [block({ clients: ["ACME"] })],
      splitBy: "nenhum",
      unit: "projeto",
      title: "   ",
      reviewerLogin: "",
    });
    expect(scope.title).toBeNull();
    expect(scope.reviewer_login).toBeNull();
  });

  it("descreve o bloco numa frase", () => {
    const employee = (id: string) => ({ "10": "Lucca", "20": "Ana" })[id] ?? id;
    const project = (id: string) => `Projeto ${id}`;
    expect(describeBlock(block({ clients: ["Mercedes"], employeeIds: ["10"] }), employee, project)).toBe(
      "Mercedes · todos os projetos · Lucca",
    );
    expect(
      describeBlock(block({ clients: ["Mercedes"], projectIds: ["E8"], packages: ["a", "b"] }), employee, project),
    ).toBe("Mercedes · Projeto E8 · 2 pacotes");
    expect(describeBlock(block({ employeeIds: ["10", "20", "30"] }), employee, project)).toBe("3 colaboradores");
    expect(describeBlock(block({ clients: ["A", "B", "C"], projectIds: ["1", "2"] }), employee, project)).toBe(
      "3 clientes · 2 projetos",
    );
  });
});

describe("recorte do pedido em nomes", () => {
  const view = (patch: Partial<Parameters<typeof describeBlockView>[0]>) =>
    describeBlockView({ clients: [], projects: [], packages: [], employees: [], ...patch });

  it("só o cliente pega todos os projetos dele", () => {
    expect(view({ clients: ["MERCEDES"] })).toBe("MERCEDES · todos os projetos");
  });

  it("junta cliente, projeto, pacotes e colaboradores", () => {
    expect(view({ clients: ["MERCEDES"], projects: ["Estribo"], packages: ["1546.1-001"], employees: ["Lucca"] })).toBe(
      "MERCEDES · Estribo · pacote: 1546.1-001 · colaborador: Lucca",
    );
    expect(view({ clients: ["A", "B"], projects: ["P1", "P2"], packages: [], employees: ["Ana", "Lucca"] })).toBe(
      "A, B · P1, P2 · colaboradores: Ana, Lucca",
    );
  });

  it("só o colaborador não restringe cliente nem projeto", () => {
    expect(view({ employees: ["Lucca"] })).toBe("qualquer cliente e projeto · colaborador: Lucca");
  });
});
