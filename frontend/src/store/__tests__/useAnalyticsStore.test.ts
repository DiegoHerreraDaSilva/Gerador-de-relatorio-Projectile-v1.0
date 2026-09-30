import { afterEach, describe, expect, it, vi } from "vitest";
import { useAnalyticsStore, type SystemHealth } from "../useAnalyticsStore";

const HEALTH: SystemHealth = {
  generation: {
    window_days: 30,
    total: 4,
    failed: 1,
    failure_rate: 0.25,
    avg_duration_ms: 2000,
    p95_duration_ms: 3000,
    last_failure: {
      started_at: "2026-09-29T11:00:00",
      format: "xlsx",
      error_code: "E_GEN",
      error_message: "boom",
    },
  },
  artifacts: { count: 3, bytes: 9 },
  auto_generation: {
    competence: "2026-08",
    status: "done",
    triggered_by: "sistema",
    started_at: null,
    finished_at: null,
    error: null,
  },
  skipped_messages: { count: 1, last_received_at: "2026-09-01T10:00:00", last_reason: "sem anexo" },
  checked_at: "2026-09-29T12:00:00+00:00",
};

afterEach(() => {
  vi.unstubAllGlobals();
  useAnalyticsStore.setState({
    summary: null,
    health: null,
    loading: false,
    healthLoading: false,
    error: "",
    healthError: "",
  });
});

describe("useAnalyticsStore.loadHealth", () => {
  it("guarda a saúde quando a resposta é ok", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => HEALTH }));

    await useAnalyticsStore.getState().loadHealth();

    expect(useAnalyticsStore.getState().health).toEqual(HEALTH);
    expect(useAnalyticsStore.getState().healthError).toBe("");
    expect(useAnalyticsStore.getState().healthLoading).toBe(false);
  });

  it("deixa mensagem amigável e preserva o dado antigo quando falha", async () => {
    useAnalyticsStore.setState({ health: HEALTH });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502, text: async () => "erro" }));

    await useAnalyticsStore.getState().loadHealth();

    expect(useAnalyticsStore.getState().healthError).toMatch(/Não consegui carregar a saúde/);
    expect(useAnalyticsStore.getState().health).toEqual(HEALTH);
    expect(useAnalyticsStore.getState().healthLoading).toBe(false);
  });
});
