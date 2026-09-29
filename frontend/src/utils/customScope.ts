import { MESES_PT } from "../store/useReportStore";
import type { CustomBlockInput, CustomScopeInput, CustomSplit, CustomUnit } from "../store/useAutoGenerationStore";
import { buildPeriodLabel } from "./period";

/** Montagem e conferência do recorte da geração personalizada, sem tela:
 * o modal só guarda o que o gerente marcou e chama estas funções. Espelha as
 * regras de `backend/app/auto_generation/custom.py` (o backend confere de
 * novo — isto só evita mandar um pedido que já se sabe inválido). */

export type BlockDraft = {
  // chave estável da linha (o bloco não tem id no servidor)
  key: string;
  clients: string[];
  projectIds: string[];
  packages: string[];
  employeeIds: string[];
};

export type PeriodDraft = { startMonth: string; startYear: string; endMonth: string; endYear: string };

export const MAX_MONTHS = 36;

/** "2026-09" → Setembro/2026 como controles (o período da geração personalizada é sempre o mês atual). */
export function periodForCompetence(competence: string): PeriodDraft {
  const [year, month] = competence.split("-");
  const name = MESES_PT[Number(month) - 1] ?? MESES_PT[0];
  return { startMonth: name, startYear: year, endMonth: name, endYear: year };
}

export function emptyBlock(key: string): BlockDraft {
  return { key, clients: [], projectIds: [], packages: [], employeeIds: [] };
}

/** "Agosto" + "2026" → "2026-08". */
export function monthToCompetence(month: string, year: string): string {
  const index = MESES_PT.indexOf(month);
  return `${year}-${String(index + 1).padStart(2, "0")}`;
}

function monthsBetween(period: PeriodDraft): number {
  const start = Number(period.startYear) * 12 + MESES_PT.indexOf(period.startMonth);
  const end = Number(period.endYear) * 12 + MESES_PT.indexOf(period.endMonth);
  return end - start + 1;
}

/** O que impede o período (mês final antes do inicial, longo demais). */
export function periodProblem(period: PeriodDraft): string | null {
  const months = monthsBetween(period);
  if (months < 1) return "O mês final vem antes do inicial.";
  if (months > MAX_MONTHS) return `O período tem ${months} meses; o máximo é ${MAX_MONTHS}.`;
  return null;
}

export function periodLabelOf(period: PeriodDraft): string {
  return buildPeriodLabel(period.startMonth, period.startYear, period.endMonth, period.endYear);
}

/** O que impede o recorte: bloco sem nenhum filtro, ou pacotes com mais (ou
 * menos) de um projeto — o nome do pacote só faz sentido dentro de UM projeto. */
export function blockProblem(block: BlockDraft): string | null {
  if (!block.clients.length && !block.projectIds.length && !block.employeeIds.length) {
    return "Escolha cliente, projeto ou colaborador.";
  }
  if (block.packages.length && block.projectIds.length !== 1) {
    return "Pacotes só valem com um único projeto.";
  }
  return null;
}

/** Só o que o servidor aceita: sem pacote quando não há exatamente um projeto. */
function blockInput(block: BlockDraft): CustomBlockInput {
  return {
    clients: block.clients,
    project_ids: block.projectIds,
    packages: block.projectIds.length === 1 ? block.packages : [],
    employee_ids: block.employeeIds,
  };
}

export function buildCustomScope(input: {
  period: PeriodDraft;
  blocks: BlockDraft[];
  splitBy: CustomSplit;
  unit: CustomUnit;
  title: string;
  reviewerLogin: string;
}): CustomScopeInput {
  return {
    period: {
      start: monthToCompetence(input.period.startMonth, input.period.startYear),
      end: monthToCompetence(input.period.endMonth, input.period.endYear),
    },
    blocks: input.blocks.map(blockInput),
    split_by: input.splitBy,
    package_unit: input.unit,
    title: input.title.trim() || null,
    reviewer_login: input.reviewerLogin || null,
  };
}

/** Um recorte do pedido em NOMES, como o backend devolve (`describe_blocks`). */
export type CustomBlockView = { clients: string[]; projects: string[]; packages: string[]; employees: string[] };

/** O recorte numa linha só: "MERCEDES · todos os projetos · colaborador: Lucca". */
export function describeBlockView(block: CustomBlockView): string {
  const parts: string[] = [];
  if (block.clients.length) parts.push(block.clients.join(", "));
  if (block.projects.length) parts.push(block.projects.join(", "));
  else parts.push(block.clients.length ? "todos os projetos" : "qualquer cliente e projeto");
  if (block.packages.length) parts.push(`${block.packages.length === 1 ? "pacote" : "pacotes"}: ${block.packages.join(", ")}`);
  if (block.employees.length) parts.push(`${block.employees.length === 1 ? "colaborador" : "colaboradores"}: ${block.employees.join(", ")}`);
  return parts.join(" · ");
}

/** Uma frase do bloco pra tela ("Mercedes · 2 projetos · Lucca"). */
export function describeBlock(
  block: BlockDraft, employeeName: (id: string) => string, projectName: (id: string) => string,
): string {
  const parts: string[] = [];
  if (block.clients.length) parts.push(block.clients.length <= 2 ? block.clients.join(", ") : `${block.clients.length} clientes`);
  if (block.projectIds.length === 1) parts.push(projectName(block.projectIds[0]));
  else if (block.projectIds.length > 1) parts.push(`${block.projectIds.length} projetos`);
  else if (block.clients.length) parts.push("todos os projetos");
  if (block.packages.length && block.projectIds.length === 1) {
    parts.push(block.packages.length === 1 ? "1 pacote" : `${block.packages.length} pacotes`);
  }
  if (block.employeeIds.length) {
    parts.push(block.employeeIds.length <= 2 ? block.employeeIds.map(employeeName).join(", ") : `${block.employeeIds.length} colaboradores`);
  }
  return parts.join(" · ");
}
