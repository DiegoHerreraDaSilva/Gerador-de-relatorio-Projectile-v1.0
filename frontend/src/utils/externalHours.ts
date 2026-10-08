import type { ExternalParseResponse, ExternalRow, WorkPackage } from "../api/types";

/** Horas externas: lógica pura (sem store, sem DOM) que decide, linha a linha da planilha, onde ela entra no
 * relatório aberto. O backend (`external_hours.py`) só lê e valida; quem conhece pacotes e grupos da tela é aqui. */

export type ExternalPlacement = {
  packageId: string;
  groupId: string;
  /** "Colaborador – descrição", como sai no relatório. */
  description: string;
  hours: number;
  /** Identidade da linha de origem (base da duplicidade). */
  key: string;
};

/** Linhas sem destino automático, agrupadas por (projeto, pacote de trabalho) pra o usuário decidir uma vez só. */
export type PendingBucket = {
  id: string;
  project: string;
  workPackage: string;
  /** "projeto" = nenhum pacote do relatório tem esse nome; "grupo" = o projeto existe, o pacote de trabalho não. */
  missing: "projeto" | "grupo";
  rows: ExternalRow[];
  hours: number;
};

export type ExternalPlan = {
  placements: ExternalPlacement[];
  pending: PendingBucket[];
  /** Já estão no relatório (anexo repetido): descartadas. */
  duplicates: ExternalRow[];
  /** Data fora do período do relatório: descartadas. */
  outOfPeriod: ExternalRow[];
};

const MONTHS = [
  "janeiro",
  "fevereiro",
  "marco",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

/** Sem acento, sem caixa, espaços colapsados — mesma ideia do casamento de grupos/atividades da store. */
export function norm(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
}

export function externalDescription(row: ExternalRow): string {
  return `${row.collaborator} – ${row.description}`;
}

export function rowKey(row: ExternalRow): string {
  return [
    row.date,
    norm(row.collaborator),
    norm(row.project),
    norm(row.package),
    norm(row.description),
    row.hours.toFixed(3),
  ].join("|");
}

function monthIndex(name: string): number {
  return MONTHS.indexOf(norm(name));
}

/** Início e fim ("AAAA-MM-DD") do período do rótulo do relatório: "Agosto/2026", "Julho a Novembro/2026" ou
 * "Dezembro/2025 a Fevereiro/2026". `null` se o rótulo não for reconhecido (aí a data não é conferida). */
export function periodBounds(label: string): { start: string; end: string } | null {
  const text = label.trim();
  const make = (m1: number, y1: number, m2: number, y2: number) => {
    if (m1 < 0 || m2 < 0) return null;
    const last = new Date(y2, m2 + 1, 0).getDate();
    const pad = (n: number) => String(n).padStart(2, "0");
    return { start: `${y1}-${pad(m1 + 1)}-01`, end: `${y2}-${pad(m2 + 1)}-${pad(last)}` };
  };
  const cross = /^([^/]+)\/(\d{4})\s+a\s+([^/]+)\/(\d{4})$/i.exec(text);
  if (cross) return make(monthIndex(cross[1]), Number(cross[2]), monthIndex(cross[3]), Number(cross[4]));
  const same = /^(.+?)\s+a\s+([^/]+)\/(\d{4})$/i.exec(text);
  if (same) return make(monthIndex(same[1]), Number(same[3]), monthIndex(same[2]), Number(same[3]));
  const single = /^([^/]+)\/(\d{4})$/.exec(text);
  if (single) return make(monthIndex(single[1]), Number(single[2]), monthIndex(single[1]), Number(single[2]));
  return null;
}

/** Chaves das linhas externas que o relatório já tem (nas atividades vindas de anexos anteriores). */
export function existingKeys(packages: WorkPackage[]): Set<string> {
  const keys = new Set<string>();
  packages.forEach((p) =>
    p.groups.forEach((g) => g.activities.forEach((a) => a.externalKeys?.forEach((k) => keys.add(k)))),
  );
  return keys;
}

function findDestination(
  packages: WorkPackage[],
  row: ExternalRow,
): { packageId: string; groupId: string } | { missing: "projeto" | "grupo" } {
  const project = norm(row.project);
  const matching = packages.filter((p) => norm(p.projectName) === project || norm(p.key) === project);
  if (matching.length === 0) return { missing: "projeto" };
  const wanted = norm(row.package);
  for (const pkg of matching) {
    const group = pkg.groups.find((g) => norm(g.name) === wanted);
    if (group) return { packageId: pkg.id, groupId: group.id };
  }
  return { missing: "grupo" };
}

/** Decide o destino de cada linha. Ordem: duplicada → fora do período → destino automático ou pendente.
 * Linhas idênticas DENTRO do arquivo contam como lançamentos distintos (só se descarta o que o relatório já tem). */
export function planExternalMerge(packages: WorkPackage[], rows: ExternalRow[], periodLabel: string): ExternalPlan {
  const have = existingKeys(packages);
  const bounds = periodBounds(periodLabel);
  const plan: ExternalPlan = { placements: [], pending: [], duplicates: [], outOfPeriod: [] };
  const buckets = new Map<string, PendingBucket>();

  rows.forEach((row) => {
    const key = rowKey(row);
    if (have.has(key)) {
      plan.duplicates.push(row);
      return;
    }
    if (bounds && (row.date < bounds.start || row.date > bounds.end)) {
      plan.outOfPeriod.push(row);
      return;
    }
    const destination = findDestination(packages, row);
    if ("missing" in destination) {
      const id = `${norm(row.project)}||${norm(row.package)}`;
      let bucket = buckets.get(id);
      if (!bucket) {
        bucket = {
          id,
          project: row.project,
          workPackage: row.package,
          missing: destination.missing,
          rows: [],
          hours: 0,
        };
        buckets.set(id, bucket);
        plan.pending.push(bucket);
      }
      bucket.rows.push(row);
      bucket.hours = Math.round((bucket.hours + row.hours) * 1000) / 1000;
      return;
    }
    plan.placements.push({
      packageId: destination.packageId,
      groupId: destination.groupId,
      description: externalDescription(row),
      hours: row.hours,
      key,
    });
  });
  return plan;
}

/** Destino escolhido pelo usuário pra um pendente: `"pacoteId::grupoId"`; vazio = descartar. */
export function resolvePending(plan: ExternalPlan, choices: Record<string, string>): ExternalPlacement[] {
  const extra: ExternalPlacement[] = [];
  plan.pending.forEach((bucket) => {
    const [packageId, groupId] = (choices[bucket.id] ?? "").split("::");
    if (!packageId || !groupId) return;
    bucket.rows.forEach((row) =>
      extra.push({ packageId, groupId, description: externalDescription(row), hours: row.hours, key: rowKey(row) }),
    );
  });
  return [...plan.placements, ...extra];
}

export function totalHours(items: Array<{ hours: number }>): number {
  return Math.round(items.reduce((sum, item) => sum + item.hours, 0) * 1000) / 1000;
}

/** Envia a planilha e devolve as linhas validadas. Levanta com mensagem pronta pra tela. */
export async function parseExternalFile(file: File): Promise<ExternalParseResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/parse-external", { method: "POST", body: form });
  if (res.status === 401) throw new Error("Sessão expirada. Entre de novo.");
  if (res.status === 403) throw new Error("Só gerente e coordenador podem adicionar horas externas.");
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : "Não consegui ler a planilha agora. Tenta de novo.",
    );
  }
  return (await res.json()) as ExternalParseResponse;
}

/** Baixa o modelo da planilha. */
export async function downloadExternalTemplate(): Promise<void> {
  const res = await fetch("/parse-external/template");
  if (!res.ok) throw new Error("Não consegui baixar o modelo agora. Tenta de novo.");
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "modelo-horas-externas.xlsx";
  link.click();
  URL.revokeObjectURL(url);
}
