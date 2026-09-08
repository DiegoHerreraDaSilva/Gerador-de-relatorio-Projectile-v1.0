import { RotateCcw } from "lucide-react";
import { ALL_COST_CENTERS, ROLLING_PERIOD, useManagementStore } from "../store/useManagementStore";
import { MultiSelectDropdown, SingleSelectDropdown } from "./FilterDropdown";

// ano mais antigo com apontamento real no Projectile (MIN(pDate) de
// ttimebit, checado direto no banco) — não é um número arbitrário.
const EARLIEST_DATA_YEAR = 2008;
const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = [
  ROLLING_PERIOD,
  ...Array.from({ length: CURRENT_YEAR - EARLIEST_DATA_YEAR + 1 }, (_, i) => String(CURRENT_YEAR - i)),
];

export function ManagementFilters({
  showCostCenter = true,
  showPackage = true,
}: { showCostCenter?: boolean; showPackage?: boolean } = {}) {
  const rows = useManagementStore((s) => s.rows);
  const period = useManagementStore((s) => s.period);
  const selectedMonths = useManagementStore((s) => s.selectedMonths);
  const costCenters = useManagementStore((s) => s.costCenters);
  const clients = useManagementStore((s) => s.clients);
  const projects = useManagementStore((s) => s.projects);
  const packages = useManagementStore((s) => s.packages);
  const availableClients = useManagementStore((s) => s.availableClients);
  const availableProjects = useManagementStore((s) => s.availableProjects);
  const availablePackages = useManagementStore((s) => s.availablePackages);
  const projectCodes = useManagementStore((s) => s.projectCodes);
  const projectClients = useManagementStore((s) => s.projectClients);
  const setPeriod = useManagementStore((s) => s.setPeriod);
  const setSelectedMonths = useManagementStore((s) => s.setSelectedMonths);
  const setCostCenters = useManagementStore((s) => s.setCostCenters);
  const setClients = useManagementStore((s) => s.setClients);
  const setProjects = useManagementStore((s) => s.setProjects);
  const setPackages = useManagementStore((s) => s.setPackages);
  const resetFilters = useManagementStore((s) => s.resetFilters);

  const monthOptions = (rows ?? []).map((r) => r.month);
  const projectLabel = (name: string) => (projectCodes[name] ? `${projectCodes[name]} - ${name}` : name);
  const projectsForSelectedClients =
    clients.length === 0 ? availableProjects : availableProjects.filter((name) => clients.includes(projectClients[name]));
  const projectOptions = [...projectsForSelectedClients].sort((a, b) => {
    const codeA = Number(projectCodes[a]);
    const codeB = Number(projectCodes[b]);
    if (!Number.isNaN(codeA) && !Number.isNaN(codeB) && codeA !== codeB) return codeA - codeB;
    if (!Number.isNaN(codeA) !== !Number.isNaN(codeB)) return Number.isNaN(codeA) ? 1 : -1;
    return a.localeCompare(b, "pt-BR");
  });
  const hasActiveFilters =
    period !== ROLLING_PERIOD ||
    selectedMonths.length > 0 ||
    costCenters.length !== ALL_COST_CENTERS.length ||
    clients.length > 0 ||
    projects.length > 0 ||
    packages.length > 0;

  return (
    <aside className="management-filters">
      <SingleSelectDropdown
        label="Período"
        options={YEAR_OPTIONS}
        value={period}
        labelFor={(opt) => (opt === ROLLING_PERIOD ? "Últimos 12 meses" : opt)}
        onChange={setPeriod}
        className="mgmt-filter-narrow"
      />
      <MultiSelectDropdown
        label="Competência"
        options={monthOptions}
        selected={selectedMonths}
        onChange={setSelectedMonths}
        className="mgmt-filter-narrow"
      />
      {showCostCenter && (
        <MultiSelectDropdown
          label="Centro de Custo"
          options={ALL_COST_CENTERS}
          selected={costCenters}
          onChange={(values) => setCostCenters(values.length === 0 ? ALL_COST_CENTERS : values)}
          className="mgmt-filter-narrow"
        />
      )}
      <MultiSelectDropdown
        label="Cliente"
        options={availableClients}
        selected={clients}
        onChange={setClients}
        className="mgmt-filter-wide"
      />
      <MultiSelectDropdown
        label="Projeto"
        options={projectOptions}
        selected={projects}
        onChange={setProjects}
        labelFor={projectLabel}
        className="mgmt-filter-wider"
      />
      {showPackage && (
        <MultiSelectDropdown
          label="Pacote de Trabalho"
          options={availablePackages}
          selected={packages}
          onChange={setPackages}
          className="mgmt-filter-wider"
        />
      )}
      <button
        type="button"
        className="mgmt-filter-reset"
        onClick={resetFilters}
        disabled={!hasActiveFilters}
        title="Voltar todos os filtros ao padrão"
      >
        <RotateCcw size={14} strokeWidth={2} />
        Resetar filtros
      </button>
    </aside>
  );
}
