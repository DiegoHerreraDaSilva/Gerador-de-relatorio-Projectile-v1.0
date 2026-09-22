import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Files, X } from "lucide-react";
import { useReportStore } from "../store/useReportStore";
import { useReportTabsStore, bundleHasContent } from "../store/useReportTabsStore";

/** Lista das guias de relatório abertas — vive dentro da seção "Relatórios
 * abertos" da sidebar (`Sidebar.tsx`), nunca mais é uma barra horizontal
 * separada. `onOpenTab` (em vez de chamar `switchTab` direto) permite abrir
 * uma guia a partir de QUALQUER tela — quem chama decide se precisa trocar
 * de view antes. Quando a sidebar está recolhida, mantém um ícone por guia
 * para preservar acesso rápido sem voltar a ocupar largura horizontal. */
export function ReportTabsBar({
  collapsed,
  onOpenTab,
}: {
  collapsed: boolean;
  onOpenTab: (tabId: string) => void;
}) {
  const tabs = useReportTabsStore((s) => s.tabs);
  const activeTabId = useReportTabsStore((s) => s.activeTabId);
  const bundles = useReportTabsStore((s) => s.bundles);
  const pendingSave = useReportTabsStore((s) => s.pendingSave);
  const closeTab = useReportTabsStore((s) => s.closeTab);
  const renameTab = useReportTabsStore((s) => s.renameTab);
  // a guia ATIVA vive em useReportStore (não no bundle serializado, que só
  // é atualizado no próximo autosave) — precisa olhar aqui pra saber se ela
  // "tem conteúdo" com o dado mais recente, não o último salvo.
  const activePackagesCount = useReportStore((s) => s.packages.length);

  const [pendingCloseId, setPendingCloseId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const editInputRef = useRef<HTMLInputElement>(null);

  function requestClose(id: string) {
    const hasContent = id === activeTabId ? activePackagesCount > 0 : bundleHasContent(bundles[id]);
    if (hasContent) setPendingCloseId(id);
    else closeTab(id);
  }

  function startRename(id: string, currentLabel: string) {
    setEditingId(id);
    setEditValue(currentLabel);
    requestAnimationFrame(() => editInputRef.current?.select());
  }

  function commitRename() {
    if (editingId) renameTab(editingId, editValue);
    setEditingId(null);
  }

  if (tabs.length === 0) return null;

  if (collapsed) {
    return (
      <div className="report-tabs-bar report-tabs-bar-collapsed" aria-label="Relatórios abertos">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <button
              key={tab.id}
              type="button"
              className={`report-tab report-tab-icon ${isActive ? "active" : ""}`}
              aria-label={`Abrir ${tab.label}`}
              aria-current={isActive ? "page" : undefined}
              title={tab.label}
              onClick={() => onOpenTab(tab.id)}
            >
              <Files size={17} strokeWidth={1.8} />
              {isActive && pendingSave && <span className="report-tab-unsaved-dot" aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <>
      <div className="report-tabs-bar">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <div
              key={tab.id}
              className={`report-tab ${isActive ? "active" : ""}`}
            >
              {editingId === tab.id ? (
                <input
                  ref={editInputRef}
                  className="report-tab-rename-input"
                  value={editValue}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setEditingId(null);
                  }}
                />
              ) : (
                <button
                  type="button"
                  className="report-tab-open"
                  aria-current={isActive ? "page" : undefined}
                  title="Clique duplo para renomear"
                  onClick={() => onOpenTab(tab.id)}
                  onDoubleClick={() => startRename(tab.id, tab.label)}
                >
                  <span className="report-tab-label">{tab.label}</span>
                </button>
              )}
              {isActive && pendingSave && (
                <span className="report-tab-unsaved-dot" title="Salvando alterações..." aria-label="Alterações não salvas" />
              )}
              <button
                type="button"
                className="report-tab-close"
                aria-label={`Fechar ${tab.label}`}
                onClick={(e) => {
                  e.stopPropagation();
                  requestClose(tab.id);
                }}
              >
                <X size={13} strokeWidth={2} />
              </button>
            </div>
          );
        })}
      </div>

      {pendingCloseId &&
        createPortal(
          <div className="modal-backdrop" onClick={() => setPendingCloseId(null)}>
            <div className="modal-card report-tab-close-confirm" onClick={(e) => e.stopPropagation()}>
              <div className="modal-head">
                <h2>Fechar guia</h2>
                <button type="button" className="modal-close" onClick={() => setPendingCloseId(null)} aria-label="Fechar">
                  <X size={18} strokeWidth={2} />
                </button>
              </div>
              <div className="modal-body">
                <p>
                  Essa guia tem um relatório com dados preenchidos. Fechar descarta tudo — não tem como desfazer
                  depois.
                </p>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setPendingCloseId(null)}>
                  Cancelar
                </button>
                <button
                  type="button"
                  className="primary"
                  onClick={() => {
                    closeTab(pendingCloseId);
                    setPendingCloseId(null);
                  }}
                >
                  Fechar guia
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
