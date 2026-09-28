import { useCallback, useState, type FocusEvent, type MouseEvent } from "react";
import { createPortal } from "react-dom";

type Tip = { label: string; top: number; left: number };

function tipTarget(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? (target.closest("[data-tip]") as HTMLElement | null) : null;
}

/** Tooltip da sidebar RECOLHIDA: aparece na hora (o `title` nativo tem o
 * atraso do navegador e o visual do sistema) e fica fora da sidebar num
 * portal — ela tem `overflow` escondido, que cortaria um tooltip desenhado
 * dentro dela. Um elemento só, por delegação: qualquer item com `data-tip`
 * mostra o texto no hover ou no foco pelo teclado. */
export function useSidebarTooltip(enabled: boolean) {
  const [tip, setTip] = useState<Tip | null>(null);

  const show = useCallback(
    (el: HTMLElement | null) => {
      const label = el?.dataset.tip;
      if (!enabled || !el || !label) return setTip(null);
      const rect = el.getBoundingClientRect();
      setTip({ label, top: rect.top + rect.height / 2, left: rect.right + 12 });
    },
    [enabled],
  );

  const handlers = {
    onMouseOver: (e: MouseEvent) => show(tipTarget(e.target)),
    onMouseLeave: () => setTip(null),
    onFocus: (e: FocusEvent) => show(tipTarget(e.target)),
    onBlur: () => setTip(null),
    // clicou: navegou/abriu — o tooltip não fica pendurado
    onClick: () => setTip(null),
  };

  const tooltip =
    enabled && tip
      ? createPortal(
          <div className="sidebar-tooltip" role="tooltip" style={{ top: tip.top, left: tip.left }}>
            {tip.label}
          </div>,
          document.body,
        )
      : null;

  return { handlers, tooltip };
}
