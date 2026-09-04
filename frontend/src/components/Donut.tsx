import { useId } from "react";

export type DonutSlice = { label: string; value: number; color: string };

const SIZE = 200;
const STROKE = 24;
const R = SIZE / 2 - 18;
const GAP = 0.03; // radianos de respiro entre fatias, ver skill de dashboard Schwaben

function arcPath(a0: number, a1: number): string {
  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const x0 = cx + R * Math.cos(a0);
  const y0 = cy + R * Math.sin(a0);
  const x1 = cx + R * Math.cos(a1);
  const y1 = cy + R * Math.sin(a1);
  const largeArc = a1 - a0 > Math.PI ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${R} ${R} 0 ${largeArc} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/** Donut simples (sem seleção/cross-filter — sempre mostra o total no
 * centro), com legenda sempre visível (nome + %, identidade nunca só pela
 * cor). SVG puro no mesmo espírito hand-rolled do Gauge.tsx. */
export function Donut({ slices, totalLabel, totalCaption }: { slices: DonutSlice[]; totalLabel: string; totalCaption: string }) {
  const reactId = useId();
  const total = slices.reduce((sum, s) => sum + s.value, 0);

  if (total <= 0) {
    return <p className="muted">Sem dados no período.</p>;
  }

  const startAngle = -Math.PI / 2;
  let cursor = 0;
  const segments = slices
    .filter((s) => s.value > 0)
    .map((s, i) => {
      const angleSpan = (s.value / total) * 2 * Math.PI;
      const segStart = startAngle + cursor + GAP / 2;
      const segEnd = startAngle + cursor + angleSpan - GAP / 2;
      cursor += angleSpan;
      return { ...s, segStart, segEnd, gradientId: `donut-${reactId}-${i}` };
    })
    .filter((s) => s.segEnd > s.segStart);

  return (
    <div className="donut">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="donut-svg">
        <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="var(--surface-2)" strokeWidth={STROKE} />
        <defs>
          {segments.map((seg) => (
            <linearGradient key={seg.gradientId} id={seg.gradientId} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={seg.color} stopOpacity="0.78" />
              <stop offset="100%" stopColor={seg.color} />
            </linearGradient>
          ))}
        </defs>
        {segments.map((seg) => (
          <path
            key={seg.label}
            d={arcPath(seg.segStart, seg.segEnd)}
            fill="none"
            stroke={`url(#${seg.gradientId})`}
            strokeWidth={STROKE}
            strokeLinecap="butt"
          />
        ))}
        <text x={SIZE / 2} y={SIZE / 2 - 4} textAnchor="middle" className="donut-center-value">
          {totalLabel}
        </text>
        <text x={SIZE / 2} y={SIZE / 2 + 18} textAnchor="middle" className="donut-center-label">
          {totalCaption}
        </text>
      </svg>
      <div className="donut-legend">
        {slices.map((s) => (
          <div key={s.label} className="donut-legend-item">
            <span className="donut-legend-swatch" style={{ background: s.color }} />
            <span className="donut-legend-label">{s.label}</span>
            <span className="donut-legend-value">{Math.round((s.value / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
