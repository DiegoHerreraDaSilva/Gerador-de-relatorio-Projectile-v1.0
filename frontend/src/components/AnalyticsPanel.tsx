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

/** Um bloco do Analytics: tabela de no máximo 8 linhas visíveis — com mais,
 * rola dentro do bloco (`.analytics-scroll-8`) e o cabeçalho fica fixo. */
function AnalyticsSection({
  title,
  columns,
  rows,
}: {
  title: string;
  columns: string[];
  rows: { key: string; cells: (string | number)[] }[];
}) {
  return (
    <section className="card analytics-section">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="muted">Sem dados ainda.</p>
      ) : (
        <div className="analytics-scroll-8">
          <table className="kpi-table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key}>
                  {row.cells.map((cell, i) => (
                    <td key={columns[i]} title={i === 0 ? String(cell) : undefined}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Tela de métricas agregadas sobre `reports_db` — só gerente (ver `managerOnly` em
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
              <span className="analytics-total-value">{summary.totals.artifacts}</span>
              <span className="analytics-total-label">Arquivos gerados</span>
            </div>
            <div className="card analytics-total-card">
              <span className="analytics-total-value">{formatPercent(summary.generation.failure_rate)}</span>
              <span className="analytics-total-label">Taxa de falha na geração</span>
            </div>
          </div>

          <div className="analytics-grid">
            <AnalyticsSection
              title="Horas por competência"
              columns={["Competência", "Horas"]}
              rows={summary.hours_by_competence.map((row) => ({
                key: row.competence_label,
                cells: [row.competence_label, formatHours(row.hours)],
              }))}
            />
            <AnalyticsSection
              title="Horas por grupo"
              columns={["Grupo", "Horas"]}
              rows={summary.hours_by_group.map((row) => ({
                key: row.group_name,
                cells: [row.group_name, formatHours(row.hours)],
              }))}
            />
            <AnalyticsSection
              title="Horas por projeto"
              columns={["Projeto", "Horas"]}
              rows={summary.hours_by_project.map((row) => ({
                key: row.project_name,
                cells: [row.project_name, formatHours(row.hours)],
              }))}
            />
            <AnalyticsSection
              title="Relatórios gerados por mês"
              columns={["Mês", "Relatórios"]}
              rows={summary.reports_over_time.map((row) => ({ key: row.period, cells: [row.period, row.count] }))}
            />
            <AnalyticsSection
              title="Responsáveis"
              columns={["Nome", "Relatórios"]}
              rows={summary.top_creators.map((row) => ({ key: row.login, cells: [row.name || row.login, row.reports] }))}
            />
            <AnalyticsSection
              title="Geração por formato"
              columns={["Formato", "Sucessos", "Tempo médio"]}
              rows={summary.generation.by_format.map((row) => ({
                key: row.format,
                cells: [row.format.toUpperCase(), row.count, formatMs(row.avg_duration_ms)],
              }))}
            />
          </div>
        </>
      )}
    </div>
  );
}
