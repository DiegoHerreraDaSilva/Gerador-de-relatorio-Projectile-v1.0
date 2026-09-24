import { create } from "zustand";
import { useAuthStore } from "./useAuthStore";

export type ChartVisualization = {
  type: "bar" | "horizontal_bar" | "line";
  title: string;
  categories: string[];
  series: { name: string; data: (number | null)[] }[];
  unit: string;
};
export type KpiVisualization = { type: "kpi"; title: string; value: number; unit: string };
export type Visualization = ChartVisualization | KpiVisualization;

export type AnalyticsTable = {
  title: string;
  columns: string[];
  rows: (string | number | null)[][];
  truncated: boolean;
};

type ChatContext = {
  conversation_id: string;
  last_intent: string | null;
  last_filters: Record<string, string | null> | null;
};

export type AnalyticsChatResponse = {
  conversation_id: string;
  route: string;
  intent: string | null;
  reply: string;
  visualizations: Visualization[];
  tables: AnalyticsTable[];
  metadata: {
    source: string | null;
    source_label: string | null;
    period_label?: string;
    compared_period_label?: string;
    classifier: string;
    claude_calls: number;
  };
  context: ChatContext;
};

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; response: AnalyticsChatResponse }
  | { id: string; role: "error"; text: string };

interface AnalyticsChatState {
  messages: ChatMessage[];
  /** contexto curto devolvido pelo backend (última intent/filtros) — vai de
   * volta em cada pergunta; é o que permite "e em agosto?". */
  context: ChatContext | null;
  sending: boolean;
  _loadedForLogin: string | null;
  ensureUser: () => void;
  send: (message: string) => Promise<void>;
  reset: () => void;
}

let nextId = 0;
const newId = () => `m${++nextId}`;

export const useAnalyticsChatStore = create<AnalyticsChatState>((set, get) => ({
  messages: [],
  context: null,
  sending: false,
  _loadedForLogin: null,

  // a store sobrevive ao logout — sem isso o próximo usuário do mesmo
  // navegador veria a conversa (com os números) do anterior.
  ensureUser: () => {
    const login = useAuthStore.getState().user?.login ?? null;
    if (get()._loadedForLogin !== login) {
      set({ messages: [], context: null, sending: false, _loadedForLogin: login });
    }
  },

  send: async (message) => {
    const text = message.trim();
    if (!text || get().sending) return;
    get().ensureUser();
    const login = get()._loadedForLogin;
    set((s) => ({ messages: [...s.messages, { id: newId(), role: "user", text }], sending: true }));
    try {
      const res = await fetch("/analytics/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, context: get().context }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const detail = typeof body?.detail === "string" ? body.detail : null;
        throw new Error(
          res.status === 401
            ? "Sua sessão expirou. Entre novamente."
            : detail || "Não consegui responder agora. Tenta de novo em instantes."
        );
      }
      const data: AnalyticsChatResponse = await res.json();
      if (get()._loadedForLogin !== login) return;
      set((s) => ({
        messages: [...s.messages, { id: newId(), role: "assistant", response: data }],
        context: data.context,
      }));
    } catch (e) {
      if (get()._loadedForLogin !== login) return;
      const textError = e instanceof Error ? e.message : "Não consegui responder agora.";
      set((s) => ({ messages: [...s.messages, { id: newId(), role: "error", text: textError }] }));
    } finally {
      set({ sending: false });
    }
  },

  reset: () => set({ messages: [], context: null }),
}));
