import { fmtNum } from "../utils/fmt";

export type BarListItem = { name: string; hours: number };

/** Lista ranqueada horizontal — cor única (`var(--accent)`), não uma por
 * item: com muitos projetos a cor não ajudaria a identificar nada (cada
 * barra já tem o próprio rótulo), só indicaria magnitude, que a barra em si
 * já mostra. Ver skill de dashboard Schwaben. */
export function BarList({ items, emptyMessage }: { items: BarListItem[]; emptyMessage: string }) {
  if (items.length === 0) {
    return <p className="muted">{emptyMessage}</p>;
  }
  const top = Math.max(...items.map((i) => i.hours), 1);
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div key={item.name} className="bar-list-row">
          <div className="bar-list-top">
            <span className="bar-list-label" title={item.name}>{item.name}</span>
            <span className="bar-list-value">{fmtNum(item.hours)} h</span>
          </div>
          <div className="bar-track">
            <div className="bar-track-fill" style={{ width: `${Math.max(4, (item.hours / top) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
