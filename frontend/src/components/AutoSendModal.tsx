import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Check, Paperclip, Send, X } from "lucide-react";
import { useAutoGenerationStore, type AutoItem, type SendDefaults } from "../store/useAutoGenerationStore";
import { FormatCheckboxes, type ReportFormat } from "./FormatCheckboxes";
import { competenceLabel } from "./AutoGenerationPanel";

const extensionOf = (name: string) => name.split(".").pop()?.toLowerCase() ?? "";

/** Formatos que existem entre os arquivos aprovados ("x.xlsx", "x.pdf"). */
export function approvedFormats(files: string[]): Set<ReportFormat> {
  const out = new Set<ReportFormat>();
  for (const name of files) {
    const ext = extensionOf(name);
    if (ext === "xlsx" || ext === "pdf") out.add(ext);
  }
  return out;
}

/** "a@x.com; b@y.com, c@z.com" → lista (o backend confere cada um). */
export function parseAddresses(text: string): string[] {
  return text.split(/[;,\s]+/).map((a) => a.trim()).filter(Boolean);
}

/** Envio ao cliente de um relatório APROVADO: os anexos são os arquivos
 * congelados na aprovação e o e-mail sai da caixa de quem está logado. */
export function AutoSendModal({ item, onClose }: { item: AutoItem; onClose: () => void }) {
  const loadSendDefaults = useAutoGenerationStore((s) => s.loadSendDefaults);
  const sendReport = useAutoGenerationStore((s) => s.sendReport);
  const [defaults, setDefaults] = useState<SendDefaults | null>(null);
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [formats, setFormats] = useState<Set<ReportFormat>>(() => new Set());

  useEffect(() => {
    loadSendDefaults(item.id)
      .then((d) => {
        setDefaults(d);
        setFormats(approvedFormats(d.files));
        setTo(d.to.join("; "));
        setCc(d.cc.join("; "));
        setSubject(d.subject);
        setMessage(d.message);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !sending) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [sending, onClose]);

  const send = async () => {
    const toList = parseAddresses(to);
    if (!toList.length) return setError("Informe pelo menos um destinatário.");
    if (!subject.trim()) return setError("Informe o assunto.");
    setSending(true);
    setError("");
    try {
      await sendReport(item, { to: toList, cc: parseAddresses(cc), subject: subject.trim(), message, formats: Array.from(formats) });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSending(false);
    }
  };

  return createPortal(
    <div className="modal-backdrop" onClick={() => !sending && onClose()}>
      <div className="modal-card auto-send-modal" role="dialog" aria-modal="true" aria-labelledby="auto-send-title" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2 id="auto-send-title">Enviar ao cliente</h2>
          <button type="button" className="modal-close" onClick={onClose} disabled={sending} aria-label="Fechar"><X size={18} strokeWidth={2} /></button>
        </div>
        <div className="modal-body auto-send-body">
          <p className="muted">{item.project_name}{item.status === "enviado" ? " · já enviado antes — este é um novo envio" : ""}</p>
          {!defaults && !error && <p className="muted">Carregando...</p>}
          {defaults && (
            <>
              <label className="auto-send-field">Para
                <input type="text" value={to} onChange={(e) => setTo(e.target.value)} placeholder="cliente@empresa.com; outro@empresa.com" autoFocus />
              </label>
              <label className="auto-send-field">Cópia
                <input type="text" value={cc} onChange={(e) => setCc(e.target.value)} placeholder="Opcional" />
              </label>
              <label className="auto-send-field">Assunto
                <input type="text" value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} />
              </label>
              <label className="auto-send-field">Mensagem
                <textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={5000} />
              </label>
              <div className="auto-send-files">
                <span className="auto-numbers-label">Anexos (dos arquivos aprovados)</span>
                <FormatCheckboxes value={formats} onChange={setFormats} available={approvedFormats(defaults.files)} disabled={sending} />
                <ul>
                  {defaults.files.filter((name) => formats.has(extensionOf(name) as ReportFormat)).map((name) => (
                    <li key={name}><Paperclip size={13} strokeWidth={2} aria-hidden="true" /> {name}</li>
                  ))}
                </ul>
              </div>
              <p className="muted auto-send-sender">
                Sai da sua caixa ({defaults.sender || "sem e-mail cadastrado"}), com a caixa da automação em cópia.
                Os destinatários ficam guardados pro próximo mês deste projeto.
              </p>
              {!defaults.counts_in_diagnostics && (
                <p className="auto-review-note auto-review-note-returned">
                  <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
                  <span>Seu e-mail não está em <code>ALBERTO_EMAIL</code>: este envio não vai aparecer como “Enviado” no Diagnóstico.</span>
                </p>
              )}
            </>
          )}
          {error && <p className="error-text" role="alert">{error}</p>}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={sending}>Cancelar</button>
          <button type="button" className="primary" onClick={() => void send()} disabled={!defaults || sending}>
            <Send size={14} strokeWidth={2} /> {sending ? "Enviando…" : "Enviar"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

type BulkRow = {
  item: AutoItem;
  defaults: SendDefaults | null;
  to: string;
  cc: string;
  state: "loading" | "ready" | "sending" | "sent" | "error";
  error?: string;
};

/** Envio em lote: um e-mail por relatório (cada projeto tem o seu cliente),
 * com os destinatários do último envio de cada um e o assunto/mensagem
 * padrão. Um que falha não para os outros. */
export function BulkSendModal({ items, onClose }: { items: AutoItem[]; onClose: () => void }) {
  const loadSendDefaults = useAutoGenerationStore((s) => s.loadSendDefaults);
  const sendReport = useAutoGenerationStore((s) => s.sendReport);
  const sendCombined = useAutoGenerationStore((s) => s.sendCombined);
  // "separate" = um e-mail por projeto; "combined" = todos num e-mail só
  const [mode, setMode] = useState<"separate" | "combined">("separate");
  const [combined, setCombined] = useState({ to: "", cc: "", subject: "", message: "", touched: false });
  const [combinedError, setCombinedError] = useState("");
  const [combinedSent, setCombinedSent] = useState(false);
  const [rows, setRows] = useState<BulkRow[]>(() => items.map((item) => ({ item, defaults: null, to: "", cc: "", state: "loading" })));
  const [running, setRunning] = useState(false);
  const [finished, setFinished] = useState(false);
  const [formats, setFormats] = useState<Set<ReportFormat>>(() => new Set(["xlsx", "pdf"]));

  const patch = (id: string, change: Partial<BulkRow>) =>
    setRows((prev) => prev.map((r) => (r.item.id === id ? { ...r, ...change } : r)));

  useEffect(() => {
    for (const item of items) {
      loadSendDefaults(item.id)
        .then((d) => patch(item.id, { defaults: d, to: d.to.join("; "), cc: d.cc.join("; "), state: "ready" }))
        .catch((e) => patch(item.id, { state: "error", error: e instanceof Error ? e.message : String(e) }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !running) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [running, onClose]);

  const sendAll = async () => {
    setRunning(true);
    for (const row of rows) {
      if (row.state !== "ready" && row.state !== "error") continue;
      if (!row.defaults) continue;
      const to = parseAddresses(row.to);
      if (!to.length) {
        patch(row.item.id, { state: "error", error: "Sem destinatário." });
        continue;
      }
      patch(row.item.id, { state: "sending", error: undefined });
      try {
        await sendReport(row.item, {
          to, cc: parseAddresses(row.cc), subject: row.defaults.subject, message: row.defaults.message, formats: Array.from(formats),
        });
        patch(row.item.id, { state: "sent" });
      } catch (e) {
        patch(row.item.id, { state: "error", error: e instanceof Error ? e.message : String(e) });
      }
    }
    setRunning(false);
    setFinished(true);
  };

  const sendAllTogether = async () => {
    const to = parseAddresses(combined.to);
    if (!to.length) return setCombinedError("Informe pelo menos um destinatário.");
    if (!combined.subject.trim()) return setCombinedError("Informe o assunto.");
    setRunning(true);
    setCombinedError("");
    try {
      await sendCombined(items, {
        to, cc: parseAddresses(combined.cc), subject: combined.subject.trim(), message: combined.message,
        formats: Array.from(formats),
      });
      setCombinedSent(true);
      setFinished(true);
    } catch (e) {
      setCombinedError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const first = rows.find((r) => r.defaults)?.defaults;
  const loading = rows.some((r) => r.state === "loading");
  useEffect(() => {
    if (loading || combined.touched) return;
    const join = (lists: string[][]) => {
      const seen = new Map<string, string>();
      for (const a of lists.flat()) if (!seen.has(a.toLowerCase())) seen.set(a.toLowerCase(), a);
      return Array.from(seen.values());
    };
    const to = join(rows.map((r) => r.defaults?.to ?? []));
    const cc = join(rows.map((r) => r.defaults?.cc ?? [])).filter((a) => !to.some((t) => t.toLowerCase() === a.toLowerCase()));
    const months = Array.from(new Set(items.map((i) => competenceLabel(i.competence))));
    const month = months.join(", ");
    setCombined({
      to: to.join("; "), cc: cc.join("; "), touched: false,
      subject: `Relatórios de Horas - ${month}`,
      message: `Seguem em anexo os relatórios de horas referentes a ${month}:\n${items.map((i) => `- ${i.project_name}`).join("\n")}`,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);
  const setCombinedField = (field: "to" | "cc" | "subject" | "message", value: string) =>
    setCombined((c) => ({ ...c, [field]: value, touched: true }));
  const combinedFiles = rows.flatMap((r) => (r.defaults?.files ?? []).filter((n) => formats.has(extensionOf(n) as ReportFormat)));
  const pending = rows.filter((r) => r.state === "ready" || (r.state === "error" && r.defaults)).length;
  const sentCount = rows.filter((r) => r.state === "sent").length;

  return createPortal(
    <div className="modal-backdrop" onClick={() => !running && onClose()}>
      <div className="modal-card auto-send-modal auto-bulk-send-modal" role="dialog" aria-modal="true" aria-labelledby="auto-bulk-send-title" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2 id="auto-bulk-send-title">Enviar {items.length} relatório{items.length === 1 ? "" : "s"} ao cliente</h2>
          <button type="button" className="modal-close" onClick={onClose} disabled={running} aria-label="Fechar"><X size={18} strokeWidth={2} /></button>
        </div>
        <div className="modal-body auto-send-body">
          {items.length > 1 && (
            <div className="auto-send-mode" role="group" aria-label="Como enviar">
              <button type="button" aria-pressed={mode === "separate"} onClick={() => setMode("separate")} disabled={running || finished}>
                Um e-mail por projeto
                <span>Cada um com os seus destinatários e o assunto padrão</span>
              </button>
              <button type="button" aria-pressed={mode === "combined"} onClick={() => setMode("combined")} disabled={running || finished}>
                Todos num e-mail só
                <span>Os {items.length} relatórios como anexos da mesma mensagem</span>
              </button>
            </div>
          )}
          <p className="muted">
            {mode === "separate"
              ? "Os destinatários vêm do último envio de cada projeto — confira antes de enviar."
              : "Os destinatários juntam os do último envio de cada projeto — confira antes de enviar."}
          </p>
          <div className="auto-send-files">
            <span className="auto-numbers-label">
              {mode === "separate"
                ? "Anexos — vale pra todos (projeto sem o formato escolhido aprovado mostra erro na linha dele)"
                : "Anexos"}
            </span>
            <FormatCheckboxes value={formats} onChange={setFormats} disabled={running} />
          </div>
          {mode === "combined" && (
            <div className="auto-send-combined">
              <ul className="auto-send-files-list">
                {combinedFiles.map((name) => <li key={name}><Paperclip size={13} strokeWidth={2} aria-hidden="true" /> {name}</li>)}
              </ul>
              {combinedSent ? (
                <p className="auto-bulk-row-ok" role="status"><Check size={14} strokeWidth={2.4} /> Enviado num e-mail só.</p>
              ) : (
                <>
                  <div className="auto-bulk-row-fields">
                    <label className="auto-send-field">Para
                      <input type="text" value={combined.to} disabled={running} placeholder="cliente@empresa.com"
                        onChange={(e) => setCombinedField("to", e.target.value)} />
                    </label>
                    <label className="auto-send-field">Cópia
                      <input type="text" value={combined.cc} disabled={running} placeholder="Opcional"
                        onChange={(e) => setCombinedField("cc", e.target.value)} />
                    </label>
                  </div>
                  <label className="auto-send-field">Assunto
                    <input type="text" value={combined.subject} maxLength={200} disabled={running}
                      onChange={(e) => setCombinedField("subject", e.target.value)} />
                  </label>
                  <label className="auto-send-field">Mensagem
                    <textarea rows={5} value={combined.message} maxLength={5000} disabled={running}
                      onChange={(e) => setCombinedField("message", e.target.value)} />
                  </label>
                </>
              )}
              {combinedError && <p className="error-text" role="alert">{combinedError}</p>}
            </div>
          )}
          {mode === "separate" && <ul className="auto-bulk-rows">
            {rows.map((row) => (
              <li key={row.item.id} className={`auto-bulk-row auto-bulk-row-${row.state}`}>
                <div className="auto-bulk-row-head">
                  <strong title={row.item.project_name}>{row.item.project_name}</strong>
                  {row.state === "sent" && <span className="auto-bulk-row-ok"><Check size={14} strokeWidth={2.4} /> Enviado</span>}
                  {row.state === "sending" && <span className="muted">Enviando…</span>}
                  {row.state === "loading" && <span className="muted">Carregando…</span>}
                </div>
                {row.defaults && row.state !== "sent" && (
                  <div className="auto-bulk-row-fields">
                    <label className="auto-send-field">Para
                      <input type="text" value={row.to} disabled={running} placeholder="cliente@empresa.com"
                        onChange={(e) => patch(row.item.id, { to: e.target.value })} />
                    </label>
                    <label className="auto-send-field">Cópia
                      <input type="text" value={row.cc} disabled={running} placeholder="Opcional"
                        onChange={(e) => patch(row.item.id, { cc: e.target.value })} />
                    </label>
                  </div>
                )}
                {row.error && <p className="error-text" role="alert">{row.error}</p>}
              </li>
            ))}
          </ul>}
          {first && (
            <p className="muted auto-send-sender">Sai da sua caixa ({first.sender || "sem e-mail cadastrado"}), com a caixa da automação em cópia.</p>
          )}
          {first && !first.counts_in_diagnostics && (
            <p className="auto-review-note auto-review-note-returned">
              <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
              <span>Seu e-mail não está em <code>ALBERTO_EMAIL</code>: estes envios não vão aparecer como “Enviado” no Diagnóstico.</span>
            </p>
          )}
          {finished && mode === "separate" && <p className="muted" role="status">{sentCount} de {items.length} enviado{sentCount === 1 ? "" : "s"}.</p>}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={running}>{finished ? "Fechar" : "Cancelar"}</button>
          {mode === "separate" ? (
            <button type="button" className="primary" onClick={() => void sendAll()} disabled={running || loading || pending === 0}>
              <Send size={14} strokeWidth={2} /> {running ? "Enviando…" : finished && pending ? `Tentar de novo (${pending})` : `Enviar ${pending}`}
            </button>
          ) : (
            <button type="button" className="primary" onClick={() => void sendAllTogether()} disabled={running || loading || combinedSent}>
              <Send size={14} strokeWidth={2} /> {running ? "Enviando…" : "Enviar num e-mail só"}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
