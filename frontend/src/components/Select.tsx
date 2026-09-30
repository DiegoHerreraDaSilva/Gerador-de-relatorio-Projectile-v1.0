import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useClickOutside } from "../hooks/useClickOutside";
import { hintText } from "../utils/hint";
import { matchesQuery } from "../utils/search";

export type SelectOption = { value: string; label: string; disabled?: boolean };

/** Seleção de UMA opção no visual do app — no lugar do `<select>` nativo, cuja
 * lista abre com o visual do sistema (branca no tema escuro, sem respeitar os
 * tokens). Mesmo look dos filtros (`.month-dropdown*`), com a caixa de busca no
 * topo da lista (sem acento, sem diferenciar maiúsculas, várias palavras em
 * qualquer ordem), teclado completo (setas, Enter, Esc; Home/End e Espaço só
 * fora da busca, onde são texto) e a lista abre pra cima quando não cabe
 * embaixo. Controlado: `value`/`onChange(value)`. */
export function Select({
  value,
  options,
  onChange,
  ariaLabel,
  disabled,
  className,
}: {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  // posição dentro de `visible` (a lista já filtrada pela busca)
  const [active, setActive] = useState(0);
  const [query, setQuery] = useState("");
  const [up, setUp] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listId = useId();
  useClickOutside(rootRef, () => close(), open);

  const current = options.find((o) => o.value === value);
  const visible = query.trim() ? options.filter((o) => matchesQuery(o.label, query)) : options;

  const firstEnabled = (list: SelectOption[]) =>
    Math.max(
      0,
      list.findIndex((o) => !o.disabled),
    );

  const openList = () => {
    if (disabled) return;
    const rect = rootRef.current?.getBoundingClientRect();
    // 300px = altura máxima da lista com a busca: sem espaço embaixo e com mais em cima, abre pra cima
    setUp(Boolean(rect && rect.bottom + 300 > window.innerHeight && rect.top > 300));
    setQuery("");
    setActive(
      Math.max(
        0,
        options.findIndex((o) => o.value === value),
      ),
    );
    setOpen(true);
  };
  function close() {
    setOpen(false);
    setQuery("");
  }
  const choose = (index: number) => {
    const option = visible[index];
    if (!option || option.disabled) return;
    onChange(option.value);
    close();
    triggerRef.current?.focus();
  };
  const move = (from: number, step: 1 | -1) => {
    for (let i = from + step; i >= 0 && i < visible.length; i += step) {
      if (!visible[i].disabled) return i;
    }
    return from;
  };

  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (open) listRef.current?.querySelector<HTMLElement>('[data-active="true"]')?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const onSearch = (text: string) => {
    setQuery(text);
    const next = text.trim() ? options.filter((o) => matchesQuery(o.label, text)) : options;
    setActive(firstEnabled(next));
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (disabled) return;
    const inSearch = e.target instanceof HTMLInputElement;
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
      triggerRef.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => move(i, 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => move(i, -1));
    } else if (e.key === "Home" && !inSearch) {
      e.preventDefault();
      setActive(move(-1, 1));
    } else if (e.key === "End" && !inSearch) {
      e.preventDefault();
      setActive(move(visible.length, -1));
    } else if (e.key === "Enter" || (e.key === " " && !inSearch)) {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Tab") {
      close();
    }
  };

  return (
    <div className={`month-dropdown app-select ${className ?? ""}`} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className="month-dropdown-trigger"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        data-hint={hintText(ariaLabel, [current?.label ?? ""])}
        disabled={disabled}
        onClick={() => (open ? close() : openList())}
      >
        <span className="mgmt-filter-summary">{current?.label ?? ""}</span>
        <ChevronDown
          size={15}
          strokeWidth={2}
          className={`month-dropdown-chevron ${open ? "open" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <ul
          className={`month-dropdown-list app-select-list ${up ? "up" : ""}`}
          role="listbox"
          id={listId}
          ref={listRef}
        >
          <li className="month-dropdown-search" role="presentation">
            <input
              ref={searchRef}
              type="search"
              autoComplete="off"
              spellCheck={false}
              value={query}
              placeholder="Buscar..."
              aria-label={ariaLabel ? `Buscar em ${ariaLabel}` : "Buscar"}
              onChange={(e) => onSearch(e.target.value)}
            />
          </li>
          {visible.length === 0 && (
            <li className="mgmt-filter-empty" role="presentation">
              Nenhum resultado
            </li>
          )}
          {visible.map((option, index) => (
            <li key={option.value} role="presentation">
              <button
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={option.value === value}
                data-active={index === active}
                disabled={option.disabled}
                data-hint={option.label}
                data-hint-side="right"
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
