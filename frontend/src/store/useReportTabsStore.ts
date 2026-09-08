import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { genId, useReportStore, serializeTabBundle, applyTabBundle, blankTabBundle } from "./useReportStore";

const STORAGE_KEY = "relatorio-horas:tabs:v1";
// tempo parado digitando antes de gravar em disco — junta várias teclas
// numa escrita só, sem deixar passar tanto tempo que uma queda de energia
// de verdade perca trabalho relevante.
const AUTOSAVE_DEBOUNCE_MS = 600;

export type ReportTabMeta = {
  id: string;
  label: string;
  // `false` = rótulo ainda é o automático ("Guia N" ou o nome do projeto
  // importado) — pode ser sobrescrito sozinho; `true` = usuário renomeou à
  // mão, nunca mais muda sozinho (mesmo padrão de `fileNameEdited`).
  labelEdited: boolean;
};

interface ReportTabsState {
  tabs: ReportTabMeta[];
  activeTabId: string;
  bundles: Record<string, string>;

  addTab: () => void;
  closeTab: (id: string) => void;
  switchTab: (id: string) => void;
  renameTab: (id: string, label: string) => void;
  persist: () => void;
}

let suppressAutosave = false;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleAutosave() {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => useReportTabsStore.getState().persist(), AUTOSAVE_DEBOUNCE_MS);
}

/** Troca o conteúdo carregado em `useReportStore` sem passar pelo ciclo
 * normal de autosave/auto-rename (evita reagir à própria troca como se
 * fosse uma edição do usuário). */
function loadBundleIntoLiveStore(bundleStr: string) {
  suppressAutosave = true;
  useReportStore.setState((s) => {
    applyTabBundle(bundleStr, s);
  });
  suppressAutosave = false;
}

const DEFAULT_TAB_ID = genId();

export const useReportTabsStore = create<ReportTabsState>()(
  immer((set, get) => ({
    tabs: [{ id: DEFAULT_TAB_ID, label: "Guia 1", labelEdited: false }],
    activeTabId: DEFAULT_TAB_ID,
    bundles: { [DEFAULT_TAB_ID]: blankTabBundle() },

    addTab: () => {
      const currentBundle = serializeTabBundle(useReportStore.getState());
      const newId = genId();
      set((s) => {
        s.bundles[s.activeTabId] = currentBundle;
        s.tabs.push({ id: newId, label: `Guia ${s.tabs.length + 1}`, labelEdited: false });
        s.bundles[newId] = blankTabBundle();
        s.activeTabId = newId;
      });
      loadBundleIntoLiveStore(get().bundles[newId]);
      get().persist();
    },

    closeTab: (id) => {
      const s = get();
      if (s.tabs.length <= 1) return; // nunca fecha a última guia
      const idx = s.tabs.findIndex((t) => t.id === id);
      if (idx === -1) return;
      const wasActive = s.activeTabId === id;
      set((st) => {
        st.tabs.splice(idx, 1);
        delete st.bundles[id];
      });
      if (wasActive) {
        const nextId = get().tabs[Math.max(0, idx - 1)]!.id;
        set((st) => {
          st.activeTabId = nextId;
        });
        loadBundleIntoLiveStore(get().bundles[nextId]);
      }
      get().persist();
    },

    switchTab: (id) => {
      const s = get();
      if (id === s.activeTabId || !s.bundles[id]) return;
      const currentBundle = serializeTabBundle(useReportStore.getState());
      set((st) => {
        st.bundles[st.activeTabId] = currentBundle;
        st.activeTabId = id;
      });
      loadBundleIntoLiveStore(get().bundles[id]);
      get().persist();
    },

    renameTab: (id, label) => {
      const trimmed = label.trim();
      set((s) => {
        const t = s.tabs.find((tab) => tab.id === id);
        if (t && trimmed) {
          t.label = trimmed;
          t.labelEdited = true;
        }
      });
      get().persist();
    },

    persist: () => {
      const s = get();
      try {
        const bundles = { ...s.bundles, [s.activeTabId]: serializeTabBundle(useReportStore.getState()) };
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ version: 1, activeTabId: s.activeTabId, tabs: s.tabs, bundles })
        );
        set({ bundles });
      } catch {
        // localStorage indisponível (modo privado) ou cheio (cota
        // estourada) — não pode derrubar o que o usuário está digitando;
        // só esse ciclo de autosave falha, o próximo debounce tenta de novo.
      }
    },
  }))
);

// reage a QUALQUER mudança na guia ativa: agenda a gravação em disco
// (debounced) e, na primeira vez que um import preenche `packages` do
// zero, renomeia a guia sozinha pro nome do projeto (só se o usuário ainda
// não tiver renomeado à mão).
useReportStore.subscribe((state, prevState) => {
  if (suppressAutosave) return;
  if (prevState.packages.length === 0 && state.packages.length > 0) {
    const ts = useReportTabsStore.getState();
    const active = ts.tabs.find((t) => t.id === ts.activeTabId);
    if (active && !active.labelEdited) {
      const label = state.packages[0]?.projectName?.trim() || state.packages[0]?.projectCode?.trim();
      if (label) {
        useReportTabsStore.setState((s) => {
          const t = s.tabs.find((tab) => tab.id === s.activeTabId);
          if (t) t.label = label;
        });
      }
    }
  }
  scheduleAutosave();
});

/** Lê o `localStorage` uma vez no boot do app e restaura as guias salvas —
 * chamado aqui mesmo, no escopo do módulo (não num `useEffect`), pra
 * rodar antes de qualquer componente pintar a tela: evita um "flash" da
 * guia em branco padrão antes do conteúdo salvo aparecer. Se não existir
 * nada salvo, ou o que existir estiver corrompido/em formato inesperado,
 * mantém o estado inicial de uma guia em branco (não quebra o app). */
function hydrate() {
  let raw: string | null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    return;
  }
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw) as {
      tabs?: unknown;
      activeTabId?: unknown;
      bundles?: unknown;
    };
    if (!Array.isArray(parsed.tabs) || parsed.tabs.length === 0 || typeof parsed.bundles !== "object" || !parsed.bundles) {
      return;
    }
    const tabs = parsed.tabs as ReportTabMeta[];
    const bundles = parsed.bundles as Record<string, string>;
    const activeTabId =
      typeof parsed.activeTabId === "string" && tabs.some((t) => t.id === parsed.activeTabId)
        ? parsed.activeTabId
        : tabs[0].id;
    if (!bundles[activeTabId]) return;
    useReportTabsStore.setState({ tabs, activeTabId, bundles });
    loadBundleIntoLiveStore(bundles[activeTabId]);
  } catch {
    // JSON inválido — ignora e segue com a guia em branco padrão
  }
}

hydrate();

/** Uma guia inativa só existe como bundle serializado (não está carregada
 * em `useReportStore`) — usado pra decidir se fechar essa guia deve pedir
 * confirmação (guia com pacote/grupo dentro) ou fechar direto (guia vazia).
 * `try/catch` porque um bundle corrompido não deve travar o botão de
 * fechar — trata como "sem conteúdo" nesse caso raro. */
export function bundleHasContent(bundleStr: string | undefined): boolean {
  if (!bundleStr) return false;
  try {
    const parsed = JSON.parse(bundleStr) as { packages?: unknown[] };
    return Array.isArray(parsed.packages) && parsed.packages.length > 0;
  } catch {
    return false;
  }
}
