import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronUp, ChevronsUpDown, Download, History, Search, Trash2, X } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { confirmDialog } from "./ConfirmDialog";
import { EmptyState, ErrorState, LoadingState } from "./PageStates";
import { toast } from "../store/useToastStore";
import { useAuthStore } from "../store/useAuthStore";
import { useHistoryStore, type SortColumn } from "../store/useHistoryStore";
import {
  formatAuditAction,
  formatCreatedFrom,
  formatDateTime,
  formatDurationMs,
  formatFileSize,
  formatGenerationStatus,
} from "../utils/historyFormat";

const COLUMNS: { key: SortColumn; label: string }[] = [
  { key: "numero", label: "Número" },
  { key: "projeto", label: "Projeto" },
  { key: "competencia", label: "Competência" },
  { key: "versao", label: "Versão" },
  { key: "criado_por", label: "Criado por" },
  { key: "atualizado", label: "Atualizado em" },
];

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

  const isManager = useAuthStore((s) => Boolean(s.user?.isManager));
  const sort = useHistoryStore((s) => s.sort);
  const setSort = useHistoryStore((s) => s.setSort);
  const checkedIds = useHistoryStore((s) => s.checkedIds);
  const checkedAll = useHistoryStore((s) => s.checkedAll);
  const toggleChecked = useHistoryStore((s) => s.toggleChecked);
  const checkPage = useHistoryStore((s) => s.checkPage);
  const checkAllMatching = useHistoryStore((s) => s.checkAllMatching);
  const clearChecked = useHistoryStore((s) => s.clearChecked);
  const deleteChecked = useHistoryStore((s) => s.deleteChecked);
  const [working, setWorking] = useState(false);
  const pageCheckbox = useRef<HTMLInputElement>(null);

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

  const pageIds = reports.map((r) => r.id);
  const checkedOnPage = pageIds.filter((id) => checkedIds.includes(id)).length;
  const allOnPageChecked = pageIds.length > 0 && checkedOnPage === pageIds.length;
  useEffect(() => {
    // "meio marcado": só parte da página está selecionada
    if (pageCheckbox.current) pageCheckbox.current.indeterminate = checkedOnPage > 0 && !allOnPageChecked;
  }, [checkedOnPage, allOnPageChecked]);

  async function selectEverything() {
    setWorking(true);
    try {
      await checkAllMatching();
    } catch {
      toast.error("Não consegui selecionar todos os resultados. Tenta de novo.");
    } finally {
      setWorking(false);
    }
  }

  async function deleteSelected() {
    const n = checkedIds.length;
    const ok = await confirmDialog({
      title: n === 1 ? "Apagar 1 relatório?" : `Apagar ${n} relatórios?`,
      message:
        "Versões, arquivos gerados e cópias dos dados serão apagados do banco e do disco. Não dá pra desfazer. A trilha de auditoria continua, com o registro de quem apagou.",
      confirmLabel: "Apagar",
      danger: true,
    });
    if (!ok) return;
    setWorking(true);
    try {
      const result = await deleteChecked();
      const count = result.deleted.length;
      toast.success(count === 1 ? "1 relatório apagado." : `${count} relatórios apagados.`);
      if (result.files_failed > 0)
        toast.error(`${result.files_failed} arquivo(s) não saíram do disco — confira a pasta de artefatos.`);
    } catch {
      toast.error("Não consegui apagar. Nada foi removido ou só parte foi; atualize a lista e confira.");
    } finally {
      setWorking(false);
    }
  }

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
          <ErrorState message={error} onRetry={() => loadReports(page)} busy={loading} />
        </div>
      )}

      <div className="card history-table-wrap">
        {isManager && checkedIds.length > 0 && (
          <div className="history-bulk" role="region" aria-label="Seleção de relatórios">
            <strong>
              {checkedIds.length} {checkedIds.length === 1 ? "selecionado" : "selecionados"}
            </strong>
            {checkedAll?.truncated && (
              <span className="muted">
                (os {checkedAll.total} resultados passam do limite; selecionei os mais recentes)
              </span>
            )}
            {!checkedAll && total > checkedIds.length && (
              <button type="button" className="auto-link-button" onClick={selectEverything} disabled={working}>
                Selecionar todos os {total} resultados
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={clearChecked} disabled={working}>
              Limpar seleção
            </button>
            <button
              type="button"
              className="btn-secondary auto-delete-button"
              onClick={deleteSelected}
              disabled={working}
            >
              <Trash2 size={14} strokeWidth={2} /> Apagar
            </button>
          </div>
        )}
        {loading && <LoadingState label="Carregando relatórios..." rows={5} />}
        {!loading && !error && reports.length === 0 && (
          <EmptyState
            icon={<History size={22} strokeWidth={1.6} />}
            title={
              searchTerm ? `Nenhum relatório encontrado para "${searchTerm}"` : "Nenhum relatório no histórico ainda"
            }
            description={
              searchTerm
                ? "Confira a grafia ou busque por outro número, projeto ou competência."
                : "Os relatórios aparecem aqui assim que são gerados, enviados ou aprovados."
            }
            action={searchTerm ? { label: "Limpar busca", onClick: () => setFilter("search", "") } : undefined}
          />
        )}
        {!loading && reports.length > 0 && (
          <table className="kpi-table history-table">
            <thead>
              <tr>
                {isManager && (
                  <th className="history-check-col">
                    <input
                      ref={pageCheckbox}
                      type="checkbox"
                      aria-label="Selecionar todos desta página"
                      checked={allOnPageChecked}
                      onChange={(e) => checkPage(e.target.checked)}
                    />
                  </th>
                )}
                {COLUMNS.map((column) => {
                  const active = sort?.column === column.key;
                  const Icon = !active ? ChevronsUpDown : sort.order === "asc" ? ChevronUp : ChevronDown;
                  return (
                    <th
                      key={column.key}
                      aria-sort={!active ? "none" : sort.order === "asc" ? "ascending" : "descending"}
                    >
                      <button type="button" className="history-sort" onClick={() => setSort(column.key)}>
                        {column.label}
                        <Icon size={13} strokeWidth={2} aria-hidden="true" className={active ? "active" : ""} />
                      </button>
                    </th>
                  );
                })}
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
                    {isManager && (
                      <td className="history-check-col">
                        <input
                          type="checkbox"
                          aria-label={`Selecionar o relatório ${r.report_number}`}
                          checked={checkedIds.includes(r.id)}
                          onChange={() => toggleChecked(r.id)}
                        />
                      </td>
                    )}
                    <td>{r.report_number}</td>
                    <td className="history-clip" title={r.project_name_snapshot}>
                      {r.project_name_snapshot}
                    </td>
                    <td className="history-clip" title={competence}>
                      {competence}
                    </td>
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
            <h3>
              {selectedReport
                ? `${selectedReport.report_number} — ${selectedReport.project_name_snapshot}`
                : "Carregando..."}
            </h3>
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
                        <span className="muted">
                          {" "}
                          por {e.actor_name_snapshot || e.actor_id} em {formatDateTime(e.created_at)}
                        </span>
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
          document.body,
        )}
    </div>
  );
}
