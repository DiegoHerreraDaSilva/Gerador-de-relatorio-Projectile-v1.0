import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Rede de segurança contra qualquer erro de render não tratado.
 *
 * Sem isto, um erro em QUALQUER componente (um campo inesperadamente nulo,
 * uma linha de dado com formato diferente do previsto) derruba a árvore
 * inteira do React sem aviso — a página vira só o fundo escuro do `body`,
 * sem nenhuma pista do que quebrou nem como se recuperar. É exatamente o
 * "às vezes não abre, fica tela escura" relatado no Painel de Gerência.
 *
 * `getDerivedStateFromError`/`componentDidCatch` só existem em componente de
 * classe — não há equivalente em hook. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] erro não tratado:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary" role="alert">
          <AlertTriangle size={28} strokeWidth={1.5} />
          <h2>Algo deu errado nesta tela</h2>
          <p className="muted">
            {this.state.error.message || "Erro desconhecido."}
          </p>
          <p className="muted">
            Tenta recarregar a página. Se continuar acontecendo, avisa o TI com a
            mensagem acima.
          </p>
          <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
            Recarregar página
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
