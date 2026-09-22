import { useEffect } from "react";
import { BarChart3, RefreshCw } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { useAnalyticsStore } from "../store/useAnalyticsStore";

function formatHours(hours: number): string {
  return `${hours.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}h`;
}

function formatPercent(rate: number | null): string {
  if (rate === null) return "—";
  return `${(rate * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function formatMs(ms: number | null): string {
  if (ms === null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}s` : `${Math.round(ms)}ms`;
}

/** Tela de métricas agregadas sobre `reports_db` (Fase 9 do
 * GUIA_EVOLUCAO_GERADOR_PROJECTILE.md) — só gerente (ver `managerOnly` em
 * `Sidebar.tsx`, reforçado no backend por `require_manager`). Fica esparsa
 * até acumular meses de uso real: cada seção trata lista vazia como estado
 * vazio explícito, nunca como erro. */
export function AnalyticsPanel() {
  const summary = useAnalyticsStore((s) => s.summary);
  const loading = useAnalyticsStore((s) => s.loading);
  const error = useAnalyticsStore((s) => s.error);
  const loadSummary = useAnalyticsStore((s) => s.loadSummary);

  useEffect(() => {
    loadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="analytics-panel page-container">
      <PageHeader
        title="Analytics"
        description="Métricas agregadas sobre relatórios gerados: horas, tempo de geração e taxa de falhas."
        icon={<BarChart3 size={20} strokeWidth={1.8} />}
        actions={
          <button type="button" className="btn-secondary" onClick={() => loadSummary()} disabled={loading}>
            <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} />
            Atualizar
          </button>
        }
      />

      {error && (
        <div className="card">
          <p className="error-text">{error}</p>
        </div>
      )}

      {loading && !summary && (
        <div className="card">
          <p className="muted">Carregando...</p>
        </div>
      )}

      {!loading && !error && summary && summary.totals.reports === 0 && (
        <div className="card">
          <p className="muted">
            Ainda não há relatórios suficientes gerados por este sistema pra formar métricas. As seções abaixo vão se
            preencher conforme relatórios forem gerados via "Gerar relatório final".
          </p>
        </div>
      )}

      {summary && (
        <>
          <div className="analytics-totals">
            <div className="card analytics-total-card">
              <span className="analytics-total-value">{summary.totals.reports}</span>
              <span className="analytics-total-label">Relatórios</span>
            </div>
            <div className="card analytics-total-card">
              <span className="analytics-total-value">{summary.totals.versions}</span>
              <span className="analytics-total-label">Versões</span>
            </div>
            <div className="card analytics-total-card">
              <span className="analytics-total-value">{summary.totals.artifacts}</span>
              <span className="analytics-total-label">Arquivos gerados</span>
            </div>
            <div className="card analytics-total-card">
              <span className="analytics-total-value">{formatPercent(summary.generation.failure_rate)}</span>
              <span className="analytics-total-label">Taxa de falha na geração</span>
            </div>
            <div className="card analytics-total-card">
              <span className="analytics-total-value">{formatMs(summary.generation.avg_duration_ms)}</span>
              <span className="analytics-total-label">Tempo médio de geração</span>
            </div>
          </div>

          <div className="analytics-grid">
            <section className="card analytics-section">
              <h3>Horas por competência</h3>
              {summary.hours_by_competence.length === 0 ? (
                <p className="muted">Sem dados ainda.</p>
              ) : (
                <table className="kpi-table">
                  <thead>
                    <tr>
                      <th>Competência</th>
                      <th>Horas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.hours_by_competence.map((row) => (
                      <tr key={row.competence_label}>
                        <td>{row.competence_label}</td>
                        <td>{formatHours(row.hours)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card analytics-section">
              <h3>Horas por grupo</h3>
              {summary.hours_by_group.length === 0 ? (
                <p className="muted">Sem dados ainda.</p>
              ) : (
                <table className="kpi-table">
                  <thead>
                    <tr>
                      <th>Grupo</th>
                      <th>Horas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.hours_by_group.map((row) => (
                      <tr key={row.group_name}>
                        <td>{row.group_name}</td>
                        <td>{formatHours(row.hours)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card analytics-section">
              <h3>Horas por projeto</h3>
              {summary.hours_by_project.length === 0 ? (
                <p className="muted">Sem dados ainda.</p>
              ) : (
                <table className="kpi-table">
                  <thead>
                    <tr>
                      <th>Projeto</th>
                      <th>Horas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.hours_by_project.map((row) => (
                      <tr key={row.project_name}>
                        <td title={row.project_name}>{row.project_name}</td>
                        <td>{formatHours(row.hours)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card analytics-section">
              <h3>Relatórios gerados por mês</h3>
              {summary.reports_over_time.length === 0 ? (
                <p className="muted">Sem dados ainda.</p>
              ) : (
                <table className="kpi-table">
                  <thead>
                    <tr>
                      <th>Mês</th>
                      <th>Relatórios</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.reports_over_time.map((row) => (
                      <tr key={row.period}>
                        <td>{row.period}</td>
                        <td>{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card analytics-section">
              <h3>Responsáveis</h3>
              {summary.top_creators.length === 0 ? (
                <p className="muted">Sem dados ainda.</p>
              ) : (
                <table className="kpi-table">
                  <thead>
                    <tr>
                      <th>Nome</th>
                      <th>Relatórios</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.top_creators.map((row) => (
                      <tr key={row.login}>
                        <td>{row.name || row.login}</td>
                        <td>{row.reports}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="card analytics-section">
              <h3>Geração por formato</h3>
              {summary.generation.by_format.length === 0 ? (
                <p className="muted">Sem dados ainda.</p>
              ) : (
                <table className="kpi-table">
                  <thead>
                    <tr>
                      <th>Formato</th>
                      <th>Sucessos</th>
                      <th>Tempo médio</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.generation.by_format.map((row) => (
                      <tr key={row.format}>
                        <td>{row.format.toUpperCase()}</td>
                        <td>{row.count}</td>
                        <td>{formatMs(row.avg_duration_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
