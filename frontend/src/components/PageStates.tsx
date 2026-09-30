import type { ReactNode } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

/** Estados de tela padronizados: vazio (com a próxima ação), erro (com "Tentar de novo") e
 * carregando (com a geometria de linhas, pra tela não saltar quando o dado chega). Toda tela nova usa
 * estes três em vez de um `<p className="muted">` improvisado. */

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="state-view state-empty">
      {icon && (
        <span className="state-icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <p className="state-title">{title}</p>
      {description && <p className="state-description">{description}</p>}
      {action && (
        <button type="button" className="btn-secondary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}

export function ErrorState({ message, onRetry, busy }: { message: string; onRetry?: () => void; busy?: boolean }) {
  return (
    <div className="state-view state-error" role="alert">
      <span className="state-icon" aria-hidden="true">
        <AlertCircle size={22} strokeWidth={1.8} />
      </span>
      <p className="state-title">{message}</p>
      {onRetry && (
        <button type="button" className="btn-secondary" onClick={onRetry} disabled={busy}>
          <RefreshCw size={14} strokeWidth={2} className={busy ? "spin" : ""} /> Tentar de novo
        </button>
      )}
    </div>
  );
}

export function LoadingState({ label = "Carregando...", rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="state-view state-loading" aria-busy="true">
      <span className="sr-only" role="status">
        {label}
      </span>
      <div aria-hidden="true">
        <div className="skel skel-title" />
        {Array.from({ length: rows }, (_, i) => (
          <div className="skel skel-line" key={i} />
        ))}
      </div>
    </div>
  );
}
