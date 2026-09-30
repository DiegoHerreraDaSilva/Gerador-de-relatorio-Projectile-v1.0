import { useEffect, useRef, type RefObject } from "react";

/** Pilha dos modais abertos: só o de cima trata Esc e Tab. Sem isso, uma confirmação aberta por cima de
 * um modal fechava os dois com um Esc só, e o Tab vazava pra página de trás. */
const stack: number[] = [];
let nextId = 1;

export const modalStack = {
  push(): number {
    const id = nextId++;
    stack.push(id);
    return id;
  },
  remove(id: number): void {
    const index = stack.indexOf(id);
    if (index >= 0) stack.splice(index, 1);
  },
  isTop(id: number): boolean {
    return stack.length > 0 && stack[stack.length - 1] === id;
  },
  size(): number {
    return stack.length;
  },
};

/** Próximo índice de foco dentro do modal (Tab prende o foco nele). `current` é a posição do elemento
 * focado na lista de focáveis (-1 = fora dela); devolve -1 se não há nada focável. */
export function wrapFocusIndex(current: number, count: number, backwards: boolean): number {
  if (count === 0) return -1;
  if (current < 0) return backwards ? count - 1 : 0;
  if (backwards) return current === 0 ? count - 1 : current - 1;
  return current === count - 1 ? 0 : current + 1;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null || el === document.activeElement,
  );
}

/** Onde o foco começa: o primeiro campo/botão do conteúdo (não o "X" de fechar, que só atrapalharia). */
function initialTarget(root: HTMLElement): HTMLElement {
  const list = focusables(root);
  return list.find((el) => !el.classList.contains("modal-close")) ?? list[0] ?? root;
}

/** Comportamento de teclado e foco de qualquer modal, num lugar só:
 *  - Esc fecha (menos quando `busy`, ex.: enviando, ou quando um controle de dentro já tratou o Esc);
 *  - Tab e Shift+Tab ficam presos dentro do modal;
 *  - o foco entra no primeiro campo e VOLTA pro elemento que abriu o modal quando ele fecha;
 *  - só o modal de cima da pilha reage.
 * Use: `const ref = useModal({ onClose, busy }); <div ref={ref} tabIndex={-1} role="dialog" ...>`. */
export function useModal({
  onClose,
  busy = false,
  enabled = true,
  initialFocus,
}: {
  onClose: () => void;
  busy?: boolean;
  enabled?: boolean;
  initialFocus?: RefObject<HTMLElement>;
}): RefObject<HTMLDivElement> {
  const containerRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const busyRef = useRef(busy);
  onCloseRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    if (!enabled) return;
    const id = modalStack.push();
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const container = containerRef.current;
    if (container) (initialFocus?.current ?? initialTarget(container)).focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (!modalStack.isTop(id)) return;
      if (e.key === "Escape") {
        // um Select/dropdown de dentro já usou este Esc (preventDefault) pra fechar a própria lista
        if (e.defaultPrevented || busyRef.current) return;
        e.preventDefault();
        onCloseRef.current();
      } else if (e.key === "Tab" && container) {
        const list = focusables(container);
        if (list.length === 0) {
          e.preventDefault();
          container.focus();
          return;
        }
        const index = list.indexOf(document.activeElement as HTMLElement);
        const atEdge = e.shiftKey ? index <= 0 : index === list.length - 1;
        if (index === -1 || atEdge) {
          e.preventDefault();
          list[wrapFocusIndex(index, list.length, e.shiftKey)].focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      modalStack.remove(id);
      if (previous && document.contains(previous)) previous.focus();
    };
  }, [enabled, initialFocus]);

  return containerRef;
}
