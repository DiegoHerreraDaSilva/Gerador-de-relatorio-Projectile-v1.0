import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle } from "lucide-react";

export type ConfirmOptions = {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Ação destrutiva: botão vermelho e o foco começa em "Cancelar". */
  danger?: boolean;
};

type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

let show: ((pending: Pending) => void) | null = null;

/** Confirmação no estilo do app, no lugar do `window.confirm` (que abre a
 * caixa do navegador, com o endereço do servidor no título). Devolve uma
 * promessa: `if (!(await confirmDialog({...}))) return;`. Precisa do
 * `<ConfirmHost />` montado uma vez (main.tsx); sem ele, cai no
 * `window.confirm` pra nunca perder a pergunta. */
export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  if (!show) return Promise.resolve(window.confirm(`${options.title}\n\n${options.message}`));
  return new Promise((resolve) => show!({ ...options, resolve }));
}

export function ConfirmHost() {
  const [queue, setQueue] = useState<Pending[]>([]);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const okRef = useRef<HTMLButtonElement>(null);
  const current = queue[0];

  useEffect(() => {
    show = (pending) => setQueue((q) => [...q, pending]);
    return () => {
      show = null;
    };
  }, []);

  const answer = (ok: boolean) => {
    if (!current) return;
    current.resolve(ok);
    setQueue((q) => q.slice(1));
  };

  useEffect(() => {
    if (!current) return;
    (current.danger ? cancelRef : okRef).current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        answer(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current]);

  if (!current) return null;
  return createPortal(
    <div className="modal-backdrop confirm-backdrop" onClick={() => answer(false)}>
      <div
        className="modal-card confirm-card"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="confirm-head">
          {current.danger && (
            <span className="confirm-icon" aria-hidden="true">
              <AlertTriangle size={18} strokeWidth={2} />
            </span>
          )}
          <h2 id="confirm-title">{current.title}</h2>
        </div>
        <p id="confirm-message" className="confirm-message">
          {current.message}
        </p>
        <div className="modal-actions">
          <button ref={cancelRef} type="button" className="btn-secondary" onClick={() => answer(false)}>
            {current.cancelLabel ?? "Cancelar"}
          </button>
          <button
            ref={okRef}
            type="button"
            className={current.danger ? "primary confirm-danger" : "primary"}
            onClick={() => answer(true)}
          >
            {current.confirmLabel ?? "Confirmar"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
