import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { LoginScreen } from "./components/LoginScreen";
import { ManagementPanel } from "./components/ManagementPanel";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { MyHoursDashboard } from "./components/MyHoursDashboard";
import { useAuthStore } from "./store/useAuthStore";
import { ValidationBanner } from "./components/ValidationBanner";
import { FileUpload } from "./components/FileUpload";
import { PackageTabs } from "./components/PackageTabs";
import { PackageFileName } from "./components/PackageFileName";
import { Preview } from "./components/Preview/Preview";
import { GenerateFooter } from "./components/GenerateFooter";
import { Chat } from "./components/Chat";
import { useReportStore } from "./store/useReportStore";
import { computeGrandTotalFor } from "./utils/calc";
import { fmtNum } from "./utils/fmt";

export type AppView = "report" | "management" | "diagnostics" | "dashboard";

export default function App() {
  const [view, setView] = useState<AppView>("report");
  const packages = useReportStore((s) => s.packages);
  const showImportCard = useReportStore((s) => s.showImportCard);
  const setShowImportCard = useReportStore((s) => s.setShowImportCard);
  const activeId = useReportStore((s) => s.activePackageId);
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

  if (view === "management") {
    return (
      <>
        <Header view={view} onNavigate={setView} />
        <ManagementPanel />
      </>
    );
  }

  if (view === "diagnostics") {
    return (
      <>
        <Header view={view} onNavigate={setView} />
        <DiagnosticsPanel />
      </>
    );
  }

  if (view === "dashboard") {
    return (
      <>
        <Header view={view} onNavigate={setView} />
        <MyHoursDashboard />
      </>
    );
  }

  return (
    <>
      <Header view={view} onNavigate={setView} />
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
                setShowImportCard(true);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            >
              Trocar arquivo
            </button>
          </div>
        </div>
      )}

      <ValidationBanner />

      <FileUpload />

      <div id="step2" className={hasPackages ? "visible" : ""} style={{ display: hasPackages ? "block" : "none" }}>
        <PackageTabs />
        <PackageFileName />
        <div className={`app-body ${isSplit ? "split-mode" : ""}`}>
          <Preview />
        </div>
      </div>

      <GenerateFooter />
      <Chat />
    </>
  );
}
