import { useEffect, useRef, useState } from "react";
import {
  Sun, Moon, LogOut, LayoutDashboard, Stethoscope, FileText, Activity, History, BarChart3,
  ChevronLeft, Menu, X, Plus,
} from "lucide-react";
import { getInitialTheme, applyTheme, type Theme } from "../utils/theme";
import { useAuthStore } from "../store/useAuthStore";
import { useReportTabsStore } from "../store/useReportTabsStore";
import { useClickOutside } from "../hooks/useClickOutside";
import { ReportTabsBar } from "./ReportTabsBar";
import { VIEW_TITLES, type AppView } from "../appView";

const COLLAPSED_STORAGE_KEY = "sidebarCollapsed";

function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** "Diego Herrera da Silva" -> "DH" — só pro avatar, não existe campo de
 * iniciais no backend (ver useAuthStore.User). */
function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

const NAV_ITEMS: Array<{ view: AppView; label: string; icon: typeof FileText; managerOnly?: boolean }> = [
  { view: "report", label: "Gerar relatório", icon: FileText },
  { view: "dashboard", label: "Dashboard de horas", icon: Activity },
  // sem managerOnly: quem não é gerente também vê, mas só os PRÓPRIOS
  // relatórios — filtro é aplicado no backend (main._require_report_access),
  // mesmo princípio de /parse-db e /my-hours.
  { view: "history", label: "Histórico de relatórios", icon: History },
  { view: "management", label: "Painel de gerência", icon: LayoutDashboard, managerOnly: true },
  { view: "diagnostics", label: "Diagnóstico de relatórios", icon: Stethoscope, managerOnly: true },
  { view: "analytics", label: "Analytics", icon: BarChart3, managerOnly: true },
];

export function Sidebar({
  view,
  onNavigate,
}: {
  view: AppView;
  onNavigate: (view: AppView) => void;
}) {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const canSeeManagementPanel = Boolean(user?.isManager);
  const addTab = useReportTabsStore((s) => s.addTab);

  const [theme, setTheme] = useState<Theme>(() => {
    const t = document.documentElement.dataset.theme as Theme | undefined;
    return t === "light" || t === "dark" ? t : getInitialTheme();
  });
  useEffect(() => applyTheme(theme), [theme]);
  const isLight = theme === "light";

  const [collapsed, setCollapsed] = useState(getInitialCollapsed);
  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // localStorage indisponível — só perde a persistência da preferência,
      // não quebra a sidebar.
    }
  }, [collapsed]);

  // drawer mobile (< 920px) — estado separado do "recolhido" de desktop,
  // sempre fechado por padrão a cada navegação/resize pra desktop.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const asideRef = useRef<HTMLElement>(null);
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  useClickOutside([asideRef, menuBtnRef], () => setDrawerOpen(false), drawerOpen);
  useEffect(() => {
    if (!drawerOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  // no drawer mobile a sidebar sempre mostra os rótulos por inteiro,
  // independente da preferência de "recolhido" salva pro desktop — são dois
  // conceitos diferentes (recolhido = rail fino sempre visível; drawer =
  // painel cheio que abre por cima, só existe fechado ou aberto).
  const showLabels = !collapsed || drawerOpen;

  const navigate = (v: AppView) => {
    onNavigate(v);
    setDrawerOpen(false);
  };

  const openReportTab = (tabId: string) => {
    if (view !== "report") onNavigate("report");
    useReportTabsStore.getState().switchTab(tabId);
    setDrawerOpen(false);
  };

  return (
    <>
      {/* barra fina só em telas < 920px — dá acesso ao menu sem a sidebar
          precisar ficar sempre visível, e mantém o usuário orientado sobre
          em que tela está enquanto o drawer está fechado. */}
      <div className="mobile-topbar">
        <button
          ref={menuBtnRef}
          type="button"
          className="mobile-topbar-menu-btn"
          aria-label="Abrir menu de navegação"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen((v) => !v)}
        >
          <Menu size={20} strokeWidth={2} />
        </button>
        <span className="mobile-topbar-title">{VIEW_TITLES[view]}</span>
      </div>

      {drawerOpen && <div className="sidebar-drawer-overlay" onClick={() => setDrawerOpen(false)} aria-hidden="true" />}

      <aside
        ref={asideRef}
        className={`sidebar ${collapsed ? "collapsed" : ""} ${drawerOpen ? "drawer-open" : ""}`}
        aria-label="Barra lateral"
      >
        <div className="sidebar-head">
          <div className="sidebar-brand">
            {showLabels ? (
              <img
                src={isLight ? "logo-light.png" : "logo.png"}
                alt="Schwaben Engineering"
                className="sidebar-logo"
                id="appLogo"
              />
            ) : (
              <span className="sidebar-logo-mark" aria-hidden="true">S</span>
            )}
            {showLabels && <span className="sidebar-app-name">Relatório de Horas</span>}
          </div>
          <button
            type="button"
            className="sidebar-collapse-btn"
            title={collapsed ? "Expandir menu" : "Recolher menu"}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            onClick={() => setCollapsed((v) => !v)}
          >
            <ChevronLeft size={16} strokeWidth={2} className={collapsed ? "flipped" : ""} />
          </button>
          <button
            type="button"
            className="sidebar-drawer-close"
            aria-label="Fechar menu"
            onClick={() => setDrawerOpen(false)}
          >
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Navegação principal">
          {showLabels && <p className="sidebar-section-label">Navegação</p>}
          {NAV_ITEMS.filter((item) => !item.managerOnly || canSeeManagementPanel).map((item) => {
            const Icon = item.icon;
            const active = view === item.view;
            return (
              <button
                key={item.view}
                type="button"
                className={`sidebar-nav-item ${active ? "active" : ""}`}
                aria-current={active ? "page" : undefined}
                title={collapsed && !drawerOpen ? item.label : undefined}
                onClick={() => navigate(item.view)}
              >
                <Icon size={18} strokeWidth={1.8} />
                {showLabels && <span>{item.label}</span>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-tabs-section">
          {showLabels && <p className="sidebar-section-label">Relatórios abertos</p>}
          <ReportTabsBar collapsed={!showLabels} onOpenTab={openReportTab} />
          <button
            type="button"
            className="sidebar-new-report-btn"
            title="Novo relatório"
            onClick={() => {
              if (view !== "report") onNavigate("report");
              addTab();
              setDrawerOpen(false);
            }}
          >
            <Plus size={16} strokeWidth={2} />
            {showLabels && <span>Novo relatório</span>}
          </button>
        </div>

        {user && (
          <div className={`sidebar-footer ${showLabels ? "expanded" : "compact"}`}>
            <span className="sidebar-avatar" aria-hidden="true">{initialsFor(user.name)}</span>
            {showLabels && (
              <div className="sidebar-footer-text">
                <span className="sidebar-user-name">{user.name}</span>
                <span className="sidebar-user-role">{user.isManager ? "Gerente" : "Colaborador"}</span>
              </div>
            )}
            <div className="sidebar-footer-actions">
              <button
                type="button"
                className="sidebar-footer-btn"
                title={isLight ? "Mudar para tema escuro" : "Mudar para tema claro"}
                aria-label={isLight ? "Mudar para tema escuro" : "Mudar para tema claro"}
                onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
              >
                {isLight ? <Moon size={16} strokeWidth={1.7} /> : <Sun size={16} strokeWidth={1.7} />}
                {showLabels && <span>Tema</span>}
              </button>
              <button
                type="button"
                className="sidebar-footer-btn"
                title="Sair"
                aria-label="Sair"
                onClick={() => logout()}
              >
                <LogOut size={16} strokeWidth={1.7} />
                {showLabels && <span>Sair</span>}
              </button>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
