import type { MyHoursPeriod } from "../../store/useMyHoursStore";

const OPTIONS: { value: MyHoursPeriod; label: string; full: string }[] = [
  { value: "current_month", label: "Mês", full: "Mês atual" },
  { value: "last_3", label: "3m", full: "Últimos 3 meses" },
  { value: "last_6", label: "6m", full: "Últimos 6 meses" },
  { value: "last_12", label: "12m", full: "Últimos 12 meses" },
];

/** Segmented control em vez de `<select>`: são 4 opções fixas e mutuamente
 * exclusivas, e o recorte é o controle mais usado da tela — esconder as
 * opções atrás de um dropdown custa um clique a mais em todas elas e não
 * mostra onde você está no espectro de tempo. */
export function PeriodSegmented({
  value,
  disabled,
  onChange,
}: {
  value: MyHoursPeriod;
  disabled: boolean;
  onChange: (period: MyHoursPeriod) => void;
}) {
  return (
    <div className="period-seg" role="group" aria-label="Período">
      {OPTIONS.map((opt) => (
        <button
          type="button"
          key={opt.value}
          className={value === opt.value ? "active" : ""}
          aria-pressed={value === opt.value}
          aria-label={opt.full}
          title={opt.full}
          disabled={disabled}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
