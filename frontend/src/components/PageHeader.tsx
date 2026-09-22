import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  icon,
  actions,
  status,
}: {
  title: string;
  description: string;
  icon?: ReactNode;
  actions?: ReactNode;
  status?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header-copy">
        {icon && <span className="page-header-icon" aria-hidden="true">{icon}</span>}
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
      {status && <div className="page-header-status" role="status" aria-live="polite">{status}</div>}
    </header>
  );
}
