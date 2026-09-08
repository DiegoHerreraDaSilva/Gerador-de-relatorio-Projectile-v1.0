import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Plus, X } from "lucide-react";
import { useReportStore } from "../store/useReportStore";
import { useReportTabsStore, bundleHasContent } from "../store/useReportTabsStore";

export function ReportTabsBar() {
  const tabs = useReportTabsStore((s) => s.tabs);
  const activeTabId = useReportTabsStore((s) => s.activeTabId);
  const bundles = useReportTabsStore((s) => s.bundles);
  const addTab = useReportTabsStore((s) => s.addTab);
  const closeTab = useReportTabsStore((s) => s.closeTab);
  const switchTab = useReportTabsStore((s) => s.switchTab);
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

  return (
    <>
      <div className="report-tabs-bar">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`report-tab ${tab.id === activeTabId ? "active" : ""}`}
            onClick={() => switchTab(tab.id)}
            onDoubleClick={() => startRename(tab.id, tab.label)}
            title="Clique duplo para renomear"
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
              <span className="report-tab-label">{tab.label}</span>
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
        ))}
        <button type="button" className="report-tab-add" title="Nova guia" onClick={() => addTab()}>
          <Plus size={15} strokeWidth={2} />
        </button>
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
