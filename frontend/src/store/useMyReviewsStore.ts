import { create } from "zustand";
import { useAuthStore } from "./useAuthStore";
import { api } from "../utils/autoApi";
import type { AutoBadges, AutoStatus, ReviewComment } from "./useAutoGenerationStore";

/** "Minhas revisões": relatórios da geração automática atribuídos a quem está
 * logado (qualquer papel) e os contadores da sidebar. Contrato em
 * `backend/app/api/routers/my_reviews.py`. */

export type ReviewItem = {
  id: string;
  competence: string;
  // geração personalizada: o período do recorte no lugar do mês
  scope_json?: { label: string; summary: string } | null;
  project_name: string;
  client: string | null;
  status: AutoStatus;
  draft_version: number;
  source_hours: number | null;
  updated_at: string;
  badges: AutoBadges;
  last_comment: ReviewComment | null;
};

export type ReviewSummary = { to_review: number; assigned: number; awaiting_approval: number | null };

interface MyReviewsState {
  toReview: ReviewItem[];
  awaitingApproval: ReviewItem[];
  done: ReviewItem[];
  loaded: boolean;
  loading: boolean;
  error: string;
  summary: ReviewSummary | null;
  _loadedForLogin: string | null;

  load: () => Promise<void>;
  loadSummary: () => Promise<void>;
  /** Depois de uma ação que muda contagem (atribuir, mandar, devolver, aprovar). */
  refreshAll: () => void;
}

function currentLogin(): string | null {
  return useAuthStore.getState().user?.login ?? null;
}

export const useMyReviewsStore = create<MyReviewsState>((set, get) => ({
  toReview: [],
  awaitingApproval: [],
  done: [],
  loaded: false,
  loading: false,
  error: "",
  summary: null,
  _loadedForLogin: null,

  load: async () => {
    const login = currentLogin();
    if (get()._loadedForLogin !== login) {
      set({ toReview: [], awaitingApproval: [], done: [], loaded: false, summary: null, _loadedForLogin: login });
    }
    set({ loading: true, error: "" });
    try {
      const data = await api<{ to_review: ReviewItem[]; awaiting_approval: ReviewItem[]; done: ReviewItem[] }>("/my-reviews");
      if (get()._loadedForLogin !== login) return;
      set({
        toReview: data.to_review, awaitingApproval: data.awaiting_approval, done: data.done,
        loaded: true, loading: false,
        summary: {
          to_review: data.to_review.length,
          assigned: data.to_review.length + data.awaiting_approval.length + data.done.length,
          awaiting_approval: get().summary?.awaiting_approval ?? null,
        },
      });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e), loading: false });
    }
  },

  loadSummary: async () => {
    const login = currentLogin();
    if (!login) return;
    try {
      const summary = await api<ReviewSummary>("/my-reviews/summary");
      if (currentLogin() !== login) return;
      if (get()._loadedForLogin !== login) {
        set({ toReview: [], awaitingApproval: [], done: [], loaded: false, _loadedForLogin: login });
      }
      set({ summary });
    } catch {
      // contador é só aviso: sem ele a sidebar continua funcionando
    }
  },

  refreshAll: () => {
    void get().loadSummary();
    if (get().loaded) void get().load();
  },
}));

/** Outro usuário no mesmo navegador: nada da lista do anterior fica. */
useAuthStore.subscribe((state, prev) => {
  if (state.user?.login !== prev.user?.login) {
    useMyReviewsStore.setState({
      toReview: [], awaitingApproval: [], done: [], loaded: false, summary: null, _loadedForLogin: state.user?.login ?? null,
    });
  }
});
