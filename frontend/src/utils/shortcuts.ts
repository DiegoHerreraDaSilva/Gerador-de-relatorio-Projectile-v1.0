import type { AppView } from "../appView";

export type ShortcutAction = "palette" | "undo";

export type ShortcutInput = {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  /** O foco está num campo onde a tecla é texto (input, textarea, select, contentEditable). */
  targetEditable: boolean;
  /** Há um modal aberto por cima da tela. */
  modalOpen: boolean;
  view: AppView;
};

/** O elemento aceita digitação (então "/" e Ctrl+Z são dele, não do app). */
export function isEditableTarget(el: { tagName?: string; isContentEditable?: boolean } | null): boolean {
  if (!el) return false;
  const tag = (el.tagName ?? "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(el.isContentEditable);
}

/** Qual atalho global (se algum) esta tecla dispara. Função pura, pra testar sem navegador.
 *  - Ctrl/⌘+K: paleta de comandos, em qualquer lugar (inclusive digitando; é o padrão dos apps com paleta);
 *  - "/": também abre a paleta, mas só fora de campos de texto e sem modal por cima;
 *  - Ctrl/⌘+Z: desfazer a última edição do relatório, só na tela do relatório, fora de campos de texto
 *    (dentro deles o desfazer é do próprio campo) e sem modal. */
export function resolveShortcut(input: ShortcutInput): ShortcutAction | null {
  const mod = input.ctrlKey || input.metaKey;
  const key = input.key.toLowerCase();
  if (mod && !input.shiftKey && !input.altKey && key === "k") return "palette";
  if (!mod && !input.altKey && input.key === "/" && !input.targetEditable && !input.modalOpen) return "palette";
  if (mod && !input.shiftKey && !input.altKey && key === "z" && input.view === "report") {
    return input.targetEditable || input.modalOpen ? null : "undo";
  }
  return null;
}
