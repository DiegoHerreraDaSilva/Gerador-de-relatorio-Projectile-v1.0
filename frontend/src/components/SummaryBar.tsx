import { useReportStore } from "../store/useReportStore";
import { computeGrandTotalFor } from "../utils/calc";
import { fmtNum } from "../utils/fmt";

export function SummaryBar() {
  const packages = useReportStore((s) => s.packages);
  const activeId = useReportStore((s) => s.activePackageId);
  const pkg = packages.find((p) => p.id === activeId) ?? null;

  if (!pkg) return null;

  const total = computeGrandTotalFor(pkg.groups);
  const groupsCount = pkg.groups.length;
  const activitiesCount = pkg.groups.reduce((sum, g) => sum + g.activities.length, 0);
  const grandTotalAll = packages.reduce((sum, p) => sum + computeGrandTotalFor(p.groups), 0);

  return (
    <>
      <div className="summary-row visible" id="summaryRow">
        <div className="summary-bar">
          {packages.length > 1 && (
            <div className="summary-stat">
              <span className="summary-value">{packages.findIndex((p) => p.id === activeId) + 1}/{packages.length}</span>
              <span className="summary-label">Pacote</span>
            </div>
          )}
          <div className="summary-stat">
            <span className="summary-value">{fmtNum(total)} h</span>
            <span className="summary-label">Total de horas</span>
          </div>
          <div className="summary-stat">
            <span className="summary-value">{groupsCount}</span>
            <span className="summary-label">Grupo{groupsCount === 1 ? "" : "s"}</span>
          </div>
          <div className="summary-stat">
            <span className="summary-value">{activitiesCount}</span>
            <span className="summary-label">Atividade{activitiesCount === 1 ? "" : "s"}</span>
          </div>
        </div>
        <div id="summaryBarActions">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              const el = document.getElementById("step1");
              if (el) el.style.display = "block";
            }}
          >
            Trocar arquivo
          </button>
          <button type="button" id="btnTogglePreviewFloating">
            Recolher preview »
          </button>
        </div>
      </div>
      {/* hidden footer total, also used by GenerateFooter */}
      <div style={{ display: "none" }} id="generateTotalHidden">
        {packages.length > 1 ? `Total geral: ${fmtNum(grandTotalAll)} horas em ${packages.length} relatórios` : `Total: ${fmtNum(total)} horas`}
      </div>
    </>
  );
}
