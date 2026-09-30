import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Copy, FileText, RefreshCw, X } from "lucide-react";
import { useModal } from "../hooks/useModal";
import { Select } from "./Select";
import { ErrorState, LoadingState } from "./PageStates";
import { toast } from "../store/useToastStore";
import { fmtNum } from "../utils/fmt";
import { fetchExecutiveSummary, paragraphs, sourceLabel, type ExecutiveSummary } from "../utils/executiveSummary";

function fmtOrDash(value: number | null, unit: string): string {
  return value === null ? "—" : `${fmtNum(value)}${unit}`;
}

/** "Resumo do mês": os números do Painel em texto de gerência, pra copiar e colar. Os números vêm sempre do
 * cálculo do Painel; o texto é do Claude (com todo número conferido) ou automático — a tela diz qual. */
export function ExecutiveSummaryModal({
  months,
  initialMonth,
  onClose,
}: {
  /** Competências disponíveis (AAAA-MM), da mais nova pra mais antiga. */
  months: string[];
  initialMonth: string;
  onClose: () => void;
}) {
  const modalRef = useModal({ onClose });
  const [month, setMonth] = useState(initialMonth);
  const [useAi, setUseAi] = useState(true);
  const [summary, setSummary] = useState<ExecutiveSummary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async (targetMonth: string, ai: boolean) => {
    const request = ++latest.current;
    setLoading(true);
    setError("");
    try {
      const result = await fetchExecutiveSummary(targetMonth, ai);
      if (request === latest.current) setSummary(result);
    } catch (e) {
      if (request !== latest.current) return; // uma escolha mais nova já está a caminho
      setSummary(null);
      setError(e instanceof Error ? e.message : "Não consegui gerar o resumo.");
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(month, useAi);
  }, [month, useAi, load]);

  const copy = async () => {
    if (!summary) return;
    try {
      await navigator.clipboard.writeText(summary.text);
      toast.success("Resumo copiado.");
    } catch {
      toast.error("Não consegui copiar. Selecione o texto e use Ctrl+C.");
    }
  };

  const facts = summary?.facts;
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={modalRef}
        tabIndex={-1}
        className="modal-card exec-summary-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="exec-summary-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="exec-summary-title">
            <FileText size={17} strokeWidth={2} aria-hidden="true" /> Resumo do mês
          </h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar">
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <div className="exec-summary-controls">
          <label>
            Competência
            <Select
              ariaLabel="Competência do resumo"
              value={month}
              options={months.map((m) => ({ value: m, label: m }))}
              onChange={setMonth}
            />
          </label>
          <label className="auto-schedule-toggle">
            <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
            <span>Redigir com IA</span>
          </label>
          <button type="button" className="btn-secondary" onClick={() => void load(month, useAi)} disabled={loading}>
            <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} /> Gerar de novo
          </button>
        </div>

        {loading && !summary && <LoadingState label="Gerando o resumo..." rows={4} />}
        {error && <ErrorState message={error} onRetry={() => void load(month, useAi)} busy={loading} />}

        {summary && facts && (
          <div className={loading ? "exec-summary-body is-stale" : "exec-summary-body"} aria-busy={loading}>
            {paragraphs(summary.text).map((p) => (
              <p key={p}>{p}</p>
            ))}
            <p className="muted exec-summary-source">
              {sourceLabel(summary.source)} {summary.ai_note}
            </p>
            <dl className="exec-summary-facts">
              <div>
                <dt>Horas trabalhadas</dt>
                <dd>{fmtOrDash(facts.worked_hours, " h")}</dd>
              </div>
              <div>
                <dt>Horas faturadas</dt>
                <dd>{fmtOrDash(facts.billed_hours, " h")}</dd>
              </div>
              <div>
                <dt>Performance</dt>
                <dd>{fmtOrDash(facts.performance_pct, "%")}</dd>
              </div>
              <div>
                <dt>Não faturável</dt>
                <dd>{fmtOrDash(facts.nonbillable_pct, "%")}</dd>
              </div>
              <div>
                <dt>Enviados</dt>
                <dd>
                  {facts.send.sent} de {facts.send.total - facts.send.closed}
                </dd>
              </div>
            </dl>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Fechar
          </button>
          <button type="button" className="primary" onClick={() => void copy()} disabled={!summary || loading}>
            <Copy size={14} strokeWidth={2} /> Copiar texto
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
