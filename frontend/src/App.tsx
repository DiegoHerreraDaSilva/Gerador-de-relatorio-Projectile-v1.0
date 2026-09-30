import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { VIEW_TITLES, type AppView } from "./appView";
import { LoginScreen } from "./components/LoginScreen";
import { AutoReportBar } from "./components/AutoReportBar";
import { CommandPalette } from "./components/CommandPalette";
import { LoadingState } from "./components/PageStates";
import { useReportTabsStore } from "./store/useReportTabsStore";
import { useAuthStore } from "./store/useAuthStore";
import { ValidationBanner } from "./components/ValidationBanner";
import { FileUpload } from "./components/FileUpload";
import { PackageTabs } from "./components/PackageTabs";
import { PackageFileName } from "./components/PackageFileName";
import { Preview } from "./components/Preview/Preview";
import { GenerateFooter } from "./components/GenerateFooter";
import { Chat } from "./components/Chat";
import { useReportStore } from "./store/useReportStore";
import { useAutoGenerationStore } from "./store/useAutoGenerationStore";
import { useMyReviewsStore } from "./store/useMyReviewsStore";
import { computeGrandTotalFor } from "./utils/calc";
import { BASE_TITLE, parseDeepLink, titleWithPending } from "./utils/deepLink";
import { fmtNum } from "./utils/fmt";
import { buildCommands } from "./utils/commands";
import { isEditableTarget, resolveShortcut } from "./utils/shortcuts";
import { modalStack } from "./hooks/useModal";

// Só a tela do relatório (a de entrada) vem no primeiro carregamento; as outras oito viram arquivos próprios,
// baixados quando a pessoa abre a tela (o JS inicial caiu pela metade). Os painéis usam export nomeado,
// então o `default` é montado aqui.
const ManagementPanel = lazy(() =>
  import("./components/ManagementPanel").then((m) => ({ default: m.ManagementPanel })),
);
const DiagnosticsPanel = lazy(() =>
  import("./components/DiagnosticsPanel").then((m) => ({ default: m.DiagnosticsPanel })),
);
const MyHoursDashboard = lazy(() =>
  import("./components/MyHoursDashboard").then((m) => ({ default: m.MyHoursDashboard })),
);
const HistoryPanel = lazy(() => import("./components/HistoryPanel").then((m) => ({ default: m.HistoryPanel })));
const AnalyticsPanel = lazy(() => import("./components/AnalyticsPanel").then((m) => ({ default: m.AnalyticsPanel })));
const AnalyticsChatPanel = lazy(() =>
  import("./components/AnalyticsChatPanel").then((m) => ({ default: m.AnalyticsChatPanel })),
);
const AutoGenerationPanel = lazy(() =>
  import("./components/AutoGenerationPanel").then((m) => ({ default: m.AutoGenerationPanel })),
);
const MyReviewsPanel = lazy(() => import("./components/MyReviewsPanel").then((m) => ({ default: m.MyReviewsPanel })));

export default function App() {
  // deep link dos avisos por e-mail (`?view=…&report=…`) abre a guia certa
  const [view, setView] = useState<AppView>(() => parseDeepLink(window.location.search).view ?? "report");
  const authStatus = useAuthStore((s) => s.status);
  const checkSession = useAuthStore((s) => s.checkSession);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const tabs = useReportTabsStore((s) => s.tabs);
  const activeTabId = useReportTabsStore((s) => s.activeTabId);
  const assigned = useMyReviewsStore((s) => s.summary?.assigned ?? 0);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  // atalhos globais (regra pura em utils/shortcuts): Ctrl/⌘+K ou "/" abre a paleta; Ctrl/⌘+Z desfaz no relatório
  useEffect(() => {
    if (authStatus !== "authenticated") return;
    const onKeyDown = (e: KeyboardEvent) => {
      const action = resolveShortcut({
        key: e.key,
        ctrlKey: e.ctrlKey,
        metaKey: e.metaKey,
        shiftKey: e.shiftKey,
        altKey: e.altKey,
        targetEditable: isEditableTarget(e.target as HTMLElement | null),
        modalOpen: modalStack.size() > 0,
        view,
      });
      if (action === "palette") {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      } else if (action === "undo") {
        e.preventDefault();
        useReportStore.getState().undo();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [authStatus, view]);

  const commands = useMemo(
    () =>
      buildCommands({
        isManager: Boolean(user?.isManager),
        isCoordinator: Boolean(user?.isCoordinator),
        currentView: view,
        hasAssignedReviews: assigned > 0,
        tabs: tabs.map((t) => ({ id: t.id, label: t.label })),
        activeTabId,
        navigate: setView,
        switchTab: (id) => useReportTabsStore.getState().switchTab(id),
        newReport: () => {
          setView("report");
          useReportTabsStore.getState().addTab();
        },
        logout: () => void logout(),
      }),
    [user, view, assigned, tabs, activeTabId, logout],
  );

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    const { view: targetView, reportId } = parseDeepLink(window.location.search);
    if (!targetView && !reportId) return;
    if (reportId && targetView) {
      const role = targetView === "my-reviews" ? "reviewer" : "manager";
      void useAutoGenerationStore
        .getState()
        .openInEditor(reportId, role)
        .then(() => setView("report"))
        .catch(() => {});
    } else if (targetView) {
      setView(targetView);
    }
    // limpa a query pra um F5 não reabrir a guia por cima do que o usuário fizer
    window.history.replaceState({}, "", window.location.pathname);
  }, [authStatus]);

  // contador de pendências no título da aba (mesmo summary do menu)
  useEffect(() => {
    const apply = () => {
      document.title =
        authStatus === "authenticated" ? titleWithPending(useMyReviewsStore.getState().summary) : BASE_TITLE;
    };
    apply();
    if (authStatus !== "authenticated") return;
    void useMyReviewsStore
      .getState()
      .loadSummary()
      .catch(() => {});
    return useMyReviewsStore.subscribe(apply);
  }, [authStatus]);

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
    <div className="app-shell">
      <Sidebar view={view} onNavigate={setView} onOpenPalette={() => setPaletteOpen(true)} />
      {paletteOpen && <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />}
      <main className="app-main">
        {/* único heading semântico da tela — cada painel (Management/
            Diagnostics/MyHours) não tem <h1> próprio fora do estado de
            carregamento; a sidebar não é mais o header, então esse título
            precisa continuar existindo em algum lugar pra leitor de tela. */}
        <h1 className="sr-only">{VIEW_TITLES[view]}</h1>
        <Suspense
          fallback={
            <div className="card page-container">
              <LoadingState label={`Abrindo ${VIEW_TITLES[view]}...`} rows={5} />
            </div>
          }
        >
          {view === "management" && <ManagementPanel />}
          {view === "diagnostics" && <DiagnosticsPanel />}
          {view === "dashboard" && <MyHoursDashboard />}
          {view === "history" && <HistoryPanel />}
          {view === "analytics" && <AnalyticsPanel />}
          {view === "analytics-chat" && <AnalyticsChatPanel />}
          {view === "auto-generation" && <AutoGenerationPanel onNavigate={setView} />}
          {view === "my-reviews" && <MyReviewsPanel onNavigate={setView} />}
        </Suspense>
        {view === "report" && <ReportView />}
      </main>
    </div>
  );
}

function ReportView() {
  const packages = useReportStore((s) => s.packages);
  const resetForNewImport = useReportStore((s) => s.resetForNewImport);
  const activeId = useReportStore((s) => s.activePackageId);
  const isSplit = useReportStore((s) => s.isSplit);
  const hasPackages = packages.length > 0;
  const activePkg = packages.find((p) => p.id === activeId);
  // guia aberta pela geração automática: aprovar (barra) no lugar de
  // importar/gerar/enviar — o rascunho vive no servidor
  const isAutoTab = useReportTabsStore((s) => Boolean(s.tabs.find((t) => t.id === s.activeTabId)?.auto));

  return (
    <>
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
                  <span className="summary-value">
                    {activePkg.groups.reduce((sum, g) => sum + g.activities.length, 0)}
                  </span>
                  <span className="summary-label">Atividade</span>
                </div>
              </>
            )}
          </div>
          <div id="summaryBarActions">
            {!isAutoTab && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  resetForNewImport();
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              >
                Alterar dados
              </button>
            )}
          </div>
        </div>
      )}

      {isAutoTab && <AutoReportBar />}

      <ValidationBanner />

      {!isAutoTab && <FileUpload key={hasPackages ? "report-loaded" : "new-import"} />}

      <div id="step2" className={hasPackages ? "visible" : ""} style={{ display: hasPackages ? "block" : "none" }}>
        <PackageTabs />
        <PackageFileName />
        <div className={`app-body ${isSplit ? "split-mode" : ""}`}>
          <Preview />
        </div>
      </div>

      {!isAutoTab && <GenerateFooter />}
      <Chat />
    </>
  );
}
