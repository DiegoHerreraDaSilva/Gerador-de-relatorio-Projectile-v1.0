import type { Group } from "../api/types";

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
