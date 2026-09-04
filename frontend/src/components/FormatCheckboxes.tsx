import { FileSpreadsheet, FileBadge2 } from "lucide-react";

export type ReportFormat = "xlsx" | "pdf";

export function FormatCheckboxes({
  value,
  onChange,
  disabled = false,
}: {
  value: Set<ReportFormat>;
  onChange: (next: Set<ReportFormat>) => void;
  disabled?: boolean;
}) {
  const toggle = (fmt: ReportFormat) => {
    if (value.has(fmt) && value.size === 1) return; // sempre pelo menos 1 formato marcado
    const next = new Set(value);
    if (next.has(fmt)) next.delete(fmt);
    else next.add(fmt);
    onChange(next);
  };

  return (
    <div className="format-checkboxes">
      <button
        type="button"
        className={`format-checkbox excel ${value.has("xlsx") ? "checked" : ""}`}
        onClick={() => toggle("xlsx")}
        disabled={disabled}
        aria-pressed={value.has("xlsx")}
        title="Excel (.xlsx)"
      >
        <FileSpreadsheet size={20} strokeWidth={2} />
        <span>Excel</span>
      </button>
      <button
        type="button"
        className={`format-checkbox pdf ${value.has("pdf") ? "checked" : ""}`}
        onClick={() => toggle("pdf")}
        disabled={disabled}
        aria-pressed={value.has("pdf")}
        title="PDF"
      >
        <FileBadge2 size={20} strokeWidth={2} />
        <span>PDF</span>
      </button>
    </div>
  );
}
