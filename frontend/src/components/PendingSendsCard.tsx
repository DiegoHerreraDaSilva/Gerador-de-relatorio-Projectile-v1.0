import { useMemo, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";
import { useManagementStore } from "../store/useManagementStore";
import { EmptyState } from "./PageStates";
import { LATE_AFTER_DAYS, summarizePending } from "../utils/pendingSends";

const VISIBLE_CLIENTS = 6;

function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return `${m}/${year}`;
}

/** "Pendências de envio": o que já fechou e ainda não foi mandado ao cliente, agrupado por cliente, o mais
 * atrasado primeiro — a lista de quem cobrar. Usa os mesmos dados e os mesmos meses filtrados do card de
 * "Relatórios enviados" logo abaixo. */
export function PendingSendsCard({ displayMonths, loading }: { displayMonths: Set<string>; loading: boolean }) {
  const rows = useManagementStore((s) => s.projectSendStatus);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const summary = useMemo(() => summarizePending(rows, displayMonths), [rows, displayMonths]);

  if (loading) return null;
  const shown = showAll ? summary.clients : summary.clients.slice(0, VISIBLE_CLIENTS);

  return (
    <section className="card pending-sends-card" aria-label="Pendências de envio">
      <div className="kpi-card-head">
        <h3>Pendências de envio</h3>
        {summary.total > 0 && (
          <p className="pending-sends-summary">
            <strong>{summary.total}</strong> {summary.total === 1 ? "relatório" : "relatórios"} de{" "}
            <strong>{summary.clients.length}</strong> {summary.clients.length === 1 ? "cliente" : "clientes"} sem envio
            {summary.late > 0 && (
              <>
                {" "}
                ·{" "}
                <span className="pending-late">
                  {summary.late} atrasado(s) há mais de {LATE_AFTER_DAYS} dias
                </span>
              </>
            )}
          </p>
        )}
      </div>
      {summary.total === 0 ? (
        <EmptyState
          icon={<CheckCircle2 size={22} strokeWidth={1.6} />}
          title="Nenhuma pendência nos meses filtrados"
          description="Tudo o que já fechou foi enviado, ou está marcado como fechado."
        />
      ) : (
        <ul className="pending-sends-list">
          {shown.map((client) => {
            const open = expanded === client.client;
            return (
              <li key={client.client}>
                <button
                  type="button"
                  className="pending-sends-row"
                  aria-expanded={open}
                  onClick={() => setExpanded(open ? null : client.client)}
                >
                  {open ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}
                  <span className="pending-sends-client">{client.client}</span>
                  <span className="pending-sends-count">
                    {client.items.length} {client.items.length === 1 ? "projeto" : "projetos"}
                  </span>
                  <span className={`pending-sends-age ${client.lateCount > 0 ? "late" : ""}`}>
                    há {client.oldestDays} {client.oldestDays === 1 ? "dia" : "dias"}
                  </span>
                </button>
                {open && (
                  <ul className="pending-sends-projects">
                    {client.items.map((item) => (
                      <li key={`${item.project_id}:${item.month}`}>
                        <span className="pending-sends-project">{item.project_name}</span>
                        <span className="muted">{monthLabel(item.month)}</span>
                        <span className="muted">
                          {item.status === "partial"
                            ? `faltam ${item.missing_pacotes.length} pacote(s)`
                            : "nada enviado"}
                        </span>
                        <span className={`pending-sends-age ${item.late ? "late" : ""}`}>há {item.daysLate} d</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {summary.clients.length > VISIBLE_CLIENTS && (
        <button type="button" className="auto-link-button" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Mostrar menos" : `Ver todos os ${summary.clients.length} clientes`}
        </button>
      )}
    </section>
  );
}
