import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import type { SortDirection } from "../hooks/useSortableRows";

/** Cabeçalho de coluna ordenável.
 *
 * O clique fica num `<button>` de verdade, não num `onClick` no `<th>`: um
 * `<th>` clicável não recebe foco nem responde a Enter/Espaço, o que torna a
 * ordenação inalcançável por teclado (WCAG 2.1.1). O botão nativo resolve
 * foco, teclado e semântica de uma vez — `aria-sort` continua no `<th>`,
 * que é onde a especificação o espera. */
export function SortableTh({
  children,
  sortKey,
  activeKey,
  direction,
  onSort,
}: {
  children: React.ReactNode;
  sortKey: string;
  activeKey: string | null;
  direction: SortDirection;
  onSort: (key: string) => void;
}) {
  const active = activeKey === sortKey;
  return (
    <th
      scope="col"
      className="sortable-th"
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
    >
      <button type="button" className="sortable-th-btn" onClick={() => onSort(sortKey)}>
        {children}
        {active ? (
          direction === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />
        ) : (
          <ChevronsUpDown size={12} className="sortable-th-icon-idle" />
        )}
      </button>
    </th>
  );
}
