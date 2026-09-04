import { useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";

/**
 * Ordenação clicável de tabela — `getValue` extrai o valor comparável de uma
 * linha pra uma coluna (`key`); `null` sempre vai pro fim, nas duas direções
 * (linha "sem dado" nunca deve competir com valor real). Compara número com
 * número e o resto como texto (pt-BR).
 */
export function useSortableRows<T>(rows: T[], getValue: (row: T, key: string) => string | number | null) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [direction, setDirection] = useState<SortDirection>("asc");

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const withValues = rows.map((row) => ({ row, value: getValue(row, sortKey) }));
    withValues.sort((a, b) => {
      if (a.value === null && b.value === null) return 0;
      if (a.value === null) return 1;
      if (b.value === null) return -1;
      const cmp =
        typeof a.value === "number" && typeof b.value === "number"
          ? a.value - b.value
          : String(a.value).localeCompare(String(b.value), "pt-BR");
      return direction === "asc" ? cmp : -cmp;
    });
    return withValues.map((w) => w.row);
  }, [rows, sortKey, direction, getValue]);

  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setDirection("asc");
    }
  };

  return { sortedRows, sortKey, direction, toggleSort };
}
