import { create } from "zustand";
import type { MyHoursEntry } from "../utils/myHours";

export type MyHoursPeriod = "current_month" | "last_3" | "last_6" | "last_12";

type MyHoursResponse = {
  entries: MyHoursEntry[];
  business_days_expected: number;
  period: MyHoursPeriod;
  start_date: string;
  end_date: string;
};

interface MyHoursState {
  entries: MyHoursEntry[];
  businessDaysExpected: number;
  period: MyHoursPeriod;
  error: string;
  loaded: boolean;
  refreshing: boolean;
  _inFlight: boolean;
  _pending: boolean;

  // mesmo padrão de cache de useManagementStore.ts — `force` ignora o cache
  // do frontend (troca de período/botão "Atualizar"); sem `force`, busca só
  // na 1ª vez que a tela é aberta.
  load: (force?: boolean) => Promise<void>;
  setPeriod: (period: MyHoursPeriod) => void;
  setError: (message: string) => void;
}

export const useMyHoursStore = create<MyHoursState>((set, get) => ({
  entries: [],
  businessDaysExpected: 0,
  period: "current_month",
  error: "",
  loaded: false,
  refreshing: false,
  _inFlight: false,
  _pending: false,

  load: async (force = false) => {
    if (get().loaded && !force) return;
    if (get()._inFlight) {
      set({ _pending: true });
      return;
    }
    set({ refreshing: true, _inFlight: true, _pending: false });
    try {
      const res = await fetch(`/my-hours?period=${get().period}`);
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const data: MyHoursResponse = await res.json();
      set({
        entries: data.entries,
        businessDaysExpected: data.business_days_expected,
        loaded: true,
        error: "",
      });
    } catch {
      set({ error: "Não consegui carregar suas horas. Tenta de novo em instantes." });
    } finally {
      set({ refreshing: false, _inFlight: false });
      if (get()._pending) get().load(true);
    }
  },

  setPeriod: (period) => {
    set({ period, loaded: false });
    get().load(true);
  },

  setError: (message) => set({ error: message }),
}));
