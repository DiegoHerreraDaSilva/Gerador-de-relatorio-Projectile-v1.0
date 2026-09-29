import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useClickOutside } from "../hooks/useClickOutside";

export type SelectOption = { value: string; label: string; disabled?: boolean };

/** Seleção de UMA opção no visual do app — no lugar do `<select>` nativo, cuja
 * lista abre com o visual do sistema (branca no tema escuro, sem respeitar os
 * tokens). Mesmo look dos filtros (`.month-dropdown*`), com teclado completo
 * (setas, Home/End, Enter/Espaço, Esc, digitar a inicial) e a lista abre pra
 * cima quando não cabe embaixo. Controlado: `value`/`onChange(value)`. */
export function Select({ value, options, onChange, ariaLabel, disabled, className }: {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [up, setUp] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  useClickOutside(rootRef, () => setOpen(false), open);

  const selectedIndex = options.findIndex((o) => o.value === value);
  const current = options[selectedIndex];

  const openList = () => {
    if (disabled) return;
    const rect = rootRef.current?.getBoundingClientRect();
    // 260px = altura máxima da lista: sem espaço embaixo e com mais em cima, abre pra cima
    setUp(Boolean(rect && rect.bottom + 260 > window.innerHeight && rect.top > 260));
    setActive(Math.max(0, selectedIndex));
    setOpen(true);
  };
  const close = () => setOpen(false);
  const choose = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    close();
  };
  const move = (from: number, step: 1 | -1) => {
    for (let i = from + step; i >= 0 && i < options.length; i += step) {
      if (!options[i].disabled) return i;
    }
    return from;
  };

  useEffect(() => {
    if (open) listRef.current?.querySelector<HTMLElement>('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const onKeyDown = (e: KeyboardEvent) => {
    if (disabled) return;
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        openList();
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => move(i, 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => move(i, -1));
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(move(-1, 1));
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(move(options.length, -1));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Tab") {
      close();
    } else if (e.key.length === 1) {
      // digitar a inicial pula pra próxima opção que começa com ela
      const letter = e.key.toLocaleLowerCase("pt-BR");
      const found = options.findIndex((o, i) => i > active && !o.disabled && o.label.toLocaleLowerCase("pt-BR").startsWith(letter));
      const wrap = found >= 0 ? found : options.findIndex((o) => !o.disabled && o.label.toLocaleLowerCase("pt-BR").startsWith(letter));
      if (wrap >= 0) setActive(wrap);
    }
  };

  return (
    <div className={`month-dropdown app-select ${className ?? ""}`} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        type="button"
        className="month-dropdown-trigger"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => (open ? close() : openList())}
      >
        <span className="mgmt-filter-summary" title={current?.label}>{current?.label ?? ""}</span>
        <ChevronDown size={15} strokeWidth={2} className={`month-dropdown-chevron ${open ? "open" : ""}`} aria-hidden="true" />
      </button>
      {open && (
        <ul className={`month-dropdown-list app-select-list ${up ? "up" : ""}`} role="listbox" id={listId} ref={listRef}>
          {options.map((option, index) => (
            <li key={option.value} role="presentation">
              <button
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={option.value === value}
                data-active={index === active}
                disabled={option.disabled}
                className={`month-dropdown-option app-select-option ${option.value === value ? "active" : ""} ${index === active ? "kbd" : ""}`}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(index)}
              >
                <span className="app-select-option-label">{option.label}</span>
                {option.value === value && <Check size={14} strokeWidth={2.4} aria-hidden="true" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
