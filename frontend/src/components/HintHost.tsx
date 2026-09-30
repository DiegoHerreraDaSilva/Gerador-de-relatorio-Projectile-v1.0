import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Side = "bottom" | "top" | "right";
type Hint = { text: string; side: Side; top: number; left: number };

/** O texto do elemento (ou de algum filho) está cortado com reticências. */
function isClipped(el: HTMLElement): boolean {
  const cut = (n: HTMLElement) => n.scrollWidth > n.clientWidth + 1;
  return cut(el) || Array.from(el.querySelectorAll<HTMLElement>("*")).some(cut);
}

function hintTarget(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? (target.closest("[data-hint]") as HTMLElement | null) : null;
}

/** Tooltip INSTANTÂNEO de dropdowns e filtros, com o mesmo visual do tooltip da sidebar recolhida
 * (`.hint-tip` = `.sidebar-tooltip`): aparece na hora, sem o atraso nem o visual do `title` nativo.
 * Um elemento só, montado uma vez, por delegação: qualquer elemento com `data-hint="texto"` mostra
 * o texto no hover ou no foco pelo teclado. Fica num portal, então nenhum `overflow` corta.
 * `data-hint-side="right"` (itens de lista) põe ao lado e só aparece quando o texto está cortado;
 * o padrão é embaixo, virando pra cima quando não cabe. Some ao clicar, ao rolar e com Esc; não aparece enquanto a lista do próprio
 * controle está aberta (`aria-expanded="true"`). */
export function HintHost() {
  const [hint, setHint] = useState<Hint | null>(null);

  useEffect(() => {
    const hide = () => setHint(null);
    const show = (el: HTMLElement | null) => {
      const text = el?.dataset.hint?.trim();
      if (!el || !text || el.getAttribute("aria-expanded") === "true") return hide();
      const rect = el.getBoundingClientRect();
      if (el.dataset.hintSide === "right") {
        // item de lista: o texto já está visível, a menos que tenha sido cortado; e só cabe ao lado
        // (embaixo cobriria a própria lista e ficaria longe do item)
        if (!isClipped(el) || rect.right + 240 >= window.innerWidth) return hide();
        return setHint({ text, side: "right", top: rect.top + rect.height / 2, left: rect.right + 12 });
      }
      // embaixo/em cima: centrado no controle; o desvio pra não sair da janela é medido depois de
      // renderizar (o balão tem largura de verdade, não uma estimativa) e a setinha continua no controle
      const left = rect.left + rect.width / 2;
      if (rect.bottom + 70 > window.innerHeight && rect.top > 70) {
        return setHint({ text, side: "top", top: rect.top - 10, left });
      }
      setHint({ text, side: "bottom", top: rect.bottom + 10, left });
    };
    const onOver = (e: MouseEvent) => show(hintTarget(e.target));
    const onOut = (e: MouseEvent) => {
      // só esconde ao sair do elemento marcado (não a cada filho que o mouse atravessa)
      const from = hintTarget(e.target);
      if (from && !from.contains(e.relatedTarget as Node | null)) hide();
    };
    const onFocus = (e: FocusEvent) => show(hintTarget(e.target));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && hide();

    document.addEventListener("mouseover", onOver);
    document.addEventListener("mouseout", onOut);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("focusout", hide);
    document.addEventListener("click", hide, true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      document.removeEventListener("mouseover", onOver);
      document.removeEventListener("mouseout", onOut);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("click", hide, true);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, []);

  const tipRef = useRef<HTMLDivElement>(null);
  // antes de pintar: se o balão centrado passa da borda da janela, empurra de volta (--hint-shift)
  useLayoutEffect(() => {
    const node = tipRef.current;
    if (!node || !hint || hint.side === "right") return;
    node.style.setProperty("--hint-shift", "0px");
    const rect = node.getBoundingClientRect();
    const margin = 8;
    let shift = 0;
    if (rect.left < margin) shift = margin - rect.left;
    else if (rect.right > window.innerWidth - margin) shift = window.innerWidth - margin - rect.right;
    node.style.setProperty("--hint-shift", `${shift}px`);
  }, [hint]);

  if (!hint) return null;
  return createPortal(
    <div
      ref={tipRef}
      className={`hint-tip hint-${hint.side}`}
      role="tooltip"
      style={{ top: hint.top, left: hint.left }}
    >
      {hint.text}
    </div>,
    document.body,
  );
}
