import { useState } from "react";
import { useAuthStore } from "../store/useAuthStore";

export function LoginScreen() {
  const login = useAuthStore((s) => s.login);
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
        <img src="logo.png" alt="Schwaben Engineering" className="login-logo" />
        <h1>Geração de Relatório de Horas</h1>
        <p className="login-subtitle">Entre com seu usuário do Projectile</p>

        <label>Usuário</label>
        <input
          type="text"
          value={loginValue}
          onChange={(e) => setLoginValue(e.target.value)}
          autoFocus
          autoComplete="username"
        />
        <label>Senha</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />

        {error && <p className="login-error">{error}</p>}

        <button className="primary" type="submit" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </div>
  );
}
