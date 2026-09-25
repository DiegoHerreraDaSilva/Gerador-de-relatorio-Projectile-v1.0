import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Download, History, Search, X } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { useHistoryStore } from "../store/useHistoryStore";
import {
  formatAuditAction,
  formatCreatedFrom,
  formatDateTime,
  formatDurationMs,
  formatFileSize,
  formatGenerationStatus,
} from "../utils/historyFormat";

/** Tela de histórico de relatórios (`GET /reports/*`) — lista relatórios já gerados,
 * suas versões, arquivos e a trilha de auditoria. Autorização é feita no
 * backend (`_require_report_access`): quem não é gerente só vê os
 * próprios relatórios, então a lista já vem filtrada pelo servidor. */
export function HistoryPanel() {
  const reports = useHistoryStore((s) => s.reports);
  const page = useHistoryStore((s) => s.page);
  const pageSize = useHistoryStore((s) => s.pageSize);
  const total = useHistoryStore((s) => s.total);
  const loading = useHistoryStore((s) => s.loading);
  const error = useHistoryStore((s) => s.error);
  const filters = useHistoryStore((s) => s.filters);
  const setFilter = useHistoryStore((s) => s.setFilter);
  const loadReports = useHistoryStore((s) => s.loadReports);

  const selectedReportId = useHistoryStore((s) => s.selectedReportId);
  const selectedReport = useHistoryStore((s) => s.selectedReport);
  const versions = useHistoryStore((s) => s.versions);
  const generations = useHistoryStore((s) => s.generations);
  const artifacts = useHistoryStore((s) => s.artifacts);
  const auditEvents = useHistoryStore((s) => s.auditEvents);
  const detailLoading = useHistoryStore((s) => s.detailLoading);
  const detailError = useHistoryStore((s) => s.detailError);
  const selectReport = useHistoryStore((s) => s.selectReport);
  const clearSelection = useHistoryStore((s) => s.clearSelection);

  const selectedVersionId = useHistoryStore((s) => s.selectedVersionId);
  const selectedVersionDetail = useHistoryStore((s) => s.selectedVersionDetail);
  const versionDetailLoading = useHistoryStore((s) => s.versionDetailLoading);
  const loadVersionDetail = useHistoryStore((s) => s.loadVersionDetail);
  const closeVersionDetail = useHistoryStore((s) => s.closeVersionDetail);

  useEffect(() => {
    loadReports(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // busca enquanto digita, 300 ms depois da última tecla; a 1ª renderização
  // não busca de novo (o efeito acima já carregou a lista)
  const searchMounted = useRef(false);
  useEffect(() => {
    if (!searchMounted.current) {
      searchMounted.current = true;
      return;
    }
    const timer = window.setTimeout(() => loadReports(1), 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.search]);
  const searchTerm = filters.search.trim();

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="history-panel page-container">
      <PageHeader
        title="Histórico de relatórios"
        description="Consulte relatórios já gerados, suas versões, arquivos e a trilha de auditoria."
        icon={<History size={20} strokeWidth={1.8} />}
      />

      <form
        className="card history-search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          loadReports(1);
        }}
      >
        <Search size={17} strokeWidth={2} className="history-search-icon" aria-hidden="true" />
        <input
          type="text"
          autoComplete="off"
          spellCheck={false}
          aria-label="Buscar relatórios por número, projeto, competência ou quem criou"
          placeholder="Buscar por número, projeto, competência ou quem criou"
          value={filters.search}
          onChange={(e) => setFilter("search", e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && filters.search) setFilter("search", "");
          }}
        />
        {filters.search && (
          <button
            type="button"
            className="history-search-clear"
            aria-label="Limpar busca"
            title="Limpar busca"
            onClick={() => setFilter("search", "")}
          >
            <X size={15} strokeWidth={2} />
          </button>
        )}
      </form>

      {error && (
        <div className="card">
          <p className="error-text">{error}</p>
        </div>
      )}

      <div className="card history-table-wrap">
        {loading && <p className="muted">Carregando...</p>}
        {!loading && reports.length === 0 && (
          <p className="muted">
            {searchTerm ? `Nenhum relatório encontrado para "${searchTerm}".` : "Nenhum relatório encontrado."}
          </p>
        )}
        {!loading && reports.length > 0 && (
          <table className="kpi-table history-table">
            <thead>
              <tr>
                <th>Número</th>
                <th>Projeto</th>
                <th>Competência</th>
                <th>Versão</th>
                <th>Criado por</th>
                <th>Atualizado em</th>
                <th aria-label="Ações" />
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => {
                // no modo "por pacote" o escopo é o próprio nome do pacote, que
                // já aparece na coluna Projeto — repetir só alargava a tabela.
                const competence =
                  r.scope && r.scope !== r.project_name_snapshot
                    ? `${r.competence_label} · ${r.scope}`
                    : r.competence_label;
                return (
                  <tr key={r.id} className={r.id === selectedReportId ? "active" : ""}>
                    <td>{r.report_number}</td>
                    <td title={r.project_name_snapshot}>{r.project_name_snapshot}</td>
                    <td title={competence}>{competence}</td>
                    <td>v{r.current_version_number ?? "—"}</td>
                    <td>{r.created_by_name_snapshot}</td>
                    <td>{formatDateTime(r.updated_at)}</td>
                    <td>
                      <button type="button" className="btn-secondary" onClick={() => selectReport(r.id)}>
                        Ver detalhes
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {!loading && total > pageSize && (
          <div className="history-pagination">
            <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => loadReports(page - 1)}>
              Anterior
            </button>
            <span className="muted">
              Página {page} de {totalPages}
            </span>
            <button
              type="button"
              className="btn-secondary"
              disabled={page >= totalPages}
              onClick={() => loadReports(page + 1)}
            >
              Próxima
            </button>
          </div>
        )}
      </div>

      {selectedReportId && (
        <div className="card history-detail">
          <div className="history-detail-head">
            <h3>{selectedReport ? `${selectedReport.report_number} — ${selectedReport.project_name_snapshot}` : "Carregando..."}</h3>
            <button type="button" className="modal-close" aria-label="Fechar detalhe" onClick={clearSelection}>
              <X size={18} strokeWidth={2} />
            </button>
          </div>

          {detailLoading && <p className="muted">Carregando detalhe...</p>}
          {detailError && <p className="error-text">{detailError}</p>}

          {!detailLoading && !detailError && (
            <>
              <section className="history-detail-section">
                <h4>Versões</h4>
                {versions.length === 0 ? (
                  <p className="muted">Nenhuma versão registrada.</p>
                ) : (
                  <table className="kpi-table">
                    <thead>
                      <tr>
                        <th>Versão</th>
                        <th>Criado por</th>
                        <th>Origem</th>
                        <th>Data</th>
                        <th aria-label="Ações" />
                      </tr>
                    </thead>
                    <tbody>
                      {versions.map((v) => (
                        <tr key={v.id}>
                          <td>v{v.version_number}</td>
                          <td>{v.created_by}</td>
                          <td>{formatCreatedFrom(v.created_from)}</td>
                          <td>{formatDateTime(v.created_at)}</td>
                          <td>
                            <button type="button" className="btn-secondary" onClick={() => loadVersionDetail(v.id)}>
                              Ver dados
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="history-detail-section">
                <h4>Gerações</h4>
                {generations.length === 0 ? (
                  <p className="muted">Nenhuma tentativa de geração registrada.</p>
                ) : (
                  <table className="kpi-table">
                    <thead>
                      <tr>
                        <th>Versão</th>
                        <th>Formato</th>
                        <th>Status</th>
                        <th>Iniciado em</th>
                        <th>Duração</th>
                        <th>Erro</th>
                      </tr>
                    </thead>
                    <tbody>
                      {generations.map((g) => (
                        <tr key={g.id}>
                          <td>v{g.version_number}</td>
                          <td>{g.format.toUpperCase()}</td>
                          <td>
                            <span className={`history-status-pill history-status-${g.status}`}>
                              {formatGenerationStatus(g.status)}
                            </span>
                          </td>
                          <td>{formatDateTime(g.started_at)}</td>
                          <td>{formatDurationMs(g.duration_ms)}</td>
                          <td title={g.error_message ?? undefined}>{g.error_code ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="history-detail-section">
                <h4>Arquivos</h4>
                {artifacts.length === 0 ? (
                  <p className="muted">Nenhum arquivo gerado ainda.</p>
                ) : (
                  <table className="kpi-table">
                    <thead>
                      <tr>
                        <th>Versão</th>
                        <th>Arquivo</th>
                        <th>Tamanho</th>
                        <th>Gerado em</th>
                        <th aria-label="Ações" />
                      </tr>
                    </thead>
                    <tbody>
                      {artifacts.map((a) => (
                        <tr key={a.id}>
                          <td>v{a.version_number}</td>
                          <td title={a.file_name}>{a.file_name}</td>
                          <td>{formatFileSize(a.file_size)}</td>
                          <td>{formatDateTime(a.created_at)}</td>
                          <td>
                            <a className="btn-secondary history-download-link" href={`/artifacts/${a.id}/download`}>
                              <Download size={14} strokeWidth={2} />
                              Baixar
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="history-detail-section">
                <h4>Auditoria</h4>
                {auditEvents.length === 0 ? (
                  <p className="muted">Nenhum evento registrado.</p>
                ) : (
                  <ul className="history-audit-list">
                    {auditEvents.map((e) => (
                      <li key={e.id}>
                        <span className="history-audit-action">{formatAuditAction(e.action)}</span>
                        <span className="muted"> por {e.actor_name_snapshot || e.actor_id} em {formatDateTime(e.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
      )}

      {selectedVersionId &&
        createPortal(
          <div className="modal-backdrop" onClick={closeVersionDetail}>
            <div className="modal-card history-version-modal" onClick={(e) => e.stopPropagation()}>
              <div className="modal-head">
                <h2>{selectedVersionDetail ? `Versão ${selectedVersionDetail.version_number}` : "Carregando..."}</h2>
                <button type="button" className="modal-close" onClick={closeVersionDetail} aria-label="Fechar">
                  <X size={18} strokeWidth={2} />
                </button>
              </div>
              <div className="modal-body">
                {versionDetailLoading && <p className="muted">Carregando...</p>}
                {!versionDetailLoading && selectedVersionDetail && (
                  <div className="history-version-snapshot">
                    <p>
                      <strong>Projeto:</strong> {selectedVersionDetail.snapshot.data.header.project_name}
                    </p>
                    <p>
                      <strong>Competência:</strong> {selectedVersionDetail.snapshot.data.header.month_label}
                    </p>
                    {selectedVersionDetail.snapshot.data.groups.map((g, i) => (
                      <div key={i} className="history-version-group">
                        <h4>
                          {g.name} <span className="muted">({g.performance}%)</span>
                        </h4>
                        <ul>
                          {g.activities.map((a, j) => (
                            <li key={j}>
                              {a.description} — {a.hours ?? "extra"}h
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
