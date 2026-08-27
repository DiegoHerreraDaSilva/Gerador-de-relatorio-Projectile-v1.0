import { useReportStore } from "../store/useReportStore";

export function ModeSelect() {
  const reportMode = useReportStore((s) => s.reportMode);
  const setReportMode = useReportStore((s) => s.setReportMode);
  const hasPackages = useReportStore((s) => s.packages.length > 0);

  return (
    <div className="mode-select">
      <button
        type="button"
        className={`mode-option ${reportMode === "single" ? "active" : ""}`}
        onClick={() => {
          if (reportMode !== "single") setReportMode("single");
        }}
      >
        <span className="mode-title">Relatório único</span>
        <span className="mode-desc">Todas as linhas viram um único relatório final.</span>
      </button>
      <button
        type="button"
        className={`mode-option ${reportMode === "multi" ? "active" : ""}`}
        onClick={() => {
          if (reportMode !== "multi") setReportMode("multi");
        }}
      >
        <span className="mode-title">Múltiplos relatórios</span>
        <span className="mode-desc">Um relatório separado por Pacote de Trabalho.</span>
      </button>
      {hasPackages && <span className="muted" style={{ display: "none" }} />}
    </div>
  );
}
