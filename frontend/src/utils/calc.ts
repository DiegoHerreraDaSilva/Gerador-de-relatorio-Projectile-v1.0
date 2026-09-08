import type { Group, WorkPackage } from "../api/types";

export function computeGroupTotals(group: Group) {
  const realActivities = group.activities.filter(
    (a) => a.hours !== null && a.hours !== undefined
  );
  const bruto = realActivities.reduce((sum, a) => sum + (parseFloat(String(a.hours)) || 0), 0);
  const performance = parseFloat(String(group.performance)) || 0;
  const resultado = bruto * performance;
  return { bruto, performance, resultado, hasRealActivities: realActivities.length > 0 };
}

export function computeGrandTotalFor(groups: Group[]): number {
  return groups.reduce((sum, group) => {
    const { resultado, hasRealActivities } = computeGroupTotals(group);
    return hasRealActivities ? sum + resultado : sum;
  }, 0);
}

export function computeGrandBruto(groups: Group[]): number {
  return groups.reduce((sum, group) => sum + computeGroupTotals(group).bruto, 0);
}

/** Primeira atividade sem descrição preenchida num pacote, ou `null` se
 * todas estiverem OK — usado antes de gerar/enviar o relatório final pra
 * barrar um "•" vazio no PDF/Excel (o número de horas continua opcional
 * pra atividade "extra": uma linha só de texto sem hora própria, ex:
 * "Relatório", é um caso de uso válido, ver `generator._build_group_rows`
 * — só a descrição em branco é bloqueada). */
export function findEmptyActivityDescription(pkg: WorkPackage): { groupName: string } | null {
  for (const group of pkg.groups) {
    if (group.activities.some((a) => !a.description.trim())) {
      return { groupName: group.name };
    }
  }
  return null;
}

/** Mensagem de erro pronta pra mostrar (ou `null` se todos os pacotes
 * estiverem OK) — checa `findEmptyActivityDescription` em todos os
 * `packages`, não só um. `verbo` entra no final da frase ("gerar"/
 * "enviar"), já que é a mesma validação usada tanto por
 * GenerateFooter.tsx quanto por SendReportModal.tsx antes de cada ação. */
export function findEmptyActivityDescriptionMessage(packages: WorkPackage[], verbo: string): string | null {
  for (const pkg of packages) {
    const empty = findEmptyActivityDescription(pkg);
    if (empty) {
      return `Preencha a descrição de todas as atividades (grupo "${empty.groupName}" em "${pkg.projectName}") antes de ${verbo}.`;
    }
  }
  return null;
}
