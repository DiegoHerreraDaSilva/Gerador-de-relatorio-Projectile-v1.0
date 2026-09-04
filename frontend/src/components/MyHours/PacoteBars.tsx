import { fmtNum } from "../../utils/fmt";
import type { PacoteTotal } from "../../utils/myHours";

const MAX_BARS = 8;

/** Cauda dobrada em "Outros" em vez de cortada: `slice(0, n)` e descartar o
 * resto mente sobre a proporção, porque as barras deixam de somar o total. */
function capWithOthers(items: PacoteTotal[]): PacoteTotal[] {
  if (items.length <= MAX_BARS) return items;
  const head = items.slice(0, MAX_BARS - 1);
  const tail = items.slice(MAX_BARS - 1);
  return [
    ...head,
    {
      name: "Outros",
      hours: Math.round(tail.reduce((s, i) => s + i.hours, 0) * 100) / 100,
      share: tail.reduce((s, i) => s + i.share, 0),
    },
  ];
}

/** Ranking de horas por pacote de trabalho, cor única (`var(--accent)`).
 *
 * Cor única e não uma por item: com vários pacotes a cor não codifica
 * identidade (cada barra já tem rótulo), só indicaria magnitude — que a
 * própria barra mostra.
 *
 * A largura é normalizada pelo TOTAL DO PERÍODO, não pelo maior item. Com um
 * item só, normalizar pelo máximo desenha uma barra cheia em 100% que é
 * auto-referente e não informa nada; pelo total, uma barra cheia significa de
 * fato "todo o período foi neste pacote".
 *
 * Cada barra é um `<button>` que filtra a tabela — e SÓ a tabela. O filtro
 * nunca recalcula os KPIs do topo. */
export function PacoteBars({
  items,
  selected,
  onSelect,
}: {
  items: PacoteTotal[];
  selected: string | null;
  onSelect: (name: string) => void;
}) {
  if (items.length === 0) {
    return <p className="muted">Nenhum lançamento no período selecionado.</p>;
  }

  const capped = capWithOthers(items);

  if (capped.length === 1) {
    // uma categoria só não é distribuição: a frase informa mais que a barra
    return (
      <p className="pacotebars-single">
        Todo o período em <strong>{capped[0].name}</strong> — {fmtNum(capped[0].hours)} h.
      </p>
    );
  }

  return (
    <div className="pacotebars">
      {capped.map((item) => {
        const isSelected = selected === item.name;
        const dimmed = selected !== null && !isSelected;
        return (
          <button
            type="button"
            key={item.name}
            className={`pacotebars-row ${isSelected ? "is-selected" : ""} ${dimmed ? "is-dimmed" : ""}`}
            aria-pressed={isSelected}
            aria-label={`${item.name}: ${fmtNum(item.hours)} horas, ${Math.round(
              item.share * 100
            )}% do período. Filtrar lançamentos.`}
            onClick={() => onSelect(item.name)}
            disabled={item.name === "Outros"}
            title={item.name === "Outros" ? "Agrupamento da cauda — sem filtro" : item.name}
          >
            <span className="pacotebars-top">
              <span className="pacotebars-label">{item.name}</span>
              <span className="pacotebars-value">
                {fmtNum(item.hours)} h · {Math.round(item.share * 100)}%
              </span>
            </span>
            <span className="bar-track">
              <span
                className="bar-track-fill"
                style={{ width: `${Math.max(2, item.share * 100)}%` }}
              />
            </span>
          </button>
        );
      })}
    </div>
  );
}
