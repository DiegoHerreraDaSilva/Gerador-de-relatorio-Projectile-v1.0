import { useEffect, useRef } from "react";
import { useReportStore } from "../../store/useReportStore";
import { PreviewSheet } from "./PreviewSheet";

function BarChartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="1.5" y="8.5" width="3" height="6" rx="1" fill="currentColor" />
      <rect x="6.5" y="4.5" width="3" height="10" rx="1" fill="currentColor" />
      <rect x="11.5" y="1.5" width="3" height="13" rx="1" fill="currentColor" />
    </svg>
  );
}

function PieChartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5H8V1.5Z" fill="currentColor" />
      <path d="M9.5 1.55A6.5 6.5 0 0 1 14.45 6.5H9.5V1.55Z" fill="currentColor" opacity="0.5" />
    </svg>
  );
}

// Shared drag-and-drop handlers for a preview pane (used by both pane 0 and pane 1
// in split-view). `paneId` is the package id that pane is currently showing — group
// drops from another package land here via moveGroupToPackage.
function createPaneDragHandlers(paneId: string | null) {
  return {
    onDragEnter: (e: React.DragEvent<HTMLDivElement>) => {
      const dg = useReportStore.getState().draggedGroup;
      if (dg && paneId && dg.fromPackageId !== paneId) (e.currentTarget as HTMLElement).classList.add("drop-target");
    },
    onDragLeave: (e: React.DragEvent<HTMLDivElement>) => (e.currentTarget as HTMLElement).classList.remove("drop-target"),
    onDragOver: (e: React.DragEvent<HTMLDivElement>) => {
      if (useReportStore.getState().draggedGroup) e.preventDefault();
    },
    onDrop: (e: React.DragEvent<HTMLDivElement>) => {
      const dg = useReportStore.getState().draggedGroup;
      (e.currentTarget as HTMLElement).classList.remove("drop-target");
      if (!dg || !paneId) return;
      e.preventDefault();
      if (dg.fromPackageId !== paneId) {
        useReportStore.getState().moveGroupToPackage(dg.fromPackageId, dg.groupId, paneId);
        useReportStore.getState().setDraggedGroup(null);
      }
    },
  };
}

export function Preview() {
  const packages = useReportStore((s) => s.packages);
  const activeId = useReportStore((s) => s.activePackageId);
  const isSplit = useReportStore((s) => s.isSplit);
  const paneBId = useReportStore((s) => s.paneBPackageId);
  const setSplit = useReportStore((s) => s.setSplit);
  const setPaneB = useReportStore((s) => s.setPaneBPackageId);
  const previewZoom = useReportStore((s) => s.previewZoom);
  const setZoom = useReportStore((s) => s.setPreviewZoom);
  const undoStack = useReportStore((s) => s.undoStack);
  const undo = useReportStore((s) => s.undo);
  const setChartBar = useReportStore((s) => s.setChartBar);
  const setChartPie = useReportStore((s) => s.setChartPie);

  const hasPackages = packages.length > 0;
  const activePkg = packages.find((p) => p.id === activeId) ?? null;
  const paneBPackage = packages.find((p) => p.id === paneBId) ?? null;

  const splitAvailable = packages.length >= 2;
  const primaryPaneId = activeId;
  const secondaryPaneId = isSplit ? (paneBPackage?.id ?? null) : null;

  const primaryPaneDragHandlers = createPaneDragHandlers(primaryPaneId);
  const secondaryPaneDragHandlers = createPaneDragHandlers(secondaryPaneId);

  // Apply zoom via CSS zoom property on preview sheets
  useEffect(() => {
    document.querySelectorAll<HTMLDivElement>(".preview-sheet").forEach((el) => {
      (el as HTMLElement).style.zoom = `${previewZoom}%`;
    });
    const label = document.getElementById("zoomLabel");
    if (label) label.textContent = `${previewZoom}%`;
    // Intentionally NOT depending on `packages`: immer gives that array a new
    // reference on every edit (any hours/description keystroke), which would make
    // this DOM query re-run on every keystroke in the whole report. This effect
    // only needs to react to zoom level, split mode, and which package/pane is
    // being shown — all covered by the deps below. The "no packages -> packages
    // just loaded" transition stays covered without `packages` because
    // setPackages() always resets activePackageId (null -> the first loaded
    // package's freshly generated id) in that same store update.
  }, [previewZoom, isSplit, activeId, paneBId]);

  if (!hasPackages || !activePkg) {
    return (
      <main className="preview-column" id="previewColumn">
        <div className="card">
          <div className="preview-toolbar">
            <h2>Preview do relatório final</h2>
            <div className="preview-tools">
              <button type="button" className="btn-toggle" disabled title="Desfazer a última alteração">↶ Desfazer</button>
              <button type="button" className="btn-toggle" disabled title="Gráfico de barras">
                <BarChartIcon />
              </button>
              <button type="button" className="btn-toggle" disabled title="Gráfico de pizza">
                <PieChartIcon />
              </button>
              <button type="button" className="btn-toggle" disabled title="Ver 2 relatórios lado a lado">⇆ Dividir tela</button>
              <button type="button" onClick={() => setZoom(previewZoom - 10)}>−</button>
              <span id="zoomLabel">{previewZoom}%</span>
              <button type="button" onClick={() => setZoom(previewZoom + 10)}>+</button>
              <button type="button" id="btnFullscreen" disabled>⛶ Tela cheia</button>
            </div>
          </div>
          <div className="preview-sheet-wrap">
            <div className="preview-sheet">
              <p className="preview-empty">Analise um arquivo do Projectile para ver o preview.</p>
            </div>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="preview-column" id="previewColumn">
      <div className="card">
        <div className="preview-toolbar">
          <h2>Preview do relatório final</h2>
          <div className="preview-tools">
            <button type="button" className="btn-toggle" disabled={undoStack.length === 0} onClick={() => undo()} title="Desfazer a última alteração">
              ↶ Desfazer
            </button>
            <button
              type="button"
              className={`btn-toggle ${activePkg?.chartBar ? "active" : ""}`}
              onClick={() => activePkg && setChartBar(activePkg.id, !activePkg.chartBar)}
              title="Gráfico de barras no relatório"
            >
              <BarChartIcon />
            </button>
            <button
              type="button"
              className={`btn-toggle ${activePkg?.chartPie ? "active" : ""}`}
              onClick={() => activePkg && setChartPie(activePkg.id, !activePkg.chartPie)}
              title="Gráfico de pizza no relatório"
            >
              <PieChartIcon />
            </button>
            <button
              type="button"
              className={`btn-toggle ${isSplit ? "active" : ""}`}
              disabled={!splitAvailable}
              onClick={() => setSplit(!isSplit)}
              title="Ver 2 relatórios lado a lado"
            >
              ⇆ Dividir tela
            </button>
            <button type="button" onClick={() => setZoom(previewZoom - 10)}>−</button>
            <span id="zoomLabel">{previewZoom}%</span>
            <button type="button" onClick={() => setZoom(previewZoom + 10)}>+</button>
            <button
              type="button"
              id="btnFullscreen"
              disabled={isSplit}
              onClick={() => {
                const wrap = document.getElementById("previewSheetWrap");
                if (!wrap) return;
                if (document.fullscreenElement === wrap) document.exitFullscreen();
                else wrap.requestFullscreen().catch(() => {});
              }}
            >
              ⛶ Tela cheia
            </button>
          </div>
        </div>

        <div className={`preview-panes ${isSplit ? "split-active" : ""}`} id="previewPanes">
          <div
            className="preview-pane"
            data-pane="0"
            {...primaryPaneDragHandlers}
          >
            {isSplit && (
              <div className="preview-pane-header">
                <select
                  className="pane-package-select"
                  value={primaryPaneId ?? ""}
                  onChange={(e) => useReportStore.getState().setActivePackageId(e.target.value)}
                >
                  {packages.map((pkg) => (
                    <option key={pkg.id} value={pkg.id} disabled={pkg.id === secondaryPaneId}>
                      {pkg.projectName || pkg.key}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="preview-sheet-wrap" id="previewSheetWrap">
              <PreviewSheet paneId="0" packageId={primaryPaneId!} />
            </div>
          </div>

          {isSplit && (
            <div
              className="preview-pane"
              data-pane="1"
              id="previewPane2"
              {...secondaryPaneDragHandlers}
            >
              <div className="preview-pane-header">
                <select
                  className="pane-package-select"
                  value={secondaryPaneId ?? ""}
                  onChange={(e) => setPaneB(e.target.value)}
                >
                  {packages.map((pkg) => (
                    <option key={pkg.id} value={pkg.id} disabled={pkg.id === primaryPaneId}>
                      {pkg.projectName || pkg.key}
                    </option>
                  ))}
                </select>
              </div>
              <div className="preview-sheet-wrap" id="previewSheetWrap2">
                {secondaryPaneId && <PreviewSheet paneId="1" packageId={secondaryPaneId} />}
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
