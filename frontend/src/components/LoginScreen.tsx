import { useEffect, useState } from "react";
import { useAuthStore } from "../store/useAuthStore";
import { getInitialTheme } from "../utils/theme";

export function LoginScreen() {
  const login = useAuthStore((s) => s.login);
  const [logoSrc] = useState(() => {
    const t = document.documentElement.dataset.theme;
    const theme = t === "light" || t === "dark" ? t : getInitialTheme();
    return theme === "light" ? "logo-light.png" : "logo.png";
  });

  useEffect(() => {
    document.body.classList.add("login-active");
    return () => document.body.classList.remove("login-active");
  }, []);

  const [loginValue, setLoginValue] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginValue.trim() || !password) return;
    setError("");
    setLoading(true);
    try {
      await login(loginValue.trim(), password);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-status">
          <span className="login-status-dot" aria-hidden="true" />
          SISTEMA · AUTENTICAÇÃO PROJECTILE
        </div>

        <img src={logoSrc} alt="Schwaben Engineering" className="login-logo" />
        <h1>Geração de Relatório de Horas</h1>
        <p className="login-subtitle">Entre com seu usuário do Projectile</p>

        <label htmlFor="loginUser">Usuário</label>
        <input
          id="loginUser"
          type="text"
          value={loginValue}
          onChange={(e) => setLoginValue(e.target.value)}
          autoFocus
          autoComplete="username"
        />
        <label htmlFor="loginPassword">Senha</label>
        <input
          id="loginPassword"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />

        {error && <p className="login-error" role="alert">{error}</p>}

        <button className="primary" type="submit" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </div>
  );
}
