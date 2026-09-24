import { Fragment, useState } from "react";
import { Check, Lock, MailSearch, Minus } from "lucide-react";
import { ClosedRegistryPopup } from "./ClosedRegistryPopup";
import { SortableTh } from "./SortableTh";
import { useSortableRows } from "../hooks/useSortableRows";
import { useManagementStore } from "../store/useManagementStore";
import type { ProjectSendStatusRow } from "../store/useManagementStore";

async function markAsSent(projectId: string, month: string): Promise<void> {
  const res = await fetch("/management/kpis/samples", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId, month, billed_hours: 0, business_days: 0 }),
  });
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
}

async function unmarkSent(sampleId: string): Promise<void> {
  const res = await fetch(`/management/kpis/samples/${sampleId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
}

type SendStatusTab = "all" | "sent" | "partial" | "none" | "closed";

/** "Relatórios enviados": status de envio por (projeto, mês) nos meses em
 * `displayMonths`, com marcação manual e o popup de "Fechados". Marcar ou
 * desmarcar "Enviado" cria/apaga uma amostra manual (0h/0 dias), por isso
 * `onChanged` — quem lista amostras (o Diagnóstico) precisa recarregar. */
export function SendStatusCard({
  displayMonths,
  loading,
  onChanged,
}: {
  displayMonths: Set<string>;
  loading: boolean;
  onChanged?: () => void;
}) {
  const projectSendStatus = useManagementStore((s) => s.projectSendStatus);
  const load = useManagementStore((s) => s.load);

  const [sendStatusSearch, setSendStatusSearch] = useState("");
  const [sendStatusTab, setSendStatusTab] = useState<SendStatusTab>("all");
  const [expandedSendStatusRow, setExpandedSendStatusRow] = useState<string | null>(null);
  const [showClosedRegistry, setShowClosedRegistry] = useState(false);
  const [sendStatusActionError, setSendStatusActionError] = useState("");

  const handleMarkAsSent = async (projectId: string, month: string) => {
    setSendStatusActionError("");
    try {
      await markAsSent(projectId, month);
      await load(true, true);
      onChanged?.();
    } catch {
      setSendStatusActionError("Não consegui marcar como enviado. Tenta de novo em instantes.");
    }
  };

  const handleUnmarkSent = async (sampleId: string) => {
    setSendStatusActionError("");
    try {
      await unmarkSent(sampleId);
      await load(true, true);
      onChanged?.();
    } catch {
      setSendStatusActionError("Não consegui desmarcar. Tenta de novo em instantes.");
    }
  };

  const sendStatusSearchNormalized = sendStatusSearch.trim().toLowerCase();
  const sendStatusRowsInPeriod = projectSendStatus
    .filter((r) => displayMonths.has(r.month))
    .filter((r) =>
      !sendStatusSearchNormalized ||
      r.client.toLowerCase().includes(sendStatusSearchNormalized) ||
      r.project_name.toLowerCase().includes(sendStatusSearchNormalized) ||
      r.month.includes(sendStatusSearchNormalized)
    )
    .sort((a, b) => a.client.localeCompare(b.client) || a.project_name.localeCompare(b.project_name) || b.month.localeCompare(a.month));
  const sendStatusSentCount = sendStatusRowsInPeriod.filter((r) => r.status === "sent").length;
  const sendStatusPartialCount = sendStatusRowsInPeriod.filter((r) => r.status === "partial").length;
  const sendStatusNoneCount = sendStatusRowsInPeriod.filter((r) => r.status === "none").length;
  const sendStatusClosedCount = sendStatusRowsInPeriod.filter((r) => r.status === "closed").length;
  const sendStatusRows = sendStatusRowsInPeriod.filter((r) => (sendStatusTab === "all" ? true : r.status === sendStatusTab));

  const sendStatusSort = useSortableRows<ProjectSendStatusRow>(sendStatusRows, (r, key) => {
    if (key === "client") return r.client;
    if (key === "project") return r.project_name;
    if (key === "month") return r.month;
    return r.status;
  });

  return (
    <div className="card send-status-card">
      <div className="send-status-card-toolbar">
        <button type="button" className="btn-secondary" onClick={() => setShowClosedRegistry(true)}>
          <Lock size={14} strokeWidth={2} /> Fechados
        </button>
      </div>
      <div className="kpi-card-head">
        <MailSearch size={18} strokeWidth={1.8} />
        <div>
          <h3>Relatórios enviados</h3>
          <p className="muted">Marcado automaticamente quando o e-mail do relatório chega</p>
        </div>
      </div>
      {sendStatusActionError && <p className="error-text">{sendStatusActionError}</p>}
      <div className="send-status-tabs">
        <button type="button" className={sendStatusTab === "all" ? "active" : ""} onClick={() => setSendStatusTab("all")}>
          Todos <span className="send-status-tab-count">{sendStatusRowsInPeriod.length}</span>
        </button>
        <button type="button" className={sendStatusTab === "sent" ? "active" : ""} onClick={() => setSendStatusTab("sent")}>
          Enviados <span className="send-status-tab-count">{sendStatusSentCount}</span>
        </button>
        <button type="button" className={sendStatusTab === "partial" ? "active" : ""} onClick={() => setSendStatusTab("partial")}>
          Enviados parcialmente <span className="send-status-tab-count">{sendStatusPartialCount}</span>
        </button>
        <button type="button" className={sendStatusTab === "none" ? "active" : ""} onClick={() => setSendStatusTab("none")}>
          Não enviados <span className="send-status-tab-count">{sendStatusNoneCount}</span>
        </button>
        <button type="button" className={sendStatusTab === "closed" ? "active" : ""} onClick={() => setSendStatusTab("closed")}>
          Fechados <span className="send-status-tab-count">{sendStatusClosedCount}</span>
        </button>
      </div>
      <div className="send-status-search">
        <MailSearch size={14} strokeWidth={2} />
        <input
          type="text"
          placeholder="Buscar por cliente, projeto ou competência..."
          value={sendStatusSearch}
          onChange={(e) => setSendStatusSearch(e.target.value)}
        />
        {sendStatusSearch && (
          <button type="button" className="send-status-search-clear" onClick={() => setSendStatusSearch("")} aria-label="Limpar busca">
            ×
          </button>
        )}
      </div>
      <div className="kpi-table-wrap send-status-table-wrap">
        <table className="kpi-table">
          <thead>
            <tr>
              <SortableTh sortKey="client" activeKey={sendStatusSort.sortKey} direction={sendStatusSort.direction} onSort={sendStatusSort.toggleSort}>Cliente</SortableTh>
              <SortableTh sortKey="project" activeKey={sendStatusSort.sortKey} direction={sendStatusSort.direction} onSort={sendStatusSort.toggleSort}>Projeto</SortableTh>
              <SortableTh sortKey="month" activeKey={sendStatusSort.sortKey} direction={sendStatusSort.direction} onSort={sendStatusSort.toggleSort}>Competência</SortableTh>
              <SortableTh sortKey="status" activeKey={sendStatusSort.sortKey} direction={sendStatusSort.direction} onSort={sendStatusSort.toggleSort}>Enviado</SortableTh>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={4} className="muted">Carregando...</td>
              </tr>
            )}
            {!loading && sendStatusRows.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  {sendStatusSearchNormalized
                    ? "Nenhum resultado pra essa busca."
                    : sendStatusTab === "sent"
                      ? "Nenhum relatório enviado ainda no período selecionado."
                      : sendStatusTab === "partial"
                        ? "Nenhum relatório parcialmente enviado no período selecionado."
                        : sendStatusTab === "none"
                          ? "Todos os relatórios do período já foram enviados."
                          : sendStatusTab === "closed"
                            ? "Nenhum cliente/projeto fechado no período selecionado."
                            : "Nenhum projeto com horas no período selecionado."}
                </td>
              </tr>
            )}
            {!loading && sendStatusSort.sortedRows.map((r) => {
              const rowKey = `${r.project_id}-${r.month}`;
              const isExpanded = expandedSendStatusRow === rowKey;
              return (
                <Fragment key={rowKey}>
                  <tr>
                    <td>{r.client}</td>
                    <td>{r.project_name}</td>
                    <td>{r.month}</td>
                    <td>
                      {r.status === "closed" ? (
                        <span
                          className="send-status-badge closed"
                          role="img"
                          aria-label="Cliente/projeto fechado"
                          title="Fechado — não precisa de relatório por e-mail (ver botão Fechados)"
                        >
                          <Lock size={12} strokeWidth={2.5} />
                        </span>
                      ) : r.status === "partial" ? (
                        <button
                          type="button"
                          className="send-status-badge-btn"
                          aria-expanded={isExpanded}
                          onClick={() => setExpandedSendStatusRow(isExpanded ? null : rowKey)}
                        >
                          <span
                            className={`send-status-badge ${r.status}`}
                            title={`Faltam: ${(r.missing_pacotes ?? []).join(", ")}`}
                          >
                            <Minus size={14} strokeWidth={3} />
                          </span>
                        </button>
                      ) : r.status === "sent" && r.manual_send_marker_id && r.manual_send_marker_removable ? (
                        <button
                          type="button"
                          className="send-status-badge-btn"
                          onClick={() => handleUnmarkSent(r.manual_send_marker_id!)}
                        >
                          <span
                            className="send-status-badge sent manual"
                            title="Marcado manualmente como enviado — clique pra desmarcar"
                          >
                            <Check size={14} strokeWidth={3} />
                          </span>
                        </button>
                      ) : r.status === "sent" ? (
                        <span
                          className="send-status-badge sent"
                          role="img"
                          aria-label="Relatório enviado"
                          title="Todos os pacotes de trabalho com hora no mês foram recebidos por e-mail"
                        >
                          <Check size={14} strokeWidth={3} />
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="send-status-badge-btn"
                          onClick={() => handleMarkAsSent(r.project_id, r.month)}
                        >
                          <span className="send-status-badge none" title="Clique pra marcar como enviado manualmente" />
                        </button>
                      )}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="send-status-missing-row">
                      <td colSpan={4}>
                        <div className="send-status-missing-panel">
                          <span className="send-status-missing-label">Pacotes faltando neste mês:</span>
                          <ul>
                            {(r.missing_pacotes ?? []).map((pacote) => (
                              <li key={pacote}>{pacote}</li>
                            ))}
                          </ul>
                          <button
                            type="button"
                            className="btn-secondary send-status-force-sent-btn"
                            onClick={() => handleMarkAsSent(r.project_id, r.month)}
                          >
                            Marcar como enviado mesmo assim
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {showClosedRegistry && <ClosedRegistryPopup onClose={() => setShowClosedRegistry(false)} />}
    </div>
  );
}
