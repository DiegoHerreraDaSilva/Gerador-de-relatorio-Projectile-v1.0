import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, MessagesSquare, RotateCcw } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { AnalyticsTableView, KpiGrid, VisualizationRenderer } from "./analytics/VisualizationRenderer";
import { useAnalyticsChatStore, type AnalyticsChatResponse, type KpiVisualization } from "../store/useAnalyticsChatStore";

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

/** Sugestões agrupadas pelo que o chat de fato sabe responder (catálogo em
 * backend/app/analytics/intents.py), com meses reais em vez de fixos. */
function suggestionGroups(today: Date) {
  const current = MONTHS[today.getMonth()];
  const previous = MONTHS[(today.getMonth() + 11) % 12];
  return [
    {
      title: "Horas",
      items: [
        "Quantas horas tivemos por cliente este mês?",
        "Horas de cada colaborador por projeto no mês passado",
        "Horas por cliente mês a mês nos últimos 6 meses",
      ],
    },
    {
      title: "Cruzamentos",
      items: [
        "Colaboradores com menos de 100 h no mês passado",
        "Quanto das horas foi não faturável por colaborador?",
        `Compare as horas por projeto de ${previous} e ${current}`,
      ],
    },
    {
      title: "Faturado e envio",
      items: [
        "Faturado x trabalhado por projeto no mês passado",
        "Performance por mês nos últimos 6 meses",
        "Quais projetos não tiveram relatório enviado no mês passado?",
      ],
    },
  ];
}

const CLASSIFIER_LABEL: Record<string, string> = { jev: "Jev", claude: "Claude" };

function Answer({ response }: { response: AnalyticsChatResponse }) {
  const meta = response.metadata;
  // comparação de períodos: "agosto x setembro" ("até" pareceria um intervalo)
  const period = meta.compared_period_label ? `${meta.compared_period_label} x ${meta.period_label}` : meta.period_label;
  const kpis = response.visualizations.filter((v): v is KpiVisualization => v.type === "kpi");
  const charts = response.visualizations.filter((v) => v.type !== "kpi");
  const single = kpis.length === 1 ? kpis[0] : null;
  return (
    <article className="achat-answer">
      {single && <VisualizationRenderer visualization={single} />}
      {kpis.length > 1 && <KpiGrid items={kpis} />}
      <p className={single ? "achat-reply achat-reply--secondary" : "achat-reply"}>{response.reply}</p>
      {charts.map((v, i) => (
        <VisualizationRenderer key={i} visualization={v} />
      ))}
      {response.tables.map((t, i) => (
        // tabela aberta quando ela É a resposta: sem gráfico, ou curta
        <AnalyticsTableView key={i} table={t} defaultOpen={charts.length === 0 || t.rows.length <= 8} />
      ))}
      {(meta.source_label || period) && (
        <dl className="achat-meta">
          {meta.source_label && (
            <div><dt>Fonte</dt><dd>{meta.source_label}</dd></div>
          )}
          {period && (
            <div><dt>Período</dt><dd>{period}</dd></div>
          )}
          {CLASSIFIER_LABEL[meta.classifier] && (
            <div><dt>Entendido por</dt><dd>{CLASSIFIER_LABEL[meta.classifier]}</dd></div>
          )}
        </dl>
      )}
    </article>
  );
}

function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  // cresce com o texto até ~5 linhas, sem alça de redimensionar
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  }, [value]);

  return (
    <form
      className="achat-composer"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <textarea
        ref={ref}
        rows={1}
        value={value}
        maxLength={1000}
        autoFocus={autoFocus}
        placeholder="Pergunte sobre horas ou relatórios"
        aria-label="Sua pergunta"
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSubmit();
          }
        }}
      />
      <button type="submit" className="achat-send" disabled={disabled || !value.trim()} aria-label="Enviar pergunta">
        <ArrowUp size={18} strokeWidth={2.4} />
      </button>
    </form>
  );
}

/** Chat analítico (só gerente): perguntas em português sobre horas e
 * relatórios gerados. As respostas vêm de consultas fixas no backend
 * (`backend/app/analytics/`) — a IA nunca acessa o banco. Separado do chat
 * de edição do relatório: nada aqui mexe no relatório aberto. */
export function AnalyticsChatPanel() {
  const messages = useAnalyticsChatStore((s) => s.messages);
  const sending = useAnalyticsChatStore((s) => s.sending);
  const send = useAnalyticsChatStore((s) => s.send);
  const reset = useAnalyticsChatStore((s) => s.reset);
  const ensureUser = useAnalyticsChatStore((s) => s.ensureUser);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const empty = messages.length === 0;

  useEffect(() => ensureUser(), [ensureUser]);
  useEffect(() => {
    if (!empty) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, sending, empty]);

  const submit = (text: string) => {
    if (!text.trim() || sending) return;
    setDraft("");
    send(text);
  };

  return (
    <div className="achat-page page-container">
      <PageHeader
        title="Chat analítico"
        description="Respostas calculadas a partir das horas apontadas e dos relatórios gerados."
        icon={<MessagesSquare size={20} strokeWidth={1.8} />}
        actions={
          !empty ? (
            <button type="button" className="btn-secondary" onClick={reset} disabled={sending}>
              <RotateCcw size={14} strokeWidth={2} /> Nova conversa
            </button>
          ) : undefined
        }
      />

      <section className={`achat-shell ${empty ? "is-empty" : ""}`}>
        {empty ? (
          <div className="achat-start">
            <h3 className="achat-start-title">O que você quer saber sobre as horas da equipe?</h3>
            <Composer value={draft} onChange={setDraft} onSubmit={() => submit(draft)} disabled={sending} autoFocus />
            <div className="achat-groups">
              {suggestionGroups(new Date()).map((group) => (
                <div className="achat-group" key={group.title}>
                  <h4>{group.title}</h4>
                  <ul>
                    {group.items.map((item) => (
                      <li key={item}>
                        <button type="button" className="achat-suggestion" onClick={() => submit(item)}>
                          {item}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="achat-thread" aria-live="polite">
              {messages.map((m) =>
                m.role === "user" ? (
                  <p key={m.id} className="achat-question">{m.text}</p>
                ) : m.role === "error" ? (
                  <p key={m.id} className="achat-error" role="alert">{m.text}</p>
                ) : (
                  <Answer key={m.id} response={m.response} />
                )
              )}
              {sending && (
                <div className="achat-pending" role="status">
                  <span className="achat-pending-bar" aria-hidden="true" />
                  Consultando os dados
                </div>
              )}
              <div ref={endRef} />
            </div>
            <div className="achat-dock">
              <Composer value={draft} onChange={setDraft} onSubmit={() => submit(draft)} disabled={sending} autoFocus />
            </div>
          </>
        )}
      </section>
    </div>
  );
}
