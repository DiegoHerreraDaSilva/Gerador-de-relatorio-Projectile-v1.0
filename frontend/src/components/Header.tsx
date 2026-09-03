import { useEffect, useState } from "react";
import { Sun, Moon, LogOut, LayoutDashboard, Stethoscope, FileText } from "lucide-react";
import { getInitialTheme, applyTheme, type Theme } from "../utils/theme";
import { useAuthStore } from "../store/useAuthStore";
import type { AppView } from "../App";

export function Header({
  view,
  onNavigate,
}: {
  view: AppView;
  onNavigate: (view: AppView) => void;
}) {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const canSeeManagementPanel = Boolean(user?.isManager);
  const [theme, setTheme] = useState<Theme>(() => {
    // theme already applied by inline script, just read it
    const t = document.documentElement.dataset.theme as Theme | undefined;
    return t === "light" || t === "dark" ? t : getInitialTheme();
  });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // sync logo on mount (inline script already set theme, just ensure logo matches)
  useEffect(() => {
    const logo = document.getElementById("appLogo") as HTMLImageElement | null;
    if (logo) logo.src = theme === "light" ? "logo-light.png" : "logo.png";
  }, [theme]);

  const isLight = theme === "light";

  return (
    <header className="app-header">
      <h1>
        {view === "management" ? (
          <>Painel de <span className="app-header-accent">Gerência</span></>
        ) : view === "diagnostics" ? (
          <>Diagnóstico de <span className="app-header-accent">relatórios</span></>
        ) : (
          <>Geração de <span className="app-header-accent">Relatório de Horas</span></>
        )}
      </h1>
      <div className="app-header-actions">
        <button
          type="button"
          className={`nav-tab ${view === "report" ? "active" : ""}`}
          onClick={() => onNavigate("report")}
        >
          <FileText size={15} strokeWidth={1.8} />
          Gerar Relatório
        </button>
        {canSeeManagementPanel && (
          <>
            <button
              type="button"
              className={`nav-tab ${view === "management" ? "active" : ""}`}
              onClick={() => onNavigate("management")}
            >
              <LayoutDashboard size={15} strokeWidth={1.8} />
              Painel de Gerência
            </button>
            <button
              type="button"
              className={`nav-tab ${view === "diagnostics" ? "active" : ""}`}
              onClick={() => onNavigate("diagnostics")}
            >
              <Stethoscope size={15} strokeWidth={1.8} />
              Diagnóstico de relatórios
            </button>
          </>
        )}
        {user && (
          <div className="user-info">
            <span className="user-name">{user.name}</span>
            <button type="button" className="theme-toggle" title="Sair" aria-label="Sair" onClick={() => logout()}>
              <LogOut size={17} strokeWidth={1.7} />
            </button>
          </div>
        )}
        <button
          type="button"
          className="theme-toggle"
          title={isLight ? "Mudar para tema escuro" : "Mudar para tema claro"}
          aria-label={isLight ? "Mudar para tema escuro" : "Mudar para tema claro"}
          onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
        >
          {isLight ? <Moon size={18} strokeWidth={1.7} /> : <Sun size={18} strokeWidth={1.7} />}
        </button>
        <img
          src={isLight ? "logo-light.png" : "logo.png"}
          alt="Schwaben Engineering"
          className="app-logo"
          id="appLogo"
        />
      </div>
    </header>
  );
}
