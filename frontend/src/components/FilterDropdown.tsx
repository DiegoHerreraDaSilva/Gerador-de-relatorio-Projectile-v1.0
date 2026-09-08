import { useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useClickOutside } from "../hooks/useClickOutside";

/** Dropdowns de filtro compartilhados entre o Painel de Gerência e o
 * Dashboard de horas — extraídos de `ManagementFilters.tsx` pra não duplicar
 * a mesma UI (mesma classe CSS `.mgmt-filter`/`.month-dropdown`) em dois
 * lugares. Qualquer tela nova que precise de filtro em dropdown usa isto. */
export function SingleSelectDropdown({
  label,
  options,
  value,
  labelFor,
  onChange,
  className,
}: {
  label: string;
  options: string[];
  value: string;
  labelFor: (opt: string) => string;
  onChange: (value: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useClickOutside(wrapRef, () => setOpen(false), open);

  return (
    <div className={`mgmt-filter ${className ?? ""}`}>
      <span className="mgmt-filter-label">{label}</span>
      <div className="month-dropdown" ref={wrapRef}>
        <button type="button" className="month-dropdown-trigger" onClick={() => setOpen((v) => !v)}>
          <span className="mgmt-filter-summary">{labelFor(value)}</span>
          <ChevronDown size={15} strokeWidth={2} className={`month-dropdown-chevron ${open ? "open" : ""}`} />
        </button>
        {open && (
          <ul className="month-dropdown-list" role="listbox">
            {options.map((opt) => (
              <li key={opt}>
                <button
                  type="button"
                  className={`month-dropdown-option ${opt === value ? "active" : ""}`}
                  onClick={() => {
                    onChange(opt);
                    setOpen(false);
                  }}
                >
                  {labelFor(opt)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function MultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
  labelFor = (opt) => opt,
  className,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
  labelFor?: (opt: string) => string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useClickOutside(wrapRef, () => setOpen(false), open);

  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };

  const summary =
    selected.length === 0
      ? "Todos"
      : selected.length === 1
      ? labelFor(selected[0])
      : `${selected.length} selecionados`;

  return (
    <div className={`mgmt-filter ${className ?? ""}`}>
      <span className="mgmt-filter-label">{label}</span>
      <div className="month-dropdown" ref={wrapRef}>
        <button type="button" className="month-dropdown-trigger" onClick={() => setOpen((v) => !v)}>
          <span className="mgmt-filter-summary" title={summary}>{summary}</span>
          <ChevronDown size={15} strokeWidth={2} className={`month-dropdown-chevron ${open ? "open" : ""}`} />
        </button>
        {open && (
          <ul className="month-dropdown-list" role="listbox">
            {options.length === 0 && <li className="mgmt-filter-empty">Nenhuma opção</li>}
            {options.map((opt) => (
              <li key={opt}>
                <label className="mgmt-filter-option">
                  <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} />
                  <span title={labelFor(opt)}>{labelFor(opt)}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
