import { useEffect, useRef, useState } from "react";
import { MessageSquare, FileText, GripVertical, User, Sparkles, AlertTriangle, Send, X } from "lucide-react";
import { useReportStore } from "../store/useReportStore";

export function Chat() {
  const packages = useReportStore((s) => s.packages);
  const header = useReportStore((s) => s.header);
  const activeId = useReportStore((s) => s.activePackageId);
  const applyChatState = useReportStore((s) => s.applyChatState);
  const pushUndo = useReportStore((s) => s.pushUndo);

  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant" | "error" | "pending"; text: string }>>([]);

  const append = (role: "user" | "assistant" | "error" | "pending", text: string) => {
    setMessages((prev) => [...prev, { role, text }]);
    requestAnimationFrame(() => {
      if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    });
  };

  const buildChatState = () => {
    const activeIndex = packages.findIndex((p) => p.id === activeId);
    return {
      packages: packages.map((pkg) => ({
        key: pkg.key,
        projectCode: pkg.projectCode || "",
        projectName: pkg.projectName || "",
        groups: pkg.groups.map((g) => ({
          name: g.name,
          performance: parseFloat(String(g.performance)) || 0,
          activities: g.activities.map((a) => ({
            description: a.description,
            hours: a.hours === null || a.hours === undefined ? null : parseFloat(String(a.hours)),
          })),
        })),
      })),
      activePackageIndex: activeIndex >= 0 ? activeIndex : 0,
      locationDate: header.locationDate || "",
      monthLabel: header.monthLabel || "",
      signer1Name: header.signer1Name || "",
      signer1Company: header.signer1Company || "",
      signer2Name: header.signer2Name || "",
      signer2Company: header.signer2Company || "",
    };
  };

  const send = async (text: string) => {
    if (!text.trim() || loading || packages.length === 0) return;
    append("user", text);
    append("pending", "Pensando...");
    setLoading(true);
    pushUndo();
    try {
      const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, state: buildChatState() }),
      });
      const data = await res.json().catch(() => null);
      setMessages((prev) => prev.filter((m) => m.role !== "pending"));
      if (!res.ok) {
        const detail = data && (data as any).detail ? (data as any).detail : `Erro ${res.status} ao falar com o assistente.`;
        append("error", detail);
        const state = useReportStore.getState();
        state.undoStack.pop();
        useReportStore.setState({ undoStack: [...state.undoStack] });
        return;
      }
      const ok = applyChatState((data as any).state);
      if (!ok) {
        append("error", "O assistente devolveu uma resposta inesperada. Nada foi alterado.");
        const state = useReportStore.getState();
        state.undoStack.pop();
        useReportStore.setState({ undoStack: [...state.undoStack] });
        return;
      }
      append("assistant", (data as any).reply || "Alterações aplicadas.");
    } catch {
      setMessages((prev) => prev.filter((m) => m.role !== "pending"));
      append("error", "Não foi possível falar com o assistente. Verifique sua conexão e tente de novo.");
      const state = useReportStore.getState();
      state.undoStack.pop();
      useReportStore.setState({ undoStack: [...state.undoStack] });
    } finally {
      setLoading(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  };

  const handleSuggestion = (text: string) => {
    setInput(text);
    textareaRef.current?.focus();
  };

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  };

  useEffect(() => { autoResize(); }, [input]);
  useEffect(() => { if (open) requestAnimationFrame(() => textareaRef.current?.focus()); }, [open]);

  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const headerEl = panel.querySelector<HTMLElement>(".chat-panel-header");
    if (!headerEl) return;
    const pinPosition = () => {
      if (panel.dataset.pinned === "1") return;
      const rect = panel.getBoundingClientRect();
      panel.style.left = `${rect.left}px`;
      panel.style.top = `${rect.top}px`;
      panel.style.bottom = "auto";
      panel.style.width = `${rect.width}px`;
      panel.style.height = `${rect.height}px`;
      panel.dataset.pinned = "1";
    };
    const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));
    const onHeaderDown = (e: MouseEvent) => {
      if ((e.target as HTMLElement).closest(".chat-panel-close")) return;
      e.preventDefault();
      pinPosition();
      panel.classList.add("dragging");
      const startX = e.clientX, startY = e.clientY;
      const startLeft = panel.offsetLeft, startTop = panel.offsetTop;
      const onMove = (ev: MouseEvent) => {
        const rect = panel.getBoundingClientRect();
        const maxLeft = window.innerWidth - rect.width;
        const maxTop = window.innerHeight - rect.height;
        const newLeft = clamp(startLeft + (ev.clientX - startX), 0, Math.max(0, maxLeft));
        const newTop = clamp(startTop + (ev.clientY - startY), 0, Math.max(0, maxTop));
        panel.style.left = `${newLeft}px`;
        panel.style.top = `${newTop}px`;
      };
      const onUp = () => {
        panel.classList.remove("dragging");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    };
    headerEl.addEventListener("mousedown", onHeaderDown);
    const cleanups: Array<() => void> = [];
    const setupResize = (handleId: string, axis: "e" | "s" | "se") => {
      const handle = document.getElementById(handleId);
      if (!handle) return;
      const onDown = (e: MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        pinPosition();
        panel.classList.add("resizing");
        const startX = e.clientX, startY = e.clientY;
        const startWidth = panel.offsetWidth, startHeight = panel.offsetHeight;
        const minWidth = parseFloat(getComputedStyle(panel).minWidth) || 320;
        const minHeight = parseFloat(getComputedStyle(panel).minHeight) || 380;
        const maxWidth = window.innerWidth - panel.offsetLeft;
        const maxHeight = window.innerHeight - panel.offsetTop;
        const onMove = (ev: MouseEvent) => {
          if (axis === "e" || axis === "se") {
            const newWidth = clamp(startWidth + (ev.clientX - startX), minWidth, maxWidth);
            panel.style.width = `${newWidth}px`;
          }
          if (axis === "s" || axis === "se") {
            const newHeight = clamp(startHeight + (ev.clientY - startY), minHeight, maxHeight);
            panel.style.height = `${newHeight}px`;
          }
        };
        const onUp = () => {
          panel.classList.remove("resizing");
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      };
      handle.addEventListener("mousedown", onDown);
      cleanups.push(() => handle.removeEventListener("mousedown", onDown));
    };
    setupResize("chatResizeE", "e");
    setupResize("chatResizeS", "s");
    setupResize("chatResizeSe", "se");
    return () => {
      headerEl.removeEventListener("mousedown", onHeaderDown);
      cleanups.forEach((fn) => fn());
    };
  }, [open]);

  const hasMessages = messages.length > 0;
  const canSend = input.trim().length > 0 && !loading && packages.length > 0;

  return (
    <>
      <button
        type="button"
        className={`chat-fab ${open ? "open" : ""}`}
        title="Assistente de edição em massa"
        aria-label="Abrir assistente de edição em massa"
        onClick={() => setOpen(true)}
      >
        <MessageSquare size={26} strokeWidth={1.8} aria-hidden="true" />
        {hasMessages && <span className="chat-fab-badge">{messages.length}</span>}
      </button>

      <div ref={panelRef} className={`chat-panel ${open ? "open" : ""}`} id="chatPanel">
        <div className="chat-panel-header">
          <span className="chat-header-grip" aria-hidden="true">
            <GripVertical size={14} />
          </span>
          <div className="chat-header-text">
            <h3>Assistente de edição</h3>
            <p>Edições em massa nos grupos e cabeçalho</p>
          </div>
          <span className="chat-header-status" title={loading ? "Processando" : "Pronto"}>
            <span className="chat-header-status-dot" style={{ opacity: loading ? 1 : 0.9, animation: loading ? "chatPulse 1.2s infinite" : "none" }} />
            {loading ? "Pensando…" : "Pronto"}
          </span>
          <button type="button" className="chat-panel-close" aria-label="Fechar assistente" onClick={() => setOpen(false)}>
            <X size={16} />
          </button>
        </div>

        <div className="chat-messages" ref={messagesRef}>
          {messages.length === 0 ? (
            <div className="chat-empty">
              <div className="chat-empty-illust" aria-hidden="true">
                <FileText size={32} strokeWidth={1.6} />
              </div>
              <p className="chat-empty-title">O que vamos editar?</p>
              <p className="chat-empty-desc">Peça em linguagem natural. Exemplos:</p>
              <div className="chat-suggestions">
                <button type="button" className="chat-suggestion-chip" onClick={() => handleSuggestion("Renomeia o grupo Bumper para Estrutura")}>Renomear grupo</button>
                <button type="button" className="chat-suggestion-chip" onClick={() => handleSuggestion("Define performance 1.1 em todos os grupos")}>Performance 1.1</button>
                <button type="button" className="chat-suggestion-chip" onClick={() => handleSuggestion("Junta os relatórios Sangam e Para-barro")}>Juntar relatórios</button>
              </div>
            </div>
          ) : (
            messages.map((m, i) => {
              if (m.role === "pending") {
                return (
                  <div key={i} className="chat-msg-row pending">
                    <span className="chat-avatar assistant" aria-hidden="true"><Sparkles size={14} strokeWidth={1.7} /></span>
                    <div className="chat-msg pending">
                      Pensando
                      <span className="chat-typing-dots"><span /><span /><span /></span>
                    </div>
                  </div>
                );
              }
              const isUser = m.role === "user";
              const isError = m.role === "error";
              return (
                <div key={i} className={`chat-msg-row ${m.role}`}>
                  <span className={`chat-avatar ${isUser ? "user" : isError ? "error" : "assistant"}`} aria-hidden="true">
                    {isUser ? <User size={14} strokeWidth={1.7} /> : isError ? <AlertTriangle size={14} strokeWidth={1.7} /> : <Sparkles size={14} strokeWidth={1.7} />}
                  </span>
                  <div className={`chat-msg ${m.role}`}>{m.text}</div>
                </div>
              );
            })
          )}
        </div>

        <div className="chat-input-wrap">
          <form
            className="chat-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              const text = input;
              setInput("");
              send(text);
            }}
          >
            <textarea
              ref={textareaRef}
              placeholder={packages.length === 0 ? "Importe um arquivo primeiro..." : "Digite um pedido de edição..."}
              autoComplete="off"
              value={input}
              rows={1}
              disabled={packages.length === 0}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  const text = input;
                  setInput("");
                  send(text);
                }
              }}
            />
            <button type="submit" className="chat-send-btn" disabled={!canSend} aria-label="Enviar mensagem" title="Enviar (Enter)">
              <Send size={18} strokeWidth={2.2} />
            </button>
          </form>
          <div className="chat-input-footer">IA pode errar — confira as alterações no preview. Enter envia, Shift+Enter quebra linha.</div>
        </div>

        <div className="chat-resize-e" id="chatResizeE" title="Redimensionar largura" />
        <div className="chat-resize-s" id="chatResizeS" title="Redimensionar altura" />
        <div className="chat-resize-se" id="chatResizeSe" title="Redimensionar largura e altura" />
      </div>
    </>
  );
}
