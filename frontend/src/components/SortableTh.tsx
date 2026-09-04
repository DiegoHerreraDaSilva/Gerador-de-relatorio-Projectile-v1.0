import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import type { SortDirection } from "../hooks/useSortableRows";

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
      className="sortable-th"
      onClick={() => onSort(sortKey)}
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
    >
      <span className="sortable-th-inner">
        {children}
        {active ? (
          direction === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />
        ) : (
          <ChevronsUpDown size={12} className="sortable-th-icon-idle" />
        )}
      </span>
    </th>
  );
}
