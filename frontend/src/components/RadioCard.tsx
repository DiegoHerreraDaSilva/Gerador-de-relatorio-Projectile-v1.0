import type { ReactNode } from "react";

/** Uma opção dentro de um `<RadioCardGroup>` — ícone + título + descrição +
 * indicador de seleção (radio real, não só cor). */
export type RadioCardOption = {
  value: string;
  icon: ReactNode;
  title: string;
  description?: string;
};

/** Grupo de radio cards de verdade (`<input type="radio">` associado a um
 * `<label>`) — usado nas decisões "de tudo ou nada" da tela de Gerar
 * relatório (De onde vêm os dados / Quais dados deseja buscar). Diferente
 * de `.source-switch` (pill deslizante, só comunica seleção por cor): aqui
 * cada opção tem indicador de seleção próprio, funciona com teclado (setas
 * navegam o grupo nativamente) e não depende só de cor pra comunicar o
 * estado (seção 10 do pedido de reforma). */
export function RadioCardGroup({
  name,
  value,
  onChange,
  options,
  ariaLabel,
  layout = "vertical",
  density = "default",
}: {
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: RadioCardOption[];
  /** Nome acessível do grupo (WAI-ARIA exige um pro role="radiogroup") —
   * normalmente o mesmo título já visível no StepCard em volta. */
  ariaLabel: string;
  layout?: "vertical" | "horizontal";
  density?: "default" | "compact";
}) {
  return (
    <div
      className={`radio-card-grid radio-card-grid-${layout} radio-card-grid-${density}`}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {options.map((opt) => (
        <label key={opt.value} className={`radio-card ${value === opt.value ? "active" : ""}`}>
          <input
            type="radio"
            name={name}
            value={opt.value}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="radio-card-input"
          />
          <span className="radio-card-icon" aria-hidden="true">
            {opt.icon}
          </span>
          <span className="radio-card-text">
            <span className="radio-card-title">{opt.title}</span>
            {opt.description && <span className="radio-card-desc">{opt.description}</span>}
          </span>
          <span className="radio-card-indicator" aria-hidden="true" />
        </label>
      ))}
    </div>
  );
}
