import { useEffect, useState } from "react";
import { Sun, Moon, LogOut } from "lucide-react";
import { getInitialTheme, applyTheme, type Theme } from "../utils/theme";
import { useAuthStore } from "../store/useAuthStore";

export function Header() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
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
      <h1>Geração de Relatório de Horas</h1>
      <div className="app-header-actions">
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
