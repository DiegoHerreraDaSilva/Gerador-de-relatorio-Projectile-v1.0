import { RotateCcw } from "lucide-react";
import { MultiSelectDropdown } from "../FilterDropdown";
import {
  filterOptions,
  hasActiveMyHoursFilters,
  MY_HOURS_FILTER_LABEL,
  type MyHoursEntry,
  type MyHoursFilters as Filters,
} from "../../utils/myHours";

const DIMENSIONS: { dim: keyof Filters; label: string }[] = [
  { dim: "months", label: "Competência" },
  { dim: "clients", label: "Cliente" },
  { dim: "projects", label: "Projeto" },
  { dim: "pacotes", label: "Pacote de Trabalho" },
];

/** Filtros do Dashboard de horas — mesmo componente de dropdown e o mesmo
 * conceito de "Competência" do Painel de Gerência (`ManagementFilters.tsx`),
 * cruzando entre si: selecionar um Cliente já estreita as opções de Projeto
 * e Pacote (e vice-versa), porque cada dropdown calcula suas opções sobre os
 * lançamentos filtrados pelos OUTROS dropdows (`filterOptions`, que ignora a
 * própria dimensão — ver `utils/myHours.ts`).
 *
 * Só aparecem opções que o usuário logado realmente apontou: `entries` já
 * chega do backend restrito a ele (`/my-hours` nunca expõe dado de outro
 * funcionário), então não existe universo maior a filtrar aqui. */
export function MyHoursFilters({
  entries,
  filters,
  onChange,
  onReset,
}: {
  entries: MyHoursEntry[];
  filters: Filters;
  onChange: (dim: keyof Filters, values: string[]) => void;
  onReset: () => void;
}) {
  const active = hasActiveMyHoursFilters(filters);

  return (
    <div className="myh-filters">
      {DIMENSIONS.map(({ dim, label }) => (
        <MultiSelectDropdown
          key={dim}
          label={label}
          options={filterOptions(entries, filters, dim)}
          selected={filters[dim]}
          onChange={(values) => onChange(dim, values)}
          labelFor={MY_HOURS_FILTER_LABEL[dim]}
          className="mgmt-filter-narrow"
        />
      ))}
      <button
        type="button"
        className="mgmt-filter-reset"
        onClick={onReset}
        disabled={!active}
        title="Voltar todos os filtros ao padrão"
      >
        <RotateCcw size={14} strokeWidth={2} />
        Resetar filtros
      </button>
    </div>
  );
}
