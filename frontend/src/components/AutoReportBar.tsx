import { useState } from "react";
import { CalendarClock, Check, ClipboardCheck, CloudOff, Download, Loader2, RefreshCw, Send, Undo2, UserRound } from "lucide-react";
import { useReportStore } from "../store/useReportStore";
import { useReportTabsStore } from "../store/useReportTabsStore";
import { canEditAutoTab, errorList, useAutoGenerationStore, type AutoStatus } from "../store/useAutoGenerationStore";
import { findEmptyActivityDescriptionMessage } from "../utils/calc";
import { FormatCheckboxes, type ReportFormat } from "./FormatCheckboxes";
import { StatusPill, competenceLabel } from "./AutoGenerationPanel";

const SAVE_TEXT = {
  saved: "Salvo no servidor",
  dirty: "Alterações ainda não salvas no servidor",
  saving: "Salvando no servidor…",
  conflict: "Este rascunho mudou em outro lugar",
  error: "Não consegui salvar no servidor — tento de novo na próxima alteração",
} as const;

type Messages = { kind: "error" | "ok" | "warn"; items: string[] } | null;

/** Barra da guia aberta pela geração automática: no lugar do rodapé de
 * gerar/enviar. Gerente APROVA (grava no histórico e congela o que vai pro
 * cliente) ou devolve ao revisor; o revisor manda pra aprovação. O rascunho
 * é salvo sozinho no servidor. */
export function AutoReportBar() {
  const tab = useReportTabsStore((s) => s.tabs.find((t) => t.id === s.activeTabId));
  const auto = tab?.auto;
  const saveState = useAutoGenerationStore((s) => (auto ? s.saveState[auto.reportId] ?? "saved" : "saved"));
  const packages = useReportStore((s) => s.packages);
  const header = useReportStore((s) => s.header);
  const [messages, setMessages] = useState<Messages>(null);
  const [working, setWorking] = useState(false);
  const [note, setNote] = useState("");
  const [showReturn, setShowReturn] = useState(false);

  if (!auto) return null;
  const status = auto.status as AutoStatus;
  const reviewer = auto.role === "reviewer";
  const editable = canEditAutoTab(auto);
  const formats = new Set<ReportFormat>(auto.formats);

  const setFormats = (next: Set<ReportFormat>) => {
    useReportTabsStore.getState().updateAutoMeta(auto.reportId, { formats: Array.from(next) });
    // formatos fazem parte do rascunho: salva junto
    useAutoGenerationStore.setState((s) => ({ saveState: { ...s.saveState, [auto.reportId]: "dirty" } }));
    void useAutoGenerationStore.getState().flushSave(auto.reportId);
  };

  const reload = async () => {
    if (tab) useReportTabsStore.getState().closeTab(tab.id);
    useAutoGenerationStore.setState((s) => ({ saveState: { ...s.saveState, [auto.reportId]: "saved" } }));
    await useAutoGenerationStore.getState().openInEditor(auto.reportId, auto.role ?? "manager");
  };

  const run = async (fn: () => Promise<Messages>) => {
    setMessages(null);
    setWorking(true);
    try {
      setMessages(await fn());
    } catch (e) {
      setMessages({ kind: "error", items: errorList(e) });
    } finally {
      setWorking(false);
    }
  };

  const approve = () => {
    const missing = packages.filter((p) => !p.projectCode.trim()).map((p) => `Falta o número do relatório de "${p.projectName}".`);
    if (!header.signer1Name.trim() || !header.signer2Name.trim()) missing.push("Preencha o nome de quem assina (Schwaben e cliente).");
    const emptyDesc = findEmptyActivityDescriptionMessage(packages, "aprovar");
    if (emptyDesc) missing.push(emptyDesc);
    if (missing.length) return setMessages({ kind: "error", items: missing });
    void run(async () => {
      const { warnings } = await useAutoGenerationStore.getState().approve(auto.reportId);
      return { kind: warnings.length ? "warn" : "ok", items: ["Aprovado. Os arquivos foram para o histórico e estão prontos para envio.", ...warnings] };
    });
  };

  const submit = () => {
    const emptyDesc = findEmptyActivityDescriptionMessage(packages, "mandar pra aprovação");
    if (emptyDesc) return setMessages({ kind: "error", items: [emptyDesc] });
    void run(async () => {
      await useAutoGenerationStore.getState().submitReview(auto.reportId, note.trim());
      setNote("");
      return { kind: "ok", items: ["Mandado pra aprovação. O gerente vê na aba Geração automática."] };
    });
  };

  const sendBack = () => {
    if (!note.trim()) return setMessages({ kind: "error", items: ["Escreva o que o revisor precisa mudar."] });
    void run(async () => {
      await useAutoGenerationStore.getState().returnToReviewer(auto.reportId, note.trim());
      setNote("");
      setShowReturn(false);
      return { kind: "ok", items: [`Devolvido${auto.reviewerName ? ` pra ${auto.reviewerName}` : ""}.`] };
    });
  };

  return (
    <div className="auto-bar card" role="region" aria-label="Relatório da geração automática">
      <div className="auto-bar-main">
        <span className="auto-bar-kind">
          {reviewer ? <><ClipboardCheck size={16} strokeWidth={2} /> Revisão</> : <><CalendarClock size={16} strokeWidth={2} /> Geração automática</>}
        </span>
        <span className="auto-bar-title">{tab?.label} · {competenceLabel(auto.competence)}</span>
        <StatusPill status={status} />
        {!reviewer && auto.reviewerName && (
          <span className="auto-bar-reviewer"><UserRound size={14} strokeWidth={2} aria-hidden="true" /> {auto.reviewerName}</span>
        )}
        {editable && (
          <span className={`auto-save auto-save-${saveState}`} role="status" aria-live="polite">
            {saveState === "saving" ? <Loader2 size={14} className="spin" /> : saveState === "saved" ? <Check size={14} /> : <CloudOff size={14} />}
            {SAVE_TEXT[saveState]}
          </span>
        )}
      </div>

      {editable && status === "devolvido" && auto.returnComment && (
        <p className="auto-review-note auto-review-note-returned">
          <Undo2 size={14} strokeWidth={2} aria-hidden="true" />
          <span><strong>O gerente pediu:</strong> {auto.returnComment}</span>
        </p>
      )}

      {saveState === "conflict" && (
        <div className="auto-bar-conflict">
          <p>O rascunho foi alterado em outro lugar depois que você abriu. Recarregue pra ver a versão atual — o que você mudou aqui desde o último salvamento se perde.</p>
          <button type="button" className="btn-secondary" onClick={() => void reload()}><RefreshCw size={14} /> Recarregar do servidor</button>
        </div>
      )}

      {reviewer && editable && (
        <div className="auto-bar-actions">
          <input className="auto-bar-note" type="text" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)}
            placeholder="Observação pro gerente (opcional)" aria-label="Observação pro gerente" />
          <button type="button" className="primary" onClick={submit} disabled={working || saveState === "conflict"}>
            <Send size={14} strokeWidth={2} /> {working ? "Mandando…" : "Mandar pra aprovação"}
          </button>
          <p className="muted auto-bar-hint">O número do relatório, os arquivos e a aprovação ficam com o gerente.</p>
        </div>
      )}

      {!reviewer && editable && (
        <div className="auto-bar-actions">
          <FormatCheckboxes value={formats} onChange={setFormats} />
          {status === "revisado" && auto.reviewerName && (
            <button type="button" className="btn-secondary" aria-expanded={showReturn} onClick={() => setShowReturn((v) => !v)} disabled={working}>
              <Undo2 size={14} strokeWidth={2} /> Devolver
            </button>
          )}
          <button type="button" className="primary" onClick={approve} disabled={working || saveState === "conflict"}>
            {working ? "Aprovando…" : "Aprovar"}
          </button>
        </div>
      )}

      {!reviewer && editable && showReturn && (
        <div className="auto-bar-actions">
          <input className="auto-bar-note" type="text" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)}
            placeholder={`O que ${auto.reviewerName ?? "o revisor"} precisa mudar?`} aria-label="O que o revisor precisa mudar" autoFocus />
          <button type="button" className="primary" onClick={sendBack} disabled={working}>
            <Undo2 size={14} strokeWidth={2} /> Devolver ao revisor
          </button>
        </div>
      )}

      {!editable && (
        <div className="auto-bar-actions">
          <p className="muted">
            {reviewer
              ? status === "revisado"
                ? "Mandado pra aprovação — aguardando o gerente. Edições aqui não são salvas."
                : status === "aprovado" || status === "enviado"
                  ? "Aprovado pelo gerente. Edições aqui não são salvas."
                  : "Este relatório não está mais com você; edições aqui não são salvas."
              : status === "aprovado"
                ? "Aprovado — edições aqui não são salvas. Pra mudar, use “Reabrir” na aba Geração automática."
                : "Este relatório não está em revisão; edições aqui não são salvas."}
          </p>
          {!reviewer && status === "aprovado" && (
            <a className="btn-secondary" href={`/auto-generation/reports/${auto.reportId}/files`}>
              <Download size={14} strokeWidth={2} /> Baixar arquivos aprovados
            </a>
          )}
        </div>
      )}

      {messages && (
        <ul className={`auto-bar-messages auto-bar-messages-${messages.kind}`} role="alert">
          {messages.items.map((m) => <li key={m}>{m}</li>)}
        </ul>
      )}
    </div>
  );
}
