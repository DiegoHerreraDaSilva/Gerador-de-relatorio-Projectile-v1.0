import { create } from "zustand";

type User = { name: string; login: string; email: string };

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
      const user = await res.json();
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
    const user = await res.json();
    set({ user, status: "authenticated" });
  },

  logout: async () => {
    await fetch("/auth/logout", { method: "POST" });
    set({ user: null, status: "unauthenticated" });
  },
}));
