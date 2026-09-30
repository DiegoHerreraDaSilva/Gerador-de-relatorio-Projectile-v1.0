import { createPortal } from "react-dom";
import { Sparkles, X } from "lucide-react";
import { useModal } from "../hooks/useModal";
import type { ChangelogEntry } from "../utils/changelog";

/** "Novidades": o que mudou no app, por papel. Abre sozinho uma vez por entrega nova (App.tsx) e, quando a pessoa
 * quer rever, pela paleta de comandos ("Ver novidades"). */
export function WhatsNewModal({ entries, onClose }: { entries: ChangelogEntry[]; onClose: () => void }) {
  const modalRef = useModal({ onClose });
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={modalRef}
        tabIndex={-1}
        className="modal-card whats-new-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="whats-new-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="whats-new-title">
            <Sparkles size={17} strokeWidth={2} aria-hidden="true" /> Novidades
          </h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar">
            <X size={18} strokeWidth={2} />
          </button>
        </div>
        <div className="whats-new-body">
          {entries.length === 0 && <p className="muted">Nada novo por aqui.</p>}
          {entries.map((entry) => (
            <section key={entry.version} className="whats-new-entry">
              <h3>{entry.title}</h3>
              <ul>
                {entry.items.map((item) => (
                  <li key={item.text}>{item.text}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="modal-actions">
          <button type="button" className="primary" onClick={onClose}>
            Entendi
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
