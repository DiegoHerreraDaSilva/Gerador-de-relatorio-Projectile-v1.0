import type { ReportHeader, RowIssue, WorkPackage } from "../api/types";

/** Rascunho da geração automática, como o backend guarda
 * (`backend/app/auto_generation/builder.py` / `schemas.Draft`). */
export type AutoDraftActivity = { id: string; source_key?: string | null; description: string; hours: number | null };
export type AutoDraftGroup = {
  id: string;
  source_key?: string | null;
  name: string;
  performance: number;
  activities: AutoDraftActivity[];
};
export type AutoDraftPackage = {
  id: string;
  key: string;
  source_key?: string | null;
  project_code: string;
  suggested_code: string;
  project_name: string;
  pacote_scope: string | null;
  language: "pt" | "en" | "de";
  chart_bar: boolean;
  chart_pie: boolean;
  groups: AutoDraftGroup[];
};
export type AutoDraft = {
  schema: number;
  mode: "pacote" | "projeto";
  header: {
    location_date: string;
    month_label: string;
    signer1_name: string;
    signer1_company: string;
    signer2_name: string;
    signer2_company: string;
  };
  include_performance: boolean;
  formats: Array<"xlsx" | "pdf">;
  packages: AutoDraftPackage[];
  // linhas do Projectile que não viraram atividade (ex.: horas sem
  // descrição) — viram o aviso do editor (`currentIssues`), como na busca manual
  issues: RowIssue[];
  memory_applied: boolean;
};

/** O que o editor não tem campo pra guardar, mas o rascunho precisa de volta:
 * a chave de memória de cada grupo/atividade/pacote (`source_key`), a chave
 * e o número sugerido de cada pacote, e o que não é editável na tela. */
export type AutoDraftExtras = {
  sourceKeys: Record<string, string>;
  packages: Record<string, { key: string; suggested_code: string }>;
  mode: AutoDraft["mode"];
  memory_applied: boolean;
};

export function draftToEditor(draft: AutoDraft): {
  packages: WorkPackage[];
  header: ReportHeader;
  includePerformance: boolean;
  formats: AutoDraft["formats"];
  issues: RowIssue[];
  extras: AutoDraftExtras;
} {
  const sourceKeys: Record<string, string> = {};
  const packageExtras: AutoDraftExtras["packages"] = {};
  const packages: WorkPackage[] = draft.packages.map((p) => {
    if (p.source_key) sourceKeys[p.id] = p.source_key;
    packageExtras[p.id] = { key: p.key, suggested_code: p.suggested_code };
    const groups = p.groups.map((g) => {
      if (g.source_key) sourceKeys[g.id] = g.source_key;
      return {
        id: g.id,
        name: g.name,
        performance: g.performance,
        activities: g.activities.map((a) => {
          if (a.source_key) sourceKeys[a.id] = a.source_key;
          // `extra` = linha sem horas (adicionada à mão) — mesmo critério do editor
          return { id: a.id, description: a.description, hours: a.hours, extra: a.hours === null };
        }),
      };
    });
    return {
      id: p.id,
      key: p.key,
      projectCode: p.project_code,
      projectName: p.project_name,
      groups,
      collapsedGroupIds: new Set(groups.map((g) => g.id)),
      fileName: "",
      fileNameEdited: false,
      chartBar: p.chart_bar,
      chartPie: p.chart_pie,
      pacoteScope: p.pacote_scope,
      language: p.language,
    };
  });
  return {
    packages,
    header: {
      locationDate: draft.header.location_date,
      monthLabel: draft.header.month_label,
      signer1Name: draft.header.signer1_name,
      signer1Company: draft.header.signer1_company,
      signer2Name: draft.header.signer2_name,
      signer2Company: draft.header.signer2_company,
    },
    includePerformance: draft.include_performance,
    formats: draft.formats,
    issues: (draft.issues ?? []).map((i) => ({
      row: i.row ?? 0,
      reason: i.reason ?? "",
      message: i.message ?? "",
      raw_hours: i.raw_hours ?? null,
      raw_description: i.raw_description ?? null,
    })),
    extras: { sourceKeys, packages: packageExtras, mode: draft.mode, memory_applied: draft.memory_applied },
  };
}

export function editorToDraft(
  packages: WorkPackage[],
  header: ReportHeader,
  includePerformance: boolean,
  formats: AutoDraft["formats"],
  extras: AutoDraftExtras,
  issues: RowIssue[] = [],
): AutoDraft {
  const key = (id: string) => extras.sourceKeys[id] ?? null;
  return {
    schema: 1,
    mode: extras.mode,
    header: {
      location_date: header.locationDate,
      month_label: header.monthLabel,
      signer1_name: header.signer1Name,
      signer1_company: header.signer1Company,
      signer2_name: header.signer2Name,
      signer2_company: header.signer2Company,
    },
    include_performance: includePerformance,
    formats,
    packages: packages.map((p) => ({
      id: p.id,
      key: extras.packages[p.id]?.key ?? p.key,
      source_key: key(p.id),
      project_code: p.projectCode,
      suggested_code: extras.packages[p.id]?.suggested_code ?? "",
      project_name: p.projectName,
      pacote_scope: p.pacoteScope,
      language: p.language,
      chart_bar: p.chartBar,
      chart_pie: p.chartPie,
      groups: p.groups.map((g) => ({
        id: g.id,
        source_key: key(g.id),
        name: g.name,
        performance: g.performance,
        activities: g.activities.map((a) => ({ id: a.id, source_key: key(a.id), description: a.description, hours: a.hours })),
      })),
    })),
    issues,
    memory_applied: extras.memory_applied,
  };
}

const DEFAULT_NUMBER_PATTERN = String.raw`^SE\.\d{2}\.\d{3}$`;
const DEFAULT_NUMBER_MODEL = "SE.##.###";

/** Formato do número pra gente ler (o mesmo texto da recusa no backend):
 * o modelo com `#` por dígito, nunca a expressão regular. */
export function numberPatternLabel(model: string | null | undefined): string {
  const shown = model ?? DEFAULT_NUMBER_MODEL;
  return shown === DEFAULT_NUMBER_MODEL ? `${shown} (ex.: SE.26.053)` : shown;
}

/** Confere o número com o formato configurado (regex do Python, que no
 * padrão é compatível com a do JS). Formato inválido nunca bloqueia a
 * digitação — quem barra é o backend na aprovação. */
export function matchesNumberPattern(code: string, pattern: string | undefined): boolean {
  try {
    return new RegExp(pattern || DEFAULT_NUMBER_PATTERN).test(code);
  } catch {
    return true;
  }
}
