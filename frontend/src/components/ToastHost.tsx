import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useToastStore, type Toast } from "../store/useToastStore";

const ICONS = { success: CheckCircle2, error: AlertCircle, info: Info } as const;

function ToastItem({ toast }: { toast: Toast }) {
  const dismiss = useToastStore((s) => s.dismiss);
  const [paused, setPaused] = useState(false);
  const remaining = useRef(toast.duration);
  const startedAt = useRef(0);

  // o tempo só corre com o aviso "solto": mouse em cima ou foco dentro pausa e retoma de onde parou
  useEffect(() => {
    if (paused) return;
    startedAt.current = Date.now();
    const timer = window.setTimeout(() => dismiss(toast.id), remaining.current);
    return () => {
      window.clearTimeout(timer);
      remaining.current = Math.max(800, remaining.current - (Date.now() - startedAt.current));
    };
  }, [paused, dismiss, toast.id]);

  const Icon = ICONS[toast.kind];
  return (
    <div
      className={`toast toast-${toast.kind}`}
      role={toast.kind === "error" ? "alert" : "status"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <Icon size={17} strokeWidth={2} className="toast-icon" aria-hidden="true" />
      <p className="toast-message">{toast.message}</p>
      {toast.actionLabel && toast.onAction && (
        <button
          type="button"
          className="toast-action"
          onClick={() => {
            toast.onAction?.();
            dismiss(toast.id);
          }}
        >
          {toast.actionLabel}
        </button>
      )}
      <button type="button" className="toast-close" aria-label="Fechar aviso" onClick={() => dismiss(toast.id)}>
        <X size={14} strokeWidth={2} aria-hidden="true" />
      </button>
    </div>
  );
}

/** Avisos do app (sucesso, erro, informação), empilhados no canto superior direito. Montado uma vez
 * em `main.tsx`; quem dispara usa `toast.success(...)` de `store/useToastStore`. */
export function ToastHost() {
  const toasts = useToastStore((s) => s.toasts);
  if (toasts.length === 0) return null;
  return createPortal(
    <div className="toast-host" role="region" aria-label="Avisos">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>,
    document.body,
  );
}
