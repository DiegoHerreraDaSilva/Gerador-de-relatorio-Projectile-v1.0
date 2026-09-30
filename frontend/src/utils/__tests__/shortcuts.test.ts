import { describe, expect, it } from "vitest";
import { isEditableTarget, resolveShortcut, type ShortcutInput } from "../shortcuts";

const press = (patch: Partial<ShortcutInput>): ShortcutInput => ({
  key: "",
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  altKey: false,
  targetEditable: false,
  modalOpen: false,
  view: "report",
  ...patch,
});

describe("atalhos globais", () => {
  it("Ctrl+K e ⌘+K abrem a paleta, inclusive com o foco num campo (é o padrão dos apps com paleta)", () => {
    expect(resolveShortcut(press({ key: "k", ctrlKey: true }))).toBe("palette");
    expect(resolveShortcut(press({ key: "K", metaKey: true }))).toBe("palette");
    expect(resolveShortcut(press({ key: "k", ctrlKey: true, targetEditable: true }))).toBe("palette");
  });

  it("'k' sozinho, ou com Shift/Alt, não faz nada", () => {
    expect(resolveShortcut(press({ key: "k" }))).toBeNull();
    expect(resolveShortcut(press({ key: "k", ctrlKey: true, shiftKey: true }))).toBeNull();
    expect(resolveShortcut(press({ key: "k", ctrlKey: true, altKey: true }))).toBeNull();
  });

  it("'/' abre a paleta só fora de campo de texto e sem modal por cima", () => {
    expect(resolveShortcut(press({ key: "/" }))).toBe("palette");
    expect(resolveShortcut(press({ key: "/", targetEditable: true }))).toBeNull();
    expect(resolveShortcut(press({ key: "/", modalOpen: true }))).toBeNull();
    expect(resolveShortcut(press({ key: "/", ctrlKey: true }))).toBeNull();
  });

  it("Ctrl+Z desfaz só na tela do relatório, fora de campo de texto e sem modal", () => {
    expect(resolveShortcut(press({ key: "z", ctrlKey: true }))).toBe("undo");
    expect(resolveShortcut(press({ key: "Z", metaKey: true }))).toBe("undo");
    expect(resolveShortcut(press({ key: "z", ctrlKey: true, targetEditable: true }))).toBeNull();
    expect(resolveShortcut(press({ key: "z", ctrlKey: true, modalOpen: true }))).toBeNull();
    expect(resolveShortcut(press({ key: "z", ctrlKey: true, view: "history" }))).toBeNull();
  });

  it("Ctrl+Shift+Z (refazer) não é tratado", () => {
    expect(resolveShortcut(press({ key: "z", ctrlKey: true, shiftKey: true }))).toBeNull();
  });

  it("outras teclas não disparam nada", () => {
    expect(resolveShortcut(press({ key: "a", ctrlKey: true }))).toBeNull();
    expect(resolveShortcut(press({ key: "Enter" }))).toBeNull();
  });
});

describe("isEditableTarget", () => {
  it("campos de texto, caixa de seleção e contentEditable aceitam digitação", () => {
    expect(isEditableTarget({ tagName: "INPUT" })).toBe(true);
    expect(isEditableTarget({ tagName: "textarea" })).toBe(true);
    expect(isEditableTarget({ tagName: "SELECT" })).toBe(true);
    expect(isEditableTarget({ tagName: "DIV", isContentEditable: true })).toBe(true);
  });

  it("botão, div comum e ausência de alvo não", () => {
    expect(isEditableTarget({ tagName: "BUTTON" })).toBe(false);
    expect(isEditableTarget({ tagName: "DIV" })).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });
});
