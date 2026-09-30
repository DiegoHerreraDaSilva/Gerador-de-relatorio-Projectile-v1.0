import { beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_TOASTS, toast, useToastStore } from "../useToastStore";

const list = () => useToastStore.getState().toasts;

beforeEach(() => useToastStore.getState().clear());

describe("useToastStore", () => {
  it("cada tipo tem a duração certa: erro fica mais tempo que sucesso", () => {
    toast.success("ok");
    toast.info("fyi");
    toast.error("falhou");
    expect(list().map((t) => [t.kind, t.duration])).toEqual([
      ["success", 4000],
      ["info", 5000],
      ["error", 8000],
    ]);
  });

  it("o mesmo aviso já na tela não empilha, mas outro tipo com o mesmo texto entra", () => {
    const first = toast.error("Não consegui salvar");
    const again = toast.error("Não consegui salvar");
    expect(again).toBe(first);
    expect(list()).toHaveLength(1);
    toast.success("Não consegui salvar");
    expect(list()).toHaveLength(2);
  });

  it("no máximo MAX_TOASTS ao mesmo tempo: sai o mais antigo", () => {
    for (let i = 0; i < MAX_TOASTS + 2; i++) toast.info(`aviso ${i}`);
    expect(list()).toHaveLength(MAX_TOASTS);
    expect(list()[0].message).toBe("aviso 2");
    expect(list()[MAX_TOASTS - 1].message).toBe(`aviso ${MAX_TOASTS + 1}`);
  });

  it("aviso com ação dura pelo menos 8 s, pra dar tempo de clicar", () => {
    const onAction = vi.fn();
    toast.success("Relatório apagado", { actionLabel: "Desfazer", onAction });
    const [item] = list();
    expect(item.duration).toBe(8000);
    expect(item.actionLabel).toBe("Desfazer");
    item.onAction?.();
    expect(onAction).toHaveBeenCalledOnce();
    toast.success("rápido", { duration: 1000 });
    expect(list()[1].duration).toBe(1000);
  });

  it("dismiss tira só o aviso pedido e clear limpa tudo", () => {
    const a = toast.info("a");
    toast.info("b");
    useToastStore.getState().dismiss(a);
    expect(list().map((t) => t.message)).toEqual(["b"]);
    useToastStore.getState().clear();
    expect(list()).toEqual([]);
  });
});
