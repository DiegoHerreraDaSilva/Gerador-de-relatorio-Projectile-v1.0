import { afterEach, describe, expect, it } from "vitest";
import { modalStack, wrapFocusIndex } from "../useModal";

describe("pilha de modais: só o de cima reage ao Esc e ao Tab", () => {
  const opened: number[] = [];
  afterEach(() => {
    opened.splice(0).forEach((id) => modalStack.remove(id));
  });
  const open = () => {
    const id = modalStack.push();
    opened.push(id);
    return id;
  };

  it("um modal sozinho é o de cima", () => {
    const a = open();
    expect(modalStack.isTop(a)).toBe(true);
  });

  it("uma confirmação por cima de um modal: só ela é a de cima (um Esc não fecha os dois)", () => {
    const modal = open();
    const confirm = open();
    expect(modalStack.isTop(confirm)).toBe(true);
    expect(modalStack.isTop(modal)).toBe(false);
  });

  it("ao fechar o de cima, o de baixo volta a reagir", () => {
    const modal = open();
    const confirm = open();
    modalStack.remove(confirm);
    expect(modalStack.isTop(modal)).toBe(true);
  });

  it("sem nenhum aberto, ninguém é o de cima; remover duas vezes não quebra", () => {
    const a = open();
    modalStack.remove(a);
    modalStack.remove(a);
    expect(modalStack.size()).toBe(0);
    expect(modalStack.isTop(a)).toBe(false);
  });
});

describe("wrapFocusIndex: o Tab fica preso dentro do modal", () => {
  it("do último volta ao primeiro, e Shift+Tab do primeiro vai ao último", () => {
    expect(wrapFocusIndex(2, 3, false)).toBe(0);
    expect(wrapFocusIndex(0, 3, true)).toBe(2);
  });

  it("no meio, anda um passo nos dois sentidos", () => {
    expect(wrapFocusIndex(1, 3, false)).toBe(2);
    expect(wrapFocusIndex(1, 3, true)).toBe(0);
  });

  it("foco fora do modal (-1) entra pelo primeiro, ou pelo último com Shift", () => {
    expect(wrapFocusIndex(-1, 4, false)).toBe(0);
    expect(wrapFocusIndex(-1, 4, true)).toBe(3);
  });

  it("sem nada focável devolve -1", () => {
    expect(wrapFocusIndex(0, 0, false)).toBe(-1);
  });

  it("com um único focável, Tab e Shift+Tab ficam nele", () => {
    expect(wrapFocusIndex(0, 1, false)).toBe(0);
    expect(wrapFocusIndex(0, 1, true)).toBe(0);
  });
});
