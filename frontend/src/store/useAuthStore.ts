import { create } from "zustand";

type User = {
  name: string;
  login: string;
  email: string;
  isManager: boolean;
  isCoordinator: boolean;
  translateAllowed: boolean;
};

function toUser(raw: any): User {
  return {
    name: raw.name,
    login: raw.login,
    email: raw.email,
    isManager: Boolean(raw.is_manager),
    isCoordinator: Boolean(raw.is_coordinator),
    translateAllowed: Boolean(raw.is_translate_allowed),
  };
}

/** Gerente ou coordenador: Diagnóstico e busca por cliente/projeto na
 * importação. Painel de Gerência e Analytics continuam só com `isManager`.
 * Só esconde/mostra tela — quem barra de verdade é o backend
 * (`require_manager_or_coordinator`). */
export function hasCoordinatorAccess(user: User | null): boolean {
  return Boolean(user && (user.isManager || user.isCoordinator));
}

interface AuthState {
  user: User | null;
  status: "loading" | "authenticated" | "unauthenticated";
  checkSession: () => Promise<void>;
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: "loading",

  checkSession: async () => {
    try {
      const res = await fetch("/auth/me");
      if (!res.ok) {
        set({ user: null, status: "unauthenticated" });
        return;
      }
      const user = toUser(await res.json());
      set({ user, status: "authenticated" });
    } catch {
      set({ user: null, status: "unauthenticated" });
    }
  },

  login: async (login, password) => {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error((data as any)?.detail || "Login ou senha incorretos.");
    }
    const user = toUser(await res.json());
    set({ user, status: "authenticated" });
  },

  logout: async () => {
    await fetch("/auth/logout", { method: "POST" });
    set({ user: null, status: "unauthenticated" });
  },
}));
