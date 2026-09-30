import { enableMapSet } from "immer";
import { WorkPackage, Group, Activity, RowIssue, ReportHeader } from "../api/types";

enableMapSet();

export const MESES_PT = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

export function genId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2, 9);
}

export function createInitialHeader(): ReportHeader {
  const hoje = new Date();
  const dia = String(hoje.getDate()).padStart(2, "0");
  const mes = String(hoje.getMonth() + 1).padStart(2, "0");
  const ano = hoje.getFullYear();
  const mesReferencia = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
  const nomeMes = MESES_PT[mesReferencia.getMonth()];
  return {
    locationDate: `Santo André, ${dia}.${mes}.${ano}`,
    monthLabel: `${nomeMes}/${mesReferencia.getFullYear()}`,
    signer1Name: "",
    signer1Company: "Schwaben Engineering",
    signer2Name: "",
    signer2Company: "Mercedes-Benz do Brasil",
  };
}

export type DraggedActivities = { fromPackageId: string; items: Array<{ groupId: string; activityId: string }> } | null;

export type DraggedGroup = { fromPackageId: string; groupId: string } | null;

export type Snapshot = {
  packages: WorkPackage[];
  header: ReportHeader;
  activePackageId: string | null;
  fileName: string;
  fileNameEdited: boolean;
};

export function clonePackages(pkgs: WorkPackage[]): WorkPackage[] {
  return pkgs.map((p) => ({
    ...p,
    groups: p.groups.map((g) => ({
      ...g,
      activities: g.activities.map((a) => ({ ...a })),
    })),
    collapsedGroupIds: new Set(p.collapsedGroupIds),
  }));
}

// Set não é serializável em JSON direto — os dois helpers abaixo convertem
// `Set` <-> `{__set: [...]}` em qualquer profundidade da árvore (não fixo a
// campos específicos), reaproveitados tanto pelo snapshot de undo (5 campos)
// quanto pelo bundle completo de uma guia (useReportTabsStore.ts).
export function jsonReplacer(_k: string, v: unknown) {
  return v instanceof Set ? { __set: Array.from(v) } : v;
}

export function jsonReviver(_k: string, v: unknown) {
  if (v && typeof v === "object" && "__set" in (v as Record<string, unknown>)) {
    return new Set((v as { __set: unknown[] }).__set);
  }
  return v;
}

export function snapshotState(state: StoreState): string {
  const snap: Snapshot = {
    packages: clonePackages(state.packages),
    header: { ...state.header },
    activePackageId: state.activePackageId,
    fileName: state.fileName,
    fileNameEdited: state.fileNameEdited,
  };
  return JSON.stringify(snap, jsonReplacer);
}

export function restoreSnapshot(snapshotStr: string, state: StoreState) {
  const parsed = JSON.parse(snapshotStr, jsonReviver) as Snapshot;
  state.packages = parsed.packages;
  state.header = parsed.header;
  state.activePackageId = parsed.activePackageId;
  state.fileName = parsed.fileName;
  state.fileNameEdited = parsed.fileNameEdited;
}

// Conteúdo "de uma guia" inteira (ver useReportTabsStore.ts) — mais campos
// que o Snapshot do undo acima (que só cobre o essencial pra desfazer uma
// edição). `previewZoom`/`draggedPackageId`/`draggedActivities`/
// `draggedGroup` ficam de fora de propósito: são preferência de tela ou
// estado de um drag em andamento, não "conteúdo do relatório" — não fazem
// sentido trocar junto quando o usuário muda de guia.
export type TabBundle = {
  packages: WorkPackage[];
  activePackageId: string | null;
  reportMode: "single" | "multi";
  currentIssues: RowIssue[];
  header: ReportHeader;
  fileName: string;
  fileNameEdited: boolean;
  undoStack: string[];
  hasGeneratedOnce: boolean;
  showImportCard: boolean;
  importSource: "file" | "db";
  importByClient: boolean;
  importSelectedClient: string;
  importSelectedProjectIds: Set<string>;
  importClientReportMode: "pacote" | "projeto";
  importPeriodMode: "single" | "range";
  importEndMonthLabel: string;
  includePerformanceInExport: boolean;
  isSplit: boolean;
  paneBPackageId: string | null;
  validationCollapsed: boolean;
  selectedByPane: Record<string, Set<string>>;
};

export function serializeTabBundle(state: StoreState): string {
  const bundle: TabBundle = {
    packages: clonePackages(state.packages),
    activePackageId: state.activePackageId,
    reportMode: state.reportMode,
    currentIssues: state.currentIssues,
    header: { ...state.header },
    fileName: state.fileName,
    fileNameEdited: state.fileNameEdited,
    undoStack: state.undoStack,
    hasGeneratedOnce: state.hasGeneratedOnce,
    showImportCard: state.showImportCard,
    importSource: state.importSource,
    importByClient: state.importByClient,
    importSelectedClient: state.importSelectedClient,
    importSelectedProjectIds: state.importSelectedProjectIds,
    importClientReportMode: state.importClientReportMode,
    importPeriodMode: state.importPeriodMode,
    importEndMonthLabel: state.importEndMonthLabel,
    includePerformanceInExport: state.includePerformanceInExport,
    isSplit: state.isSplit,
    paneBPackageId: state.paneBPackageId,
    validationCollapsed: state.validationCollapsed,
    selectedByPane: state.selectedByPane,
  };
  return JSON.stringify(bundle, jsonReplacer);
}

export function applyTabBundle(bundleStr: string, state: StoreState) {
  const parsed = JSON.parse(bundleStr, jsonReviver) as TabBundle;
  // `language` foi adicionado depois — guias salvas no localStorage antes
  // disso (ou pacotes vindos de uma sessão de backend mais antiga) não têm
  // esse campo, e `LABELS[pkg.language]` (PreviewSheet.tsx) quebra com
  // `undefined` em vez de cair no português.
  state.packages = parsed.packages.map((pkg) => ({ ...pkg, language: pkg.language ?? "pt" }));
  state.activePackageId = parsed.activePackageId;
  state.reportMode = parsed.reportMode;
  state.currentIssues = parsed.currentIssues;
  state.header = parsed.header;
  state.fileName = parsed.fileName;
  state.fileNameEdited = parsed.fileNameEdited;
  state.undoStack = parsed.undoStack;
  state.hasGeneratedOnce = parsed.hasGeneratedOnce;
  state.showImportCard = parsed.showImportCard;
  state.importSource = parsed.importSource;
  state.importByClient = parsed.importByClient;
  state.importSelectedClient = parsed.importSelectedClient;
  state.importSelectedProjectIds = parsed.importSelectedProjectIds;
  state.importClientReportMode = parsed.importClientReportMode;
  // adicionados depois — mesmo padrão de `language` acima, guias salvas
  // antes desta feature não têm esses campos.
  state.importPeriodMode = parsed.importPeriodMode ?? "single";
  state.importEndMonthLabel =
    parsed.importEndMonthLabel ?? parsed.header?.monthLabel ?? createInitialHeader().monthLabel;
  state.includePerformanceInExport = parsed.includePerformanceInExport;
  state.isSplit = parsed.isSplit;
  state.paneBPackageId = parsed.paneBPackageId;
  state.validationCollapsed = parsed.validationCollapsed;
  state.selectedByPane = parsed.selectedByPane;
}

/** Bundle de uma guia nova/vazia — mesmos valores iniciais do `create()`
 * da store logo abaixo, exceto `header` (cada guia começa com um header
 * limpo, não o padrão do dia — ver `createInitialHeader`). */
export function blankTabBundle(): string {
  const bundle: TabBundle = {
    packages: [],
    activePackageId: null,
    reportMode: "single",
    currentIssues: [],
    header: createInitialHeader(),
    fileName: "",
    fileNameEdited: false,
    undoStack: [],
    hasGeneratedOnce: false,
    showImportCard: true,
    importSource: "file",
    importByClient: false,
    importSelectedClient: "",
    importSelectedProjectIds: new Set(),
    importClientReportMode: "pacote",
    importPeriodMode: "single",
    importEndMonthLabel: createInitialHeader().monthLabel,
    includePerformanceInExport: false,
    isSplit: false,
    paneBPackageId: null,
    validationCollapsed: false,
    selectedByPane: { "0": new Set(), "1": new Set() },
  };
  return JSON.stringify(bundle, jsonReplacer);
}

/** Bundle de uma guia que já abre com um relatório pronto (sem o card de
 * importação) — usado pela geração automática pra abrir um rascunho do
 * servidor no editor de sempre. */
export function reportTabBundle(
  packages: WorkPackage[],
  header: ReportHeader,
  includePerformance: boolean,
  issues: RowIssue[] = [],
): string {
  const bundle = JSON.parse(blankTabBundle(), jsonReviver) as TabBundle;
  bundle.packages = packages;
  bundle.currentIssues = issues;
  bundle.activePackageId = packages[0]?.id ?? null;
  bundle.header = header;
  bundle.showImportCard = false;
  bundle.includePerformanceInExport = includePerformance;
  return JSON.stringify(bundle, jsonReplacer);
}

export interface StoreState {
  packages: WorkPackage[];
  // controla o card "Importe a planilha de horas" (id="step1" em
  // FileUpload.tsx) — precisa viver na store (não em useState local) porque
  // trocar de aba (Painel de Gerência/Diagnóstico e voltar) desmonta e
  // remonta essa árvore inteira; um estado de componente resetaria sozinho a
  // cada volta, mas a store persiste. `true` por padrão (nada carregado
  // ainda); `setPackages` desliga sozinho ao carregar um relatório com
  // sucesso; "Alterar dados" reinicia a guia via `resetForNewImport()`.
  showImportCard: boolean;
  // seleção feita dentro do card acima ("Fonte dos dados", "Por cliente",
  // cliente/projetos escolhidos, "Por pacote"/"Por projeto") — mesmo motivo
  // do `showImportCard`: precisa viver na store (não em useState local de
  // FileUpload.tsx) pra cada guia manter a própria busca configurada ao
  // voltar pra ela, em vez de perder tudo porque o componente foi
  // desmontado e remontado (ver `key={activeTabId}` em App.tsx).
  importSource: "file" | "db";
  importByClient: boolean;
  importSelectedClient: string;
  importSelectedProjectIds: Set<string>;
  importClientReportMode: "pacote" | "projeto";
  // "single" (padrão, mês único) ou "range" (período — busca soma vários
  // meses num relatório só, ver PeriodPicker em FileUpload.tsx).
  importPeriodMode: "single" | "range";
  // mês final do período, mesmo formato "Mês/Ano" de `header.monthLabel`
  // (que vira o mês INICIAL nesse modo) — só é lido quando
  // `importPeriodMode === "range"`.
  importEndMonthLabel: string;
  // checkbox "Incluir performance" no rodapé de Gerar Relatório — por guia,
  // mesmo motivo dos campos de import acima.
  includePerformanceInExport: boolean;
  activePackageId: string | null;
  reportMode: "single" | "multi";
  currentIssues: RowIssue[];
  validationCollapsed: boolean;
  previewZoom: number;
  isSplit: boolean;
  paneBPackageId: string | null;
  draggedPackageId: string | null;
  draggedActivities: DraggedActivities;
  draggedGroup: DraggedGroup;
  hasGeneratedOnce: boolean;
  header: ReportHeader;
  fileName: string;
  fileNameEdited: boolean;
  undoStack: string[];
  selectedByPane: Record<string, Set<string>>; // paneId -> Set<"groupId:activityId">

  // actions
  setPackages: (pkgs: WorkPackage[], activeId?: string | null) => void;
  setShowImportCard: (v: boolean) => void;
  setImportSource: (v: "file" | "db") => void;
  setImportByClient: (v: boolean) => void;
  setImportSelectedClient: (v: string) => void;
  setImportSelectedProjectIds: (v: Set<string>) => void;
  setImportClientReportMode: (v: "pacote" | "projeto") => void;
  setImportPeriodMode: (v: "single" | "range") => void;
  setImportEndMonthLabel: (v: string) => void;
  setIncludePerformanceInExport: (v: boolean) => void;
  setActivePackageId: (id: string) => void;
  setReportMode: (mode: "single" | "multi") => void;
  setIssues: (issues: RowIssue[]) => void;
  setValidationCollapsed: (v: boolean) => void;
  setPreviewZoom: (z: number) => void;
  setSplit: (v: boolean) => void;
  setPaneBPackageId: (id: string) => void;
  setDraggedPackageId: (id: string | null) => void;
  setDraggedActivities: (d: DraggedActivities) => void;
  setDraggedGroup: (d: DraggedGroup) => void;
  setHeaderField: (field: keyof ReportHeader, value: string) => void;
  setHasGeneratedOnce: (v: boolean) => void;
  setFileName: (v: string, edited: boolean) => void;
  setPackageFileName: (packageId: string, v: string) => void;
  setChartBar: (packageId: string, v: boolean) => void;
  setChartPie: (packageId: string, v: boolean) => void;
  pushUndo: () => void;
  undo: () => void;
  resetParsedState: () => void;
  resetForNewImport: () => void;
  addGroup: (packageId?: string) => void;
  removeGroup: (groupId: string, packageId?: string) => void;
  addActivity: (groupId: string, packageId?: string) => void;
  // recupera linha(s) ignorada(s) do aviso (ValidationBanner) num único
  // lote — um só snapshot de undo pro grupo inteiro selecionado, e a hora
  // vem fixa (extra: false, mesmo tratamento visual de atividade importada,
  // sem input editável) porque já é um valor confiável lido do Projectile,
  // não um número digitado à mão.
  // devolve `false` (sem adicionar nada) quando o grupo/pacote alvo não
  // existe mais no momento do clique — ex: usuário escolheu um grupo,
  // trocou de guia (ver ReportTabsBar/useReportTabsStore) ou removeu esse
  // grupo antes de confirmar. ValidationBanner usa o retorno pra só tirar
  // as linhas da lista de avisos quando a recuperação de fato aconteceu,
  // em vez de fazer a hora desaparecer em silêncio como se tivesse dado
  // certo.
  addActivitiesFromIssues: (
    groupId: string,
    packageId: string,
    items: Array<{ description: string; hours: number }>,
  ) => boolean;
  removeActivities: (packageId: string, items: Array<{ groupId: string; activityId: string }>) => void;
  updateGroupName: (groupId: string, name: string, packageId?: string) => void;
  updatePerformance: (groupId: string, perf: number, packageId?: string) => void;
  updateDescription: (groupId: string, activityId: string, desc: string, packageId?: string) => void;
  updateExtraHours: (groupId: string, activityId: string, hours: number | null, packageId?: string) => void;
  updateProjectCode: (value: string, packageId?: string) => void;
  updateProjectName: (value: string, packageId?: string) => void;
  removePackage: (packageId: string) => void;
  mergePackages: (sourceId: string, targetId: string) => void;
  moveGroupToPackage: (fromPackageId: string, groupId: string, toPackageId: string) => void;
  // reordenar: solta perto do TOPO/BASE de outro grupo — insere o grupo
  // arrastado ANTES de `beforeGroupId` (ou no fim do pacote, se `null`), sem
  // mesclar nada (diferente de moveGroupToPackage, que mescla por nome
  // quando os pacotes são diferentes). Funciona pra reordenar dentro do
  // mesmo pacote ou mover entre pacotes sem mesclar.
  moveGroupToPosition: (
    fromPackageId: string,
    groupId: string,
    toPackageId: string,
    beforeGroupId: string | null,
  ) => void;
  moveActivitiesToGroup: (
    fromPackageId: string,
    items: Array<{ groupId: string; activityId: string }>,
    toPackageId: string,
    toGroupId: string,
  ) => void;
  // soltar uma atividade EM CIMA de outra (não só no grupo): soma as horas
  // na atividade de destino e mantém o nome dela, ignorando se o nome bate
  // com a arrastada — diferente de moveActivitiesToGroup/mergeActivityIntoGroup,
  // que casam por descrição igual.
  mergeActivitiesIntoActivity: (
    fromPackageId: string,
    items: Array<{ groupId: string; activityId: string }>,
    toPackageId: string,
    toGroupId: string,
    toActivityId: string,
  ) => void;
  // reordenar: solta perto do TOPO/BASE de uma atividade (em vez de em cima
  // dela) — insere as atividades arrastadas ANTES de `beforeActivityId`
  // (ou no fim do grupo, se `null`), sem mesclar nada. Funciona tanto pra
  // reordenar dentro do mesmo grupo quanto pra mover entre grupos/pacotes.
  moveActivitiesToPosition: (
    fromPackageId: string,
    items: Array<{ groupId: string; activityId: string }>,
    toPackageId: string,
    toGroupId: string,
    beforeActivityId: string | null,
  ) => void;
  // botões "EN"/"DE" do preview — troca `name` de grupo e `description` de
  // atividade, casando por `id` (nunca ambíguo, diferente de applyChatState,
  // que casa por nome/descrição porque lida com operações abertas). `id` de
  // grupo e de atividade nunca colidem entre si (mesmo gerador `genId()`,
  // mas espaços de uso disjuntos), então uma lista só serve pros dois tipos
  // — quem chama (Preview.tsx) nem precisa saber qual é qual. Marca
  // `pkg.language` com o idioma-alvo escolhido; quem chama já dá pushUndo()
  // antes (mesmo padrão de applyChatState), então desfazer reverte dado e
  // idioma juntos.
  applyTranslation: (
    packageId: string,
    translations: Array<{ id: string; text: string }>,
    language: WorkPackage["language"],
  ) => void;
  applyChatState: (newState: {
    packages: Array<{
      key: string;
      projectCode: string;
      projectName: string;
      groups: Array<{
        id: string;
        name: string;
        performance: number;
        activities: Array<{ id: string; description: string; hours: number | null }>;
      }>;
    }>;
    locationDate: string;
    monthLabel: string;
    signer1Name: string;
    signer1Company: string;
    signer2Name: string;
    signer2Company: string;
  }) => boolean;
  toggleGroupCollapsed: (groupId: string, packageId?: string) => void;
  toggleSelected: (paneId: string, key: string) => void;
  setSelected: (paneId: string, set: Set<string>) => void;
  clearSelected: (paneId: string) => void;
}

/** Remove de `pkg` as atividades apontadas por `items` (que podem vir de
 * vários grupos de origem diferentes) e devolve as removidas, na ordem em
 * que apareciam nos grupos de origem — não na ordem de `items`, que reflete
 * a ordem de seleção do usuário. Usado por moveActivitiesToGroup/
 * mergeActivitiesIntoActivity/moveActivitiesToPosition: as três precisam
 * de "tirar estas atividades de onde estão, mantendo o resto do grupo",
 * só o que fazem com o resultado depois é que muda (mesclar por descrição,
 * somar num alvo, ou reinserir noutra posição). */
export function extractActivitiesFromGroups(
  pkg: WorkPackage,
  items: Array<{ groupId: string; activityId: string }>,
): Activity[] {
  const byGroup = new Map<string, string[]>();
  items.forEach(({ groupId, activityId }) => {
    if (!byGroup.has(groupId)) byGroup.set(groupId, []);
    byGroup.get(groupId)!.push(activityId);
  });
  const extracted: Activity[] = [];
  byGroup.forEach((aIds, gId) => {
    const gr = pkg.groups.find((g) => g.id === gId);
    if (!gr) return;
    const keep: Activity[] = [];
    gr.activities.forEach((a) => (aIds.includes(a.id) ? extracted.push(a) : keep.push(a)));
    gr.activities = keep;
  });
  return extracted;
}

// helpers for merge logic
export function mergeActivityIntoGroup(toGroup: Group, activity: Activity) {
  const desc = activity.description.trim().toLowerCase();
  const existing = desc ? toGroup.activities.find((a) => a.description.trim().toLowerCase() === desc) : undefined;
  if (existing) {
    existing.hours =
      Math.round(((parseFloat(String(existing.hours)) || 0) + (parseFloat(String(activity.hours)) || 0)) * 1000) / 1000;
  } else {
    toGroup.activities.push({ ...activity, id: genId() });
  }
}

export function mergeGroupIntoPackage(targetPkg: WorkPackage, sourceGroup: Group, claimed: Set<string>) {
  const sourceName = sourceGroup.name.trim().toLowerCase();
  const match = targetPkg.groups.find((g) => !claimed.has(g.id) && g.name.trim().toLowerCase() === sourceName);
  if (match) {
    sourceGroup.activities.forEach((a) => mergeActivityIntoGroup(match, a));
    claimed.add(match.id);
  } else {
    const newGroup: Group = {
      ...sourceGroup,
      id: genId(),
      activities: sourceGroup.activities.map((a) => ({ ...a, id: genId() })),
    };
    targetPkg.groups.push(newGroup);
    targetPkg.collapsedGroupIds.add(newGroup.id);
  }
}
