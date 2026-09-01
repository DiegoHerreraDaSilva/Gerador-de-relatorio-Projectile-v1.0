import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ALL_COST_CENTERS, ROLLING_PERIOD, useManagementStore } from "../store/useManagementStore";

function SingleSelectDropdown({
  label,
  options,
  value,
  labelFor,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  labelFor: (opt: string) => string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onOutside = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [open]);

  return (
    <div className="mgmt-filter">
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

function MultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onOutside = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [open]);

  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };

  const summary =
    selected.length === 0
      ? "Todos"
      : selected.length === 1
      ? selected[0]
      : `${selected.length} selecionados`;

  return (
    <div className="mgmt-filter">
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
                  <span title={opt}>{opt}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ano mais antigo com apontamento real no Projectile (MIN(pDate) de
// ttimebit, checado direto no banco) — não é um número arbitrário.
const EARLIEST_DATA_YEAR = 2008;
const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [
  ROLLING_PERIOD,
  ...Array.from({ length: CURRENT_YEAR - EARLIEST_DATA_YEAR + 1 }, (_, i) => String(CURRENT_YEAR - i)),
];

export function ManagementFilters() {
  const rows = useManagementStore((s) => s.rows);
  const period = useManagementStore((s) => s.period);
  const selectedMonths = useManagementStore((s) => s.selectedMonths);
  const costCenters = useManagementStore((s) => s.costCenters);
  const clients = useManagementStore((s) => s.clients);
  const projects = useManagementStore((s) => s.projects);
  const availableClients = useManagementStore((s) => s.availableClients);
  const availableProjects = useManagementStore((s) => s.availableProjects);
  const setPeriod = useManagementStore((s) => s.setPeriod);
  const setSelectedMonths = useManagementStore((s) => s.setSelectedMonths);
  const setCostCenters = useManagementStore((s) => s.setCostCenters);
  const setClients = useManagementStore((s) => s.setClients);
  const setProjects = useManagementStore((s) => s.setProjects);

  const monthOptions = (rows ?? []).map((r) => r.month);

  return (
    <aside className="management-filters">
      <SingleSelectDropdown
        label="Período"
        options={YEAR_OPTIONS}
        value={period}
        labelFor={(opt) => (opt === ROLLING_PERIOD ? "Últimos 12 meses" : opt)}
        onChange={setPeriod}
      />
      <MultiSelectDropdown label="Competência" options={monthOptions} selected={selectedMonths} onChange={setSelectedMonths} />
      <MultiSelectDropdown
        label="Centro de Custo"
        options={ALL_COST_CENTERS}
        selected={costCenters}
        onChange={(values) => setCostCenters(values.length === 0 ? ALL_COST_CENTERS : values)}
      />
      <MultiSelectDropdown label="Cliente" options={availableClients} selected={clients} onChange={setClients} />
      <MultiSelectDropdown label="Projeto" options={availableProjects} selected={projects} onChange={setProjects} />
    </aside>
  );
}
