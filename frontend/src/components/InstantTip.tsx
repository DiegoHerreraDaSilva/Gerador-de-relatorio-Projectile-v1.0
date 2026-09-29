import { useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Tooltip que aparece NA HORA (o `title` nativo demora e tem o visual do
 * sistema), no hover ou no foco pelo teclado. Fica num portal, fora de
 * qualquer contêiner com `overflow` (modal, sidebar), com o mesmo visual do
 * tooltip da sidebar (`.sidebar-tooltip`). */
export function InstantTip({ text, children, className }: { text: string; children: ReactNode; className?: string }) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const show = (el: HTMLElement) => {
    const rect = el.getBoundingClientRect();
    setPos({ top: rect.bottom + 8, left: Math.max(8, Math.min(rect.left, window.innerWidth - 300)) });
  };
  return (
    <>
      <span
        className={className}
        tabIndex={0}
        onMouseEnter={(e) => show(e.currentTarget)}
        onMouseLeave={() => setPos(null)}
        onFocus={(e) => show(e.currentTarget)}
        onBlur={() => setPos(null)}
        aria-label={text}
      >
        {children}
      </span>
      {pos && createPortal(<div className="instant-tip" role="tooltip" style={pos}>{text}</div>, document.body)}
    </>
  );
}
