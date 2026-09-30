import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchExecutiveSummary, paragraphs, sourceLabel } from "../executiveSummary";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      return { ok: status >= 200 && status < 300, status, json: async () => body };
    }),
  );
  return calls;
}

describe("sourceLabel", () => {
  it("diz se foi a IA (com números conferidos) ou o texto automático", () => {
    expect(sourceLabel("claude")).toContain("Claude");
    expect(sourceLabel("claude")).toContain("conferido");
    expect(sourceLabel("automatico")).toContain("automático");
  });
});

describe("paragraphs", () => {
  it("separa pelas linhas em branco e ignora vazios e espaços", () => {
    expect(paragraphs("Um.\n\nDois.\n\n\n  Três.  \n\n")).toEqual(["Um.", "Dois.", "Três."]);
  });

  it("texto sem separação é um parágrafo só; vazio não gera nada", () => {
    expect(paragraphs("Só um parágrafo\ncom quebra simples.")).toEqual(["Só um parágrafo\ncom quebra simples."]);
    expect(paragraphs("   ")).toEqual([]);
  });
});

describe("fetchExecutiveSummary", () => {
  it("pede o mês e se quer IA, e devolve o resumo", async () => {
    const summary = { month: "2026-08", text: "ok", source: "automatico", ai_note: null, facts: {} };
    const calls = stubFetch(200, summary);
    await expect(fetchExecutiveSummary("2026-08", false)).resolves.toEqual(summary);
    const params = new URLSearchParams(calls[0].split("?")[1]);
    expect(calls[0].startsWith("/management/executive-summary?")).toBe(true);
    expect(params.get("month")).toBe("2026-08");
    expect(params.get("use_ai")).toBe("false");
  });

  it("400 usa a mensagem do servidor (mês fora da janela)", async () => {
    stubFetch(400, { detail: "Mês fora da janela do Painel (últimos 12 meses)." });
    await expect(fetchExecutiveSummary("2024-01", true)).rejects.toThrow("Mês fora da janela");
  });

  it("401, 403 e erro do servidor viram mensagem pronta pra tela", async () => {
    stubFetch(401, {});
    await expect(fetchExecutiveSummary("2026-08", true)).rejects.toThrow("Sessão expirada");
    stubFetch(403, {});
    await expect(fetchExecutiveSummary("2026-08", true)).rejects.toThrow("Só o gerente");
    stubFetch(502, {});
    await expect(fetchExecutiveSummary("2026-08", true)).rejects.toThrow("Tenta de novo");
  });
});
