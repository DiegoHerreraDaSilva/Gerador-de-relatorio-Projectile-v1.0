import type { ReactNode } from "react";

/** Card de uma etapa numerada (badge + título + descrição + conteúdo) —
 * usado pela sequência de etapas de "Gerar relatório" (3 no fluxo de
 * arquivo local, 4 no fluxo Projectile, ver FileUpload.tsx). Puramente
 * apresentacional, sem estado próprio. */
export function StepCard({
  number,
  title,
  description,
  children,
}: {
  number: number;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="step-card">
      <div className="step-card-head">
        <span className="step-card-badge" aria-hidden="true">
          {String(number).padStart(2, "0")}
        </span>
        <div>
          <h2 className="step-card-title">{title}</h2>
          <p className="step-card-desc">{description}</p>
        </div>
      </div>
      <div className="step-card-body">{children}</div>
    </div>
  );
}
