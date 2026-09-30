import { create } from "zustand";

export type ToastKind = "success" | "error" | "info";

export type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
  /** Ação no próprio aviso ("Desfazer"): clicar executa e fecha. */
  actionLabel?: string;
  onAction?: () => void;
  /** Quanto fica na tela, em ms (pausa com o mouse em cima ou o foco dentro). */
  duration: number;
};

export type ToastOptions = { actionLabel?: string; onAction?: () => void; duration?: number };

/** Quantos avisos aparecem ao mesmo tempo; o mais antigo sai quando chega um novo além disso. */
export const MAX_TOASTS = 4;

const DEFAULT_DURATION: Record<ToastKind, number> = { success: 4000, info: 5000, error: 8000 };
/** Aviso com ação precisa de tempo pra dar pra clicar. */
const MIN_DURATION_WITH_ACTION = 8000;

let nextId = 1;

interface ToastState {
  toasts: Toast[];
  push: (kind: ToastKind, message: string, options?: ToastOptions) => number;
  dismiss: (id: number) => void;
  clear: () => void;
}

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (kind, message, options = {}) => {
    // o mesmo aviso já na tela não empilha (clicar duas vezes em algo que falha não enche o canto)
    const same = get().toasts.find((t) => t.kind === kind && t.message === message);
    if (same) return same.id;
    const base = options.duration ?? DEFAULT_DURATION[kind];
    const duration = options.onAction ? Math.max(base, MIN_DURATION_WITH_ACTION) : base;
    const toast: Toast = {
      id: nextId++,
      kind,
      message,
      duration,
      actionLabel: options.actionLabel,
      onAction: options.onAction,
    };
    set((s) => ({ toasts: [...s.toasts, toast].slice(-MAX_TOASTS) }));
    return toast.id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}));

/** Avisos do app, de qualquer lugar (não precisa de hook): `toast.success("Relatório gerado")`.
 * Precisa do `<ToastHost />` montado uma vez (main.tsx). Erro fica mais tempo que sucesso. */
export const toast = {
  success: (message: string, options?: ToastOptions) => useToastStore.getState().push("success", message, options),
  error: (message: string, options?: ToastOptions) => useToastStore.getState().push("error", message, options),
  info: (message: string, options?: ToastOptions) => useToastStore.getState().push("info", message, options),
};
