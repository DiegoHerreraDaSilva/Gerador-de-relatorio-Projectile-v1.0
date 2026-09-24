import { useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { useClickOutside } from "../hooks/useClickOutside";

function normalizeForSearch(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

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
  searchPlaceholder,
}: {
  label: string;
  options: string[];
  value: string;
  labelFor: (opt: string) => string;
  onChange: (value: string) => void;
  className?: string;
  /** Com isso, a lista ganha uma caixa de busca no topo (filtra por
   * `labelFor`, sem diferenciar maiúsculas nem acentos). */
  searchPlaceholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

  const close = () => {
    setOpen(false);
    setQuery("");
  };
  useClickOutside(wrapRef, close, open);

  const normalized = normalizeForSearch(query.trim());
  const visible = normalized
    ? options.filter((opt) => normalizeForSearch(labelFor(opt)).includes(normalized))
    : options;

  return (
    <div className={`mgmt-filter ${className ?? ""}`}>
      <span className="mgmt-filter-label">{label}</span>
      <div className="month-dropdown" ref={wrapRef}>
        <button type="button" className="month-dropdown-trigger" onClick={() => (open ? close() : setOpen(true))}>
          <span className="mgmt-filter-summary" title={labelFor(value)}>{labelFor(value)}</span>
          <ChevronDown size={15} strokeWidth={2} className={`month-dropdown-chevron ${open ? "open" : ""}`} />
        </button>
        {open && (
          <ul className="month-dropdown-list" role="listbox">
            {searchPlaceholder && (
              <li className="month-dropdown-search">
                <input
                  type="search"
                  autoFocus
                  value={query}
                  placeholder={searchPlaceholder}
                  aria-label={searchPlaceholder}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") close();
                    if (e.key === "Enter" && visible.length === 1) {
                      onChange(visible[0]);
                      close();
                    }
                  }}
                />
              </li>
            )}
            {visible.length === 0 && <li className="mgmt-filter-empty">Nenhum resultado</li>}
            {visible.map((opt) => (
              <li key={opt}>
                <button
                  type="button"
                  className={`month-dropdown-option ${opt === value ? "active" : ""}`}
                  onClick={() => {
                    onChange(opt);
                    close();
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
