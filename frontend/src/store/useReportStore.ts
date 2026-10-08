import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { WorkPackage, Group, Activity, RowIssue, ReportHeader } from "../api/types";
import {
  StoreState,
  createInitialHeader,
  extractActivitiesFromGroups,
  genId,
  mergeActivityIntoGroup,
  mergeGroupIntoPackage,
  restoreSnapshot,
  snapshotState,
  unionExternalKeys,
} from "./reportState";

export type { DraggedActivities } from "./reportState";
export type { DraggedGroup } from "./reportState";
export { MESES_PT } from "./reportState";
export type { Snapshot } from "./reportState";
export type { StoreState } from "./reportState";
export type { TabBundle } from "./reportState";
export { applyTabBundle } from "./reportState";
export { blankTabBundle } from "./reportState";
export { clonePackages } from "./reportState";
export { createInitialHeader } from "./reportState";
export { extractActivitiesFromGroups } from "./reportState";
export { genId } from "./reportState";
export { jsonReplacer } from "./reportState";
export { jsonReviver } from "./reportState";
export { mergeActivityIntoGroup } from "./reportState";
export { mergeGroupIntoPackage } from "./reportState";
export { reportTabBundle } from "./reportState";
export { restoreSnapshot } from "./reportState";
export { serializeTabBundle } from "./reportState";
export { snapshotState } from "./reportState";

export const useReportStore = create<StoreState>()(
  immer((set, get) => ({
    packages: [],
    showImportCard: true,
    importSource: "file",
    importByClient: false,
    importSelectedClient: "",
    importSelectedProjectIds: new Set(),
    importClientReportMode: "pacote",
    importPeriodMode: "single",
    importEndMonthLabel: createInitialHeader().monthLabel,
    includePerformanceInExport: false,
    activePackageId: null,
    reportMode: "single",
    currentIssues: [],
    validationCollapsed: false,
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
        s.showImportCard = pkgs.length === 0;
        s.activePackageId = activeId ?? pkgs[0]?.id ?? null;
        s.undoStack = [];
        s.hasGeneratedOnce = false;
        s.isSplit = false;
        s.paneBPackageId = null;
        // nome de quem assina não pode vir de um relatório anterior — cada
        // carregamento novo (arquivo ou banco) exige preencher de novo.
        s.header.signer1Name = "";
        s.header.signer2Name = "";
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
          s.showImportCard = true;
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
    setIssues: (issues) =>
      set((s) => {
        s.currentIssues = issues;
      }),
    setValidationCollapsed: (v) =>
      set((s) => {
        s.validationCollapsed = v;
      }),
    setPreviewZoom: (z) =>
      set((s) => {
        s.previewZoom = Math.max(50, Math.min(150, z));
      }),
    setSplit: (v) =>
      set((s) => {
        if (v && s.packages.length >= 2) {
          s.isSplit = true;
          if (
            !s.paneBPackageId ||
            !s.packages.find((p) => p.id === s.paneBPackageId) ||
            s.paneBPackageId === s.activePackageId
          ) {
            const idx = s.packages.findIndex((p) => p.id === s.activePackageId);
            const next = s.packages[(idx + 1) % s.packages.length];
            s.paneBPackageId = next?.id ?? null;
          }
        } else {
          s.isSplit = false;
        }
      }),
    setPaneBPackageId: (id) =>
      set((s) => {
        s.paneBPackageId = id;
      }),
    setDraggedPackageId: (id) =>
      set((s) => {
        s.draggedPackageId = id;
      }),
    setDraggedActivities: (d) =>
      set((s) => {
        s.draggedActivities = d;
      }),
    setDraggedGroup: (d) =>
      set((s) => {
        s.draggedGroup = d;
      }),
    setHeaderField: (field, value) =>
      set((s) => {
        (s.header as unknown as Record<string, string>)[field] = value;
        s.hasGeneratedOnce = false;
      }),
    setHasGeneratedOnce: (v) =>
      set((s) => {
        s.hasGeneratedOnce = v;
      }),
    setFileName: (v, edited) =>
      set((s) => {
        s.fileName = v;
        s.fileNameEdited = edited;
      }),
    setPackageFileName: (packageId, v) =>
      set((s) => {
        const p = s.packages.find((x) => x.id === packageId);
        if (p) {
          p.fileName = v;
          p.fileNameEdited = true;
        }
      }),
    setChartBar: (packageId, v) =>
      set((s) => {
        const p = s.packages.find((x) => x.id === packageId);
        if (p) {
          p.chartBar = v;
          s.hasGeneratedOnce = false;
        }
      }),
    setChartPie: (packageId, v) =>
      set((s) => {
        const p = s.packages.find((x) => x.id === packageId);
        if (p) {
          p.chartPie = v;
          s.hasGeneratedOnce = false;
        }
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
    setShowImportCard: (v) =>
      set((s) => {
        s.showImportCard = v;
      }),
    setImportSource: (v) =>
      set((s) => {
        s.importSource = v;
      }),
    setImportByClient: (v) =>
      set((s) => {
        s.importByClient = v;
      }),
    setImportSelectedClient: (v) =>
      set((s) => {
        s.importSelectedClient = v;
      }),
    setImportSelectedProjectIds: (v) =>
      set((s) => {
        s.importSelectedProjectIds = v;
      }),
    setImportClientReportMode: (v) =>
      set((s) => {
        s.importClientReportMode = v;
      }),
    setImportPeriodMode: (v) =>
      set((s) => {
        s.importPeriodMode = v;
      }),
    setImportEndMonthLabel: (v) =>
      set((s) => {
        s.importEndMonthLabel = v;
      }),
    setIncludePerformanceInExport: (v) =>
      set((s) => {
        s.includePerformanceInExport = v;
      }),
    resetParsedState: () =>
      set((s) => {
        s.packages = [];
        s.showImportCard = true;
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
    resetForNewImport: () =>
      set((s) => {
        const initialHeader = createInitialHeader();
        s.packages = [];
        s.showImportCard = true;
        s.importSource = "file";
        s.importByClient = false;
        s.importSelectedClient = "";
        s.importSelectedProjectIds = new Set();
        s.importClientReportMode = "pacote";
        s.importPeriodMode = "single";
        s.importEndMonthLabel = initialHeader.monthLabel;
        s.includePerformanceInExport = false;
        s.activePackageId = null;
        s.reportMode = "single";
        s.currentIssues = [];
        s.validationCollapsed = false;
        s.previewZoom = 100;
        s.isSplit = false;
        s.paneBPackageId = null;
        s.draggedPackageId = null;
        s.draggedActivities = null;
        s.draggedGroup = null;
        s.hasGeneratedOnce = false;
        s.header = initialHeader;
        s.fileName = "";
        s.fileNameEdited = false;
        s.undoStack = [];
        s.selectedByPane = { "0": new Set(), "1": new Set() };
      }),
    addGroup: (packageId) =>
      set((s) => {
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (!pkg) return;
        const g: Group = {
          id: genId(),
          name: "Novo grupo",
          performance: 1,
          activities: [{ id: genId(), description: "", hours: null, extra: true }],
        };
        pkg.groups.push(g);
        s.hasGeneratedOnce = false;
      }),
    removeGroup: (groupId, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (!pkg || pkg.groups.length <= 1) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
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
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
        g.activities.push({ id: genId(), description: "", hours: null, extra: true });
        s.hasGeneratedOnce = false;
      }),
    addActivitiesFromIssues: (groupId, packageId, items) => {
      let added = false;
      set((s) => {
        const pkg = s.packages.find((p) => p.id === packageId);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        if (!g || !items.length) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
        items.forEach(({ description, hours }) => {
          g.activities.push({ id: genId(), description, hours, extra: false });
        });
        s.hasGeneratedOnce = false;
        added = true;
      });
      return added;
    },
    applyExternalHours: (placements) => {
      let applied = false;
      set((s) => {
        const targets = placements.flatMap((p) => {
          const group = s.packages.find((pkg) => pkg.id === p.packageId)?.groups.find((g) => g.id === p.groupId);
          return group ? [{ group, p }] : [];
        });
        if (!targets.length) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
        targets.forEach(({ group, p }) => {
          mergeActivityIntoGroup(group, {
            id: genId(),
            description: p.description,
            hours: p.hours,
            extra: false,
            externalKeys: [p.key],
          });
        });
        s.hasGeneratedOnce = false;
        applied = true;
      });
      return applied;
    },
    removeActivities: (packageId, items) =>
      set((s) => {
        const pkg = s.packages.find((p) => p.id === packageId);
        if (!pkg || !items.length) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
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
        if (g) {
          g.name = name;
          s.hasGeneratedOnce = false;
        }
      }),
    updatePerformance: (groupId, perf, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        if (g) {
          g.performance = perf;
          s.hasGeneratedOnce = false;
        }
      }),
    updateDescription: (groupId, activityId, desc, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        const a = g?.activities.find((ac) => ac.id === activityId);
        if (a) {
          a.description = desc;
          s.hasGeneratedOnce = false;
        }
      }),
    updateExtraHours: (groupId, activityId, hours, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        const g = pkg?.groups.find((gr) => gr.id === groupId);
        const a = g?.activities.find((ac) => ac.id === activityId);
        if (a) {
          a.hours = hours;
          s.hasGeneratedOnce = false;
        }
      }),
    updateProjectCode: (value, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (pkg) {
          pkg.projectCode = value;
          s.hasGeneratedOnce = false;
        }
      }),
    updateProjectName: (value, packageId) =>
      set((s) => {
        const pid = packageId ?? s.activePackageId;
        const pkg = s.packages.find((p) => p.id === pid);
        if (pkg) {
          pkg.projectName = value;
          s.hasGeneratedOnce = false;
        }
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
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
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
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
        fromPkg.groups = fromPkg.groups.filter((g) => g.id !== groupId);
        fromPkg.collapsedGroupIds.delete(groupId);
        mergeGroupIntoPackage(toPkg, group, new Set());
        s.hasGeneratedOnce = false;
      }),
    moveGroupToPosition: (fromPackageId, groupId, toPackageId, beforeGroupId) =>
      set((s) => {
        const fromPkg = s.packages.find((p) => p.id === fromPackageId);
        const toPkg = s.packages.find((p) => p.id === toPackageId);
        const group = fromPkg?.groups.find((g) => g.id === groupId);
        if (!fromPkg || !toPkg || !group) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();

        fromPkg.groups = fromPkg.groups.filter((g) => g.id !== groupId);
        const insertAt = beforeGroupId ? toPkg.groups.findIndex((g) => g.id === beforeGroupId) : -1;
        if (insertAt === -1) toPkg.groups.push(group);
        else toPkg.groups.splice(insertAt, 0, group);
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
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
        const removed = extractActivitiesFromGroups(fromPkg, filtered);
        removed.forEach((a) => mergeActivityIntoGroup(toGroup, a));
        s.hasGeneratedOnce = false;
      }),
    mergeActivitiesIntoActivity: (fromPackageId, items, toPackageId, toGroupId, toActivityId) =>
      set((s) => {
        const toPkg = s.packages.find((p) => p.id === toPackageId);
        const toGroup = toPkg?.groups.find((g) => g.id === toGroupId);
        const toActivity = toGroup?.activities.find((a) => a.id === toActivityId);
        if (!toGroup || !toActivity || !items.length) return;
        // ignora a própria atividade-alvo se ela estiver entre as arrastadas
        // (ex: seleção múltipla incluindo o destino) — não faz sentido somá-la
        // nela mesma.
        const filtered = items.filter((it) => it.activityId !== toActivityId);
        if (!filtered.length) return;
        const fromPkg = s.packages.find((p) => p.id === fromPackageId);
        if (!fromPkg) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();
        const removed = extractActivitiesFromGroups(fromPkg, filtered);
        // sempre soma no destino, nunca casa por descrição — diferente de
        // mergeActivityIntoGroup: o nome que sobra é sempre o da atividade
        // que ficou parada (o destino), nunca o da arrastada.
        const somaArrastada = removed.reduce((acc, a) => acc + (parseFloat(String(a.hours)) || 0), 0);
        toActivity.hours = Math.round(((parseFloat(String(toActivity.hours)) || 0) + somaArrastada) * 1000) / 1000;
        const keys = removed.reduce<string[] | undefined>(
          (acc, a) => unionExternalKeys(acc, a.externalKeys),
          toActivity.externalKeys,
        );
        if (keys) toActivity.externalKeys = keys;
        s.hasGeneratedOnce = false;
      }),
    moveActivitiesToPosition: (fromPackageId, items, toPackageId, toGroupId, beforeActivityId) =>
      set((s) => {
        const toPkg = s.packages.find((p) => p.id === toPackageId);
        const toGroup = toPkg?.groups.find((g) => g.id === toGroupId);
        if (!toGroup || !items.length) return;
        const fromPkg = s.packages.find((p) => p.id === fromPackageId);
        if (!fromPkg) return;
        const snap = snapshotState(s);
        s.undoStack.push(snap);
        if (s.undoStack.length > 50) s.undoStack.shift();

        // remove das origens (pode incluir o próprio `toGroup`, se for
        // reordenar dentro do mesmo grupo — `fromPkg.groups.find` devolve a
        // MESMA referência que `toGroup` nesse caso, então a mutação de
        // `gr.activities` dentro do helper já atualiza `toGroup.activities`
        // também). A ordem devolvida já é a que `moveActivitiesToPosition`
        // precisa: pela posição original nos grupos de origem.
        const orderedMoved = extractActivitiesFromGroups(fromPkg, items);
        if (!orderedMoved.length) return;

        // procurado DEPOIS da remoção acima: se `beforeActivityId` era uma
        // das próprias atividades arrastadas (raro — ex: multi-seleção
        // contígua soltando "depois" de um vizinho que também foi
        // selecionado), ela já não existe mais em `toGroup.activities` e o
        // findIndex abaixo devolve -1, caindo no fallback de inserir no fim.
        const insertAt = beforeActivityId ? toGroup.activities.findIndex((a) => a.id === beforeActivityId) : -1;
        if (insertAt === -1) toGroup.activities.push(...orderedMoved);
        else toGroup.activities.splice(insertAt, 0, ...orderedMoved);
        s.hasGeneratedOnce = false;
      }),
    applyTranslation: (packageId, translations, language) =>
      set((s) => {
        const pkg = s.packages.find((p) => p.id === packageId);
        if (!pkg) return;
        const byId = new Map(translations.map((t) => [t.id, t.text]));
        pkg.groups.forEach((g) => {
          const translatedName = byId.get(g.id);
          if (translatedName !== undefined) g.name = translatedName;
          g.activities.forEach((a) => {
            const translatedDesc = byId.get(a.id);
            if (translatedDesc !== undefined) a.description = translatedDesc;
          });
        });
        pkg.language = language;
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
          // Casa por `id` (estável, atribuído pelo backend — ver chat_ops.py) em
          // vez de por nome/descrição: grupo/atividade que o chat não tocou
          // mantém exatamente o mesmo id; grupo/atividade novo (add_group/
          // add_activity) já chega com um id novo do backend, nunca colide com
          // um existente. Sem isso, TODA atividade ganhava um id novo a cada
          // resposta do chat, mesmo as intocadas — forçava o React a remontar a
          // lista inteira (perde foco) e deixava entradas órfãs em
          // selectedByPane apontando pro id antigo.
          const oldActivitiesById = new Map(pkg.groups.flatMap((g) => g.activities.map((a) => [a.id, a] as const)));
          pkg.groups = pkgState.groups.map((g) => ({
            id: g.id,
            name: g.name,
            performance: g.performance,
            activities: g.activities.map((a) => {
              const oldActivity = oldActivitiesById.get(a.id);
              return {
                id: a.id,
                description: a.description,
                hours: a.hours,
                // preserva a marcação de quem já existia; pra atividade nova
                // que o chat criou, trata como "extra" se veio sem horas
                extra: oldActivity?.extra ?? a.hours === null,
                // o chat não conhece as chaves de horas externas: quem já tinha continua com elas
                ...(oldActivity?.externalKeys ? { externalKeys: oldActivity.externalKeys } : {}),
              };
            }),
          }));
          // limpa collapsedGroupIds de grupos que não existem mais (removidos) —
          // senão a entrada fica órfã pra sempre
          const newGroupIds = new Set(pkg.groups.map((g) => g.id));
          pkg.collapsedGroupIds = new Set([...pkg.collapsedGroupIds].filter((id) => newGroupIds.has(id)));
        });
        // seleção de atividades é estado transitório de UI — depois de uma edição
        // em massa os ids que estavam selecionados podem não existir mais (ou
        // apontar pra outra coisa), então limpa em vez de deixar seleção fantasma
        s.selectedByPane = Object.fromEntries(
          Object.keys(s.selectedByPane).map((paneId) => [paneId, new Set<string>()]),
        );
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
    setSelected: (paneId, setVal) =>
      set((s) => {
        s.selectedByPane[paneId] = new Set(setVal);
      }),
    clearSelected: (paneId) =>
      set((s) => {
        s.selectedByPane[paneId] = new Set();
      }),
  })),
);

export function useActivePackage() {
  const packages = useReportStore((s) => s.packages);
  const activeId = useReportStore((s) => s.activePackageId);
  return packages.find((p) => p.id === activeId) ?? null;
}
