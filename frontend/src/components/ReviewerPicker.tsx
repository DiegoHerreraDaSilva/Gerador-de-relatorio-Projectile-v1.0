import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Check, ChevronDown, Search, UserRound } from "lucide-react";
import { useClickOutside } from "../hooks/useClickOutside";
import type { Reviewer } from "../store/useAutoGenerationStore";
import { hintText } from "../utils/hint";

/** Sem acento e sem caixa: "joão" acha "Joao" e vice-versa. */
function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLocaleLowerCase("pt-BR");
}

/** Filtra por nome ou login, com cada palavra digitada em qualquer ordem
 * ("silva di" acha "Diego da Silva"). */
export function filterReviewers(reviewers: Reviewer[], query: string): Reviewer[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return reviewers;
  return reviewers.filter((r) => {
    const text = fold(`${r.name} ${r.login}`);
    return words.every((w) => text.includes(w));
  });
}

/** Escolha do revisor com busca: botão com o atual, lista que filtra
 * enquanto digita, setas + Enter pra escolher e Esc pra fechar. */
export function ReviewerPicker({
  value,
  valueName,
  reviewers,
  emptyLabel,
  loadingLabel,
  disabled,
  onChange,
  describedBy,
}: {
  // login atual ("" = nenhum)
  value: string;
  // nome do atual quando ele não está (mais) na lista
  valueName?: string | null;
  reviewers: Reviewer[] | null;
  // o que "nenhum" significa aqui ("Sem revisor", "Padrão (Fulano)")
  emptyLabel: string;
  loadingLabel: string;
  disabled?: boolean;
  onChange: (login: string | null) => void;
  describedBy?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  useClickOutside(rootRef, () => setOpen(false), open);

  const list = reviewers ?? [];
  const current = list.find((r) => r.login.toLowerCase() === value.toLowerCase());
  const label = !value ? (reviewers ? emptyLabel : loadingLabel) : (current?.name ?? valueName ?? value);
  const matches = useMemo(() => filterReviewers(list, query), [list, query]);
  // "nenhum" só aparece sem busca (é uma opção, não um nome)
  const options: Array<Reviewer | null> = query.trim() ? matches : [null, ...matches];

  useEffect(() => {
    if (!open) return;
    setQuery("");
    const index = value ? list.findIndex((r) => r.login.toLowerCase() === value.toLowerCase()) + 1 : 0;
    setActive(Math.max(0, index));
    requestAnimationFrame(() => inputRef.current?.focus());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const choose = (reviewer: Reviewer | null) => {
    setOpen(false);
    if ((reviewer?.login ?? "").toLowerCase() !== value.toLowerCase()) onChange(reviewer?.login ?? null);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(options.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (options[active] !== undefined) choose(options[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className="reviewer-picker" ref={rootRef}>
      <button
        type="button"
        className="reviewer-picker-trigger"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled || !reviewers}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-describedby={describedBy}
        data-hint={hintText("Revisor", [label])}
      >
        <UserRound size={14} strokeWidth={2} aria-hidden="true" />
        <span className={value ? "" : "muted"}>{label}</span>
        <ChevronDown size={14} strokeWidth={2} aria-hidden="true" className={open ? "flipped" : ""} />
      </button>
      {open && (
        <div className="reviewer-picker-pop" role="dialog" aria-label="Escolher revisor">
          <label className="reviewer-picker-search">
            <Search size={14} strokeWidth={2} aria-hidden="true" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Buscar colaborador..."
              role="combobox"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={`${listId}-${active}`}
              aria-label="Buscar colaborador"
            />
          </label>
          <ul className="reviewer-picker-list" role="listbox" id={listId} ref={listRef}>
            {options.map((r, i) => {
              const selected = (r?.login ?? "").toLowerCase() === value.toLowerCase();
              return (
                <li
                  key={r?.login ?? "__none"}
                  id={`${listId}-${i}`}
                  data-index={i}
                  role="option"
                  aria-selected={selected}
                  className={`reviewer-picker-option ${i === active ? "active" : ""} ${r ? "" : "reviewer-picker-none"}`}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(r)}
                >
                  <span>{r ? r.name : emptyLabel}</span>
                  {selected && <Check size={14} strokeWidth={2.4} aria-hidden="true" />}
                </li>
              );
            })}
            {query.trim() && matches.length === 0 && (
              <li className="reviewer-picker-empty">Ninguém com “{query.trim()}” na engenharia.</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
