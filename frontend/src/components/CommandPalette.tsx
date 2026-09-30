import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { CornerDownLeft, Search } from "lucide-react";
import { useModal } from "../hooks/useModal";
import { filterCommands, type Command } from "../utils/commands";

/** Paleta de comandos (Ctrl/⌘+K ou "/"): busca e executa qualquer navegação ou ação sem tirar a mão do
 * teclado. Os comandos vêm prontos de `utils/commands.buildCommands` (a regra de quem vê o quê fica lá).
 * Setas movem, Enter executa, Esc fecha (`useModal`, que também prende o Tab e devolve o foco). */
export function CommandPalette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  const modalRef = useModal({ onClose });
  const listId = useId();

  const visible = useMemo(() => filterCommands(commands, query), [commands, query]);
  const current = visible[Math.min(active, visible.length - 1)];

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active, visible]);

  const run = (command: Command | undefined) => {
    if (!command) return;
    onClose();
    // depois de fechar: o modal devolve o foco a quem abriu e só então o comando age
    window.setTimeout(command.run, 0);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (visible.length ? (i + 1) % visible.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (visible.length ? (i - 1 + visible.length) % visible.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(current);
    }
  };

  let lastGroup = "";
  return createPortal(
    <div className="modal-backdrop palette-backdrop" onClick={onClose}>
      <div
        ref={modalRef}
        tabIndex={-1}
        className="modal-card palette-card"
        role="dialog"
        aria-modal="true"
        aria-label="Paleta de comandos"
        onClick={(e) => e.stopPropagation()}
      >
        <label className="palette-search">
          <Search size={17} strokeWidth={2} aria-hidden="true" />
          <input
            type="text"
            autoComplete="off"
            spellCheck={false}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={current ? `${listId}-${current.id}` : undefined}
            aria-label="Buscar telas, guias e ações"
            placeholder="Buscar telas, guias e ações..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
          />
          <kbd className="palette-kbd">Esc</kbd>
        </label>
        <ul className="palette-list" role="listbox" id={listId} ref={listRef}>
          {visible.length === 0 && <li className="palette-empty">Nenhum comando para “{query.trim()}”.</li>}
          {visible.map((command, index) => {
            const heading = command.group !== lastGroup ? command.group : null;
            lastGroup = command.group;
            return (
              <li key={command.id} role="presentation">
                {heading && !query.trim() && <p className="palette-group">{heading}</p>}
                <button
                  type="button"
                  role="option"
                  id={`${listId}-${command.id}`}
                  tabIndex={-1}
                  aria-selected={index === active}
                  data-active={index === active}
                  className={`palette-item ${index === active ? "active" : ""}`}
                  onMouseMove={() => setActive(index)}
                  onClick={() => run(command)}
                >
                  <span className="palette-item-label">{command.label}</span>
                  {query.trim() && <span className="palette-item-group">{command.group}</span>}
                  {command.hint && <span className="palette-item-hint">{command.hint}</span>}
                  {index === active && <CornerDownLeft size={14} strokeWidth={2} aria-hidden="true" />}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>,
    document.body,
  );
}
