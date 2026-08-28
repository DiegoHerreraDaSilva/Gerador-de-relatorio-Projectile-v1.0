import { useEffect } from "react";
import { Header } from "./components/Header";
import { LoginScreen } from "./components/LoginScreen";
import { useAuthStore } from "./store/useAuthStore";
import { Stepper } from "./components/Stepper";
import { ValidationBanner } from "./components/ValidationBanner";
import { FileUpload } from "./components/FileUpload";
import { PackageTabs } from "./components/PackageTabs";
import { HeaderDataCard } from "./components/HeaderDataCard";
import { GroupsPanel } from "./components/GroupsPanel";
import { PackageFileName } from "./components/PackageFileName";
import { Preview } from "./components/Preview/Preview";
import { GenerateFooter } from "./components/GenerateFooter";
import { Chat } from "./components/Chat";
import { useReportStore } from "./store/useReportStore";
import { computeGrandTotalFor } from "./utils/calc";
import { fmtNum } from "./utils/fmt";

export default function App() {
  const packages = useReportStore((s) => s.packages);
  const activeId = useReportStore((s) => s.activePackageId);
  const previewCollapsed = useReportStore((s) => s.previewCollapsed);
  const setPreviewCollapsed = useReportStore((s) => s.setPreviewCollapsed);
  const isSplit = useReportStore((s) => s.isSplit);
  const authStatus = useAuthStore((s) => s.status);
  const checkSession = useAuthStore((s) => s.checkSession);

  const hasPackages = packages.length > 0;
  const activePkg = packages.find((p) => p.id === activeId);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  // footer height sync: keep --footer-height accurate? Legacy fixed 100px, we keep CSS var.
  // Update generateTotal for non-footer? Already handled in GenerateFooter.

  useEffect(() => {
    const handler = () => {
      const wrap = document.getElementById("previewSheetWrap");
      const btn = document.getElementById("btnFullscreen");
      if (btn) btn.textContent = document.fullscreenElement === wrap ? "⛶ Sair da tela cheia" : "⛶ Tela cheia";
    };
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  if (authStatus === "loading") return null;
  if (authStatus === "unauthenticated") return <LoginScreen />;

  return (
    <>
      <Header />
      <Stepper />
      {hasPackages && (
        <div className={`summary-row ${hasPackages ? "visible" : ""}`}>
          <div className="summary-bar">
            {packages.length > 1 && (
              <div className="summary-stat">
                <span className="summary-value">
                  {packages.findIndex((p) => p.id === activeId) + 1}/{packages.length}
                </span>
                <span className="summary-label">Pacote</span>
              </div>
            )}
            {activePkg && (
              <>
                <div className="summary-stat">
                  <span className="summary-value">{fmtNum(computeGrandTotalFor(activePkg.groups))} h</span>
                  <span className="summary-label">Total de horas</span>
                </div>
                <div className="summary-stat">
                  <span className="summary-value">{activePkg.groups.length}</span>
                  <span className="summary-label">Grupo{activePkg.groups.length === 1 ? "" : "s"}</span>
                </div>
                <div className="summary-stat">
                  <span className="summary-value">{activePkg.groups.reduce((sum, g) => sum + g.activities.length, 0)}</span>
                  <span className="summary-label">Atividade</span>
                </div>
              </>
            )}
          </div>
          <div id="summaryBarActions">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                const el = document.getElementById("step1");
                if (el) el.style.display = "block";
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            >
              Trocar arquivo
            </button>
            {!isSplit && (
              <button
                type="button"
                id="btnTogglePreviewFloating"
                onClick={() => {
                  // replicate legacy fade logic
                  const columns = document.querySelector(".app-body") as HTMLElement | null;
                  const previewColumn = document.getElementById("previewColumn") as HTMLElement | null;
                  const btn = document.getElementById("btnTogglePreviewFloating") as HTMLButtonElement | null;
                  if (!previewColumn || !columns || !btn) return;
                  const isCollapsing = !previewColumn.classList.contains("fade-out");
                  if (isCollapsing) {
                    previewColumn.classList.add("fade-out");
                    btn.textContent = "« Mostrar preview";
                    setTimeout(() => {
                      previewColumn.classList.add("hidden");
                      columns.classList.add("preview-collapsed");
                      setPreviewCollapsed(true);
                    }, 220);
                  } else {
                    previewColumn.classList.remove("hidden");
                    columns.classList.remove("preview-collapsed");
                    void previewColumn.offsetWidth;
                    previewColumn.classList.remove("fade-out");
                    btn.textContent = "Recolher preview »";
                    setPreviewCollapsed(false);
                  }
                }}
              >
                {previewCollapsed ? "« Mostrar preview" : "Recolher preview »"}
              </button>
            )}
          </div>
        </div>
      )}

      <ValidationBanner />

      <FileUpload />

      <div id="step2" className={hasPackages ? "visible" : ""} style={{ display: hasPackages ? "block" : "none" }}>
        <PackageTabs />
        <div className={`app-body ${previewCollapsed ? "preview-collapsed" : ""} ${isSplit ? "split-mode" : ""}`}>
          <aside className="sidebar">
            <PackageFileName />
            <HeaderDataCard />
            <GroupsPanel />
          </aside>
          <Preview />
        </div>
      </div>

      <GenerateFooter />
      <Chat />
    </>
  );
}
