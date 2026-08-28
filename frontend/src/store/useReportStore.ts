import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { enableMapSet } from "immer";
import type { WorkPackage, Group, Activity, RowIssue, ReportHeader } from "../api/types";
import { computeDefaultFileNameFor } from "../utils/fileName";

enableMapSet();

export const MESES_PT = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

function genId(): string {
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

type Snapshot = {
  packages: WorkPackage[];
  header: ReportHeader;
  activePackageId: string | null;
  fileName: string;
  fileNameEdited: boolean;
};

function clonePackages(pkgs: WorkPackage[]): WorkPackage[] {
  return pkgs.map((p) => ({
    ...p,
    groups: p.groups.map((g) => ({
      ...g,
      activities: g.activities.map((a) => ({ ...a })),
    })),
    collapsedGroupIds: new Set(p.collapsedGroupIds),
  }));
}

function snapshotState(state: StoreState): string {
  const snap: Snapshot = {
    packages: clonePackages(state.packages),
    header: { ...state.header },
    activePackageId: state.activePackageId,
    fileName: state.fileName,
    fileNameEdited: state.fileNameEdited,
  };
  // Sets are not JSON serializable, convert
  return JSON.stringify(snap, (_k, v) => (v instanceof Set ? { __set: Array.from(v) } : v));
}

function restoreSnapshot(snapshotStr: string, state: StoreState) {
  const parsed = JSON.parse(snapshotStr, (_k, v) => {
    if (v && typeof v === "object" && "__set" in v) return new Set(v.__set);
    return v;
  }) as Snapshot;
  state.packages = parsed.packages;
  state.header = parsed.header;
  state.activePackageId = parsed.activePackageId;
  state.fileName = parsed.fileName;
  state.fileNameEdited = parsed.fileNameEdited;
}

export interface StoreState {
  packages: WorkPackage[];
  activePackageId: string | null;
  reportMode: "single" | "multi";
  currentIssues: RowIssue[];
  validationCollapsed: boolean;
  headerCollapsed: boolean;
  previewCollapsed: boolean;
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
  setActivePackageId: (id: string) => void;
  setReportMode: (mode: "single" | "multi") => void;
  setIssues: (issues: RowIssue[]) => void;
  setValidationCollapsed: (v: boolean) => void;
  setHeaderCollapsed: (v: boolean) => void;
  setPreviewCollapsed: (v: boolean) => void;
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
  addGroup: (packageId?: string) => void;
  removeGroup: (groupId: string, packageId?: string) => void;
  addActivity: (groupId: string, packageId?: string) => void;
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
  moveActivitiesToGroup: (
    fromPackageId: string,
    items: Array<{ groupId: string; activityId: string }>,
    toPackageId: string,
    toGroupId: string
  ) => void;
  applyChatState: (newState: {
    packages: Array<{ key: string; projectCode: string; projectName: string; groups: Array<{ name: string; performance: number; activities: Array<{ description: string; hours: number | null }> }> }>;
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

// helpers for merge logic
function mergeActivityIntoGroup(toGroup: Group, activity: Activity) {
  const desc = activity.description.trim().toLowerCase();
  const existing = desc ? toGroup.activities.find((a) => a.description.trim().toLowerCase() === desc) : undefined;
  if (existing) {
    existing.hours = Math.round(((parseFloat(String(existing.hours)) || 0) + (parseFloat(String(activity.hours)) || 0)) * 1000) / 1000;
  } else {
    toGroup.activities.push({ ...activity, id: genId() });
  }
}

function mergeGroupIntoPackage(targetPkg: WorkPackage, sourceGroup: Group, claimed: Set<string>) {
  const sourceName = sourceGroup.name.trim().toLowerCase();
  const match = targetPkg.groups.find((g) => !claimed.has(g.id) && g.name.trim().toLowerCase() === sourceName);
  if (match) {
    sourceGroup.activities.forEach((a) => mergeActivityIntoGroup(match, a));
    claimed.add(match.id);
  } else {
    const newGroup: Group = { ...sourceGroup, id: genId(), activities: sourceGroup.activities.map((a) => ({ ...a, id: genId() })) };
    targetPkg.groups.push(newGroup);
    targetPkg.collapsedGroupIds.add(newGroup.id);
  }
}

export const useReportStore = create<StoreState>()(
  immer((set, get) => ({
    packages: [],
    activePackageId: null,
    reportMode: "single",
    currentIssues: [],
    validationCollapsed: false,
    headerCollapsed: true,
    previewCollapsed: false,
    previewZoom: 100,
    isSplit: false,
    paneBPackageId: null,
    draggedPackageId: null,
    draggedActivities: null,
    draggedGroup: null,
    hasGeneratedOnce: false,
    header: createInitialHeader(),
    fileName: "",
    fileNameEdited: false,
    undoStack: [],
    selectedByPane: { "0": new Set(), "1": new Set() },

    setPackages: (pkgs, activeId) =>
      set((s) => {
        s.packages = pkgs;
        s.activePackageId = activeId ?? (pkgs[0]?.id ?? null);
        s.undoStack = [];
        s.hasGeneratedOnce = false;
        s.isSplit = false;
        s.paneBPackageId = null;
      }),
    setActivePackageId: (id) =>
      set((s) => {
        s.activePackageId = id;
      }),
    setReportMode: (mode) =>
      set((s) => {
        s.reportMode = mode;
        if (s.packages.length > 0) {
          s.packages = [];
          s.activePackageId = null;
          s.currentIssues = [];
          s.undoStack = [];
          s.isSplit = false;
          s.paneBPackageId = null;
          s.fileName = "";
          s.fileNameEdited = false;
          s.hasGeneratedOnce = false;
        }
      }),
    setIssues: (issues) => set((s) => { s.currentIssues = issues; }),
    setValidationCollapsed: (v) => set((s) => { s.validationCollapsed = v; }),
    setHeaderCollapsed: (v) => set((s) => { s.headerCollapsed = v; }),
    setPreviewCollapsed: (v) => set((s) => { s.previewCollapsed = v; }),
    setPreviewZoom: (z) => set((s) => { s.previewZoom = Math.max(50, Math.min(150, z)); }),
    setSplit: (v) =>
      set((s) => {
        if (v && s.packages.length >= 2) {
          s.isSplit = true;
          if (!s.paneBPackageId || !s.packages.find((p) => p.id === s.paneBPackageId) || s.paneBPackageId === s.activePackageId) {
            const idx = s.packages.findIndex((p) => p.id === s.activePackageId);
            const next = s.packages[(idx + 1) % s.packages.length];
            s.paneBPackageId = next?.id ?? null;
          }
        } else {
          s.isSplit = false;
        }
      }),
    setPaneBPackageId: (id) => set((s) => { s.paneBPackageId = id; }),
    setDraggedPackageId: (id) => set((s) => { s.draggedPackageId = id; }),
    setDraggedActivities: (d) => set((s) => { s.draggedActivities = d; }),
    setDraggedGroup: (d) => set((s) => { s.draggedGroup = d; }),
    setHeaderField: (field, value) => set((s) => { (s.header as unknown as Record<string, string>)[field] = value; s.hasGeneratedOnce = false; }),
    setHasGeneratedOnce: (v) => set((s) => { s.hasGeneratedOnce = v; }),
    setFileName: (v, edited) => set((s) => { s.fileName = v; s.fileNameEdited = edited; }),
    setPackageFileName: (packageId, v) =>
      set((s) => {
        const p = s.packages.find((x) => x.id === packageId);
        if (p) { p.fileName = v; p.fileNameEdited = true; }
      }),
    setChartBar: (packageId, v) =>
      set((s) => {
        const p = s.packages.find((x) => x.id === packageId);
        if (p) { p.chartBar = v; s.hasGeneratedOnce = false; }
      }),
    setChartPie: (packageId, v) =>
      set((s) => {
        const p = s.packages.find((x) => x.id === packageId);
        if (p) { p.chartPie = v; s.hasGeneratedOnce = false; }
      }),
    pushUndo: () =>
      set((s) => {
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
      }),
    undo: () =>
      set((s) => {
        const snap = s.undoStack.pop();
        if (!snap) return;
        restoreSnapshot(snap, s);
      }),
    resetParsedState: () =>
      set((s) => {
        s.packages = [];
        s.activePackageId = null;
        s.currentIssues = [];
        s.undoStack = [];
        s.isSplit = false;
        s.paneBPackageId = null;
        s.fileName = "";
        s.fileNameEdited = false;
        s.hasGeneratedOnce = false;
        s.selectedByPane = { "0": new Set(), "1": new Set() };
      }),
    addGroup: (packageId) =>
      set((s) => {
        const snap = snapshotState(s);
        s.undoStack.push(snap); if (s.undoStack.length > 50) s.undoStack.shift();
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (!pkg) return;
        const g: Group = { id: genId(), name: "Novo grupo", performance: 1, activities: [{ id: genId(), description: "", hours: null }] };
        pkg.groups.push(g);
        s.hasGeneratedOnce = false;
      }),
    removeGroup: (groupId, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (!pkg || pkg.groups.length <= 1) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap); if (s.undoStack.length > 50) s.undoStack.shift();
        pkg.groups = pkg.groups.filter((g) => g.id !== groupId);
        pkg.collapsedGroupIds.delete(groupId);
        s.hasGeneratedOnce = false;
      }),
    addActivity: (groupId, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        if (!g) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap); if (s.undoStack.length > 50) s.undoStack.shift();
        g.activities.push({ id: genId(), description: "", hours: null });
        s.hasGeneratedOnce = false;
      }),
    removeActivities: (packageId, items) =>
      set((s) => {
        const pkg = s.packages.find((p) => p.id === packageId);
        if (!pkg || !items.length) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap); if (s.undoStack.length > 50) s.undoStack.shift();
        const byGroup = new Map<string, string[]>();
        items.forEach(({ groupId, activityId }) => {
          if (!byGroup.has(groupId)) byGroup.set(groupId, []);
          byGroup.get(groupId)!.push(activityId);
        });
        byGroup.forEach((aIds, gId) => {
          const gr = pkg.groups.find((g) => g.id === gId);
          if (!gr) return;
          gr.activities = gr.activities.filter((a) => !aIds.includes(a.id));
        });
        s.hasGeneratedOnce = false;
      }),
    updateGroupName: (groupId, name, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        if (g) { g.name = name; s.hasGeneratedOnce = false; }
      }),
    updatePerformance: (groupId, perf, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        if (g) { g.performance = perf; s.hasGeneratedOnce = false; }
      }),
    updateDescription: (groupId, activityId, desc, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        const a = g?.activities.find((ac) => ac.id === activityId);
        if (a) { a.description = desc; s.hasGeneratedOnce = false; }
      }),
    updateExtraHours: (groupId, activityId, hours, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        const a = g?.activities.find((ac) => ac.id === activityId);
        if (a) { a.hours = hours; s.hasGeneratedOnce = false; }
      }),
    updateProjectCode: (value, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (pkg) { pkg.projectCode = value; s.hasGeneratedOnce = false; }
      }),
    updateProjectName: (value, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (pkg) { pkg.projectName = value; s.hasGeneratedOnce = false; }
      }),
    removePackage: (packageId) =>
      set((s) => {
        if (s.packages.length <= 1) return;
        s.isSplit = false;
        s.paneBPackageId = null;
        const idx = s.packages.findIndex((p) => p.id === packageId);
        s.packages.splice(idx, 1);
        if (s.activePackageId === packageId) {
          s.activePackageId = s.packages[Math.max(0, idx - 1)]?.id ?? s.packages[0]?.id ?? null;
        }
        s.undoStack = [];
        s.hasGeneratedOnce = false;
      }),
    mergePackages: (sourceId, targetId) =>
      set((s) => {
        if (sourceId === targetId) return;
        const source = s.packages.find((p) => p.id === sourceId);
        const target = s.packages.find((p) => p.id === targetId);
        if (!source || !target) return;
        s.isSplit = false;
        s.paneBPackageId = null;
        const snap = snapshotState(s);
        s.undoStack.push(snap); if (s.undoStack.length > 50) s.undoStack.shift();
        const claimed = new Set<string>();
        source.groups.forEach((g) => mergeGroupIntoPackage(target, g, claimed));
        s.packages = s.packages.filter((p) => p.id !== sourceId);
        s.activePackageId = targetId;
        s.undoStack = [];
        s.hasGeneratedOnce = false;
      }),
    moveGroupToPackage: (fromPackageId, groupId, toPackageId) =>
      set((s) => {
        if (fromPackageId === toPackageId) return;
        const fromPkg = s.packages.find((p) => p.id === fromPackageId);
        const toPkg = s.packages.find((p) => p.id === toPackageId);
        const group = fromPkg?.groups.find((g) => g.id === groupId);
        if (!fromPkg || !toPkg || !group) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap); if (s.undoStack.length > 50) s.undoStack.shift();
        fromPkg.groups = fromPkg.groups.filter((g) => g.id !== groupId);
        fromPkg.collapsedGroupIds.delete(groupId);
        mergeGroupIntoPackage(toPkg, group, new Set());
        s.hasGeneratedOnce = false;
      }),
    moveActivitiesToGroup: (fromPackageId, items, toPackageId, toGroupId) =>
      set((s) => {
        const toPkg = s.packages.find((p) => p.id === toPackageId);
        const toGroup = toPkg?.groups.find((g) => g.id === toGroupId);
        if (!toGroup || !items.length) return;
        const filtered = items.filter(({ groupId }) => !(fromPackageId === toPackageId && groupId === toGroupId));
        if (!filtered.length) return;
        const fromPkg = s.packages.find((p) => p.id === fromPackageId);
        if (!fromPkg) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap); if (s.undoStack.length > 50) s.undoStack.shift();
        const removed: Activity[] = [];
        const byGroup = new Map<string, string[]>();
        filtered.forEach(({ groupId, activityId }) => {
          if (!byGroup.has(groupId)) byGroup.set(groupId, []);
          byGroup.get(groupId)!.push(activityId);
        });
        byGroup.forEach((aIds, gId) => {
          const gr = fromPkg.groups.find((g) => g.id === gId);
          if (!gr) return;
          const keep: Activity[] = [];
          gr.activities.forEach((a) => {
            if (aIds.includes(a.id)) removed.push(a);
            else keep.push(a);
          });
          gr.activities = keep;
        });
        removed.forEach((a) => mergeActivityIntoGroup(toGroup, a));
        s.hasGeneratedOnce = false;
      }),
    applyChatState: (newState) => {
      // Não empilha snapshot de undo aqui — Chat.tsx já chama pushUndo() ANTES de
      // mandar a requisição (padrão otimista: se der erro, ele mesmo desfaz o
      // push). Empilhar de novo aqui duplicava a entrada e fazia o primeiro
      // Ctrl+Z depois de um edit do chat não fazer nada visível.
      let ok = false;
      set((s) => {
        if (!newState || !Array.isArray(newState.packages) || newState.packages.length !== s.packages.length) return;
        newState.packages.forEach((pkgState, i) => {
          const pkg = s.packages[i];
          pkg.projectCode = pkgState.projectCode || "";
          pkg.projectName = pkgState.projectName || "";
          const oldGroups = pkg.groups;
          const claimedGroupIds = new Set<string>();
          pkg.groups = pkgState.groups.map((g) => {
            const oldGroup = oldGroups.find((og) => !claimedGroupIds.has(og.id) && og.name === g.name);
            if (oldGroup) claimedGroupIds.add(oldGroup.id);
            // casa por descrição pra preservar o id de atividades que não mudaram
            // (mesmo padrão de mergeActivityIntoGroup) — sem isso, TODA atividade
            // ganhava um id novo a cada resposta do chat, mesmo as intocadas, o
            // que forçava o React a remontar a lista inteira (perde foco) e
            // deixava entradas órfãs em selectedByPane apontando pro id antigo.
            const claimedActivityIds = new Set<string>();
            return {
              id: oldGroup?.id ?? genId(),
              name: g.name,
              performance: g.performance,
              activities: g.activities.map((a) => {
                const oldActivity = oldGroup?.activities.find(
                  (oa) => !claimedActivityIds.has(oa.id) && oa.description === a.description
                );
                if (oldActivity) claimedActivityIds.add(oldActivity.id);
                return { id: oldActivity?.id ?? genId(), description: a.description, hours: a.hours };
              }),
            };
          });
          // limpa collapsedGroupIds de grupos que não existem mais (removidos ou
          // renomeados sem correspondência) — senão a entrada fica órfã pra sempre
          const newGroupIds = new Set(pkg.groups.map((g) => g.id));
          pkg.collapsedGroupIds = new Set([...pkg.collapsedGroupIds].filter((id) => newGroupIds.has(id)));
        });
        // seleção de atividades é estado transitório de UI — depois de uma edição
        // em massa os ids que estavam selecionados podem não existir mais (ou
        // apontar pra outra coisa), então limpa em vez de deixar seleção fantasma
        s.selectedByPane = Object.fromEntries(Object.keys(s.selectedByPane).map((paneId) => [paneId, new Set<string>()]));
        s.header.locationDate = newState.locationDate;
        s.header.monthLabel = newState.monthLabel;
        s.header.signer1Name = newState.signer1Name;
        s.header.signer1Company = newState.signer1Company;
        s.header.signer2Name = newState.signer2Name;
        s.header.signer2Company = newState.signer2Company;
        s.hasGeneratedOnce = false;
        ok = true;
      });
      return ok;
    },
    toggleGroupCollapsed: (groupId, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (!pkg) return;
        if (pkg.collapsedGroupIds.has(groupId)) pkg.collapsedGroupIds.delete(groupId);
        else pkg.collapsedGroupIds.add(groupId);
      }),
    toggleSelected: (paneId, key) =>
      set((s) => {
        const setSel = s.selectedByPane[paneId] ?? new Set<string>();
        if (setSel.has(key)) setSel.delete(key);
        else setSel.add(key);
        s.selectedByPane[paneId] = new Set(setSel);
      }),
    setSelected: (paneId, setVal) => set((s) => { s.selectedByPane[paneId] = new Set(setVal); }),
    clearSelected: (paneId) => set((s) => { s.selectedByPane[paneId] = new Set(); }),
  }))
);

export function useActivePackage() {
  const packages = useReportStore((s) => s.packages);
  const activeId = useReportStore((s) => s.activePackageId);
  return packages.find((p) => p.id === activeId) ?? null;
}
