import type { MonthRow } from "../store/useManagementStore";
import { fmtNum } from "../utils/fmt";

type Props = {
  rows: MonthRow[];
};

type Series = {
  key: "worked" | "billed" | "delta";
  label: string;
  color: string;
  values: Array<number | null>;
};

const WIDTH = 720;
const HEIGHT = 240;
const PAD_LEFT = 44;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;

/** Quebra uma série em segmentos de polyline contíguos — um mês sem dado
 * (`null`, ex: billed_hours antes do 1º e-mail chegar, ou toda a série
 * quando o filtro de Pessoa está ativo) corta a linha em vez de interpolar
 * um valor que não existe. */
function buildSegments(points: Array<{ x: number; y: number } | null>): Array<Array<{ x: number; y: number }>> {
  const segments: Array<Array<{ x: number; y: number }>> = [];
  let current: Array<{ x: number; y: number }> = [];
  for (const p of points) {
    if (p === null) {
      if (current.length > 1) segments.push(current);
      current = [];
      continue;
    }
    current.push(p);
  }
  if (current.length > 1) segments.push(current);
  return segments;
}

/** Gráfico evolutivo Trabalhado/Faturado/Delta — SVG puro, sem lib de
 * gráfico (mesmo padrão de Gauge.tsx). Eixo Y único em horas, compartilhado
 * pelas 3 séries: todas já são a mesma unidade, então uma escala só é
 * legítima mesmo com magnitudes bem diferentes entre Trabalhado e Delta. */
export function EvolutionChart({ rows }: Props) {
  if (rows.length === 0) {
    return (
      <div className="evolution-chart-empty muted">Sem dados no recorte atual pra desenhar o gráfico.</div>
    );
  }

  const series: Series[] = [
    { key: "worked", label: "Trabalhado", color: "var(--accent)", values: rows.map((r) => r.worked_hours) },
    { key: "billed", label: "Faturado", color: "var(--brand-strong)", values: rows.map((r) => r.billed_hours) },
    { key: "delta", label: "Delta (Performance)", color: "var(--warn)", values: rows.map((r) => r.perf_hours) },
  ];

  const allValues = series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  const rawMin = allValues.length ? Math.min(...allValues) : 0;
  const rawMax = allValues.length ? Math.max(...allValues) : 0;
  // sempre inclui 0 no domínio — é a linha de base do Delta, precisa estar
  // visível mesmo quando todo o resto do gráfico é bem positivo.
  const domainMin = Math.min(0, rawMin);
  const domainMax = Math.max(0, rawMax);
  const span = domainMax - domainMin || 1;
  // 8% de respiro em cima/embaixo pra ponto/linha não colar na borda do SVG.
  const yMin = domainMin - span * 0.08;
  const yMax = domainMax + span * 0.08;

  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const xFor = (i: number) => (rows.length === 1 ? PAD_LEFT + plotWidth / 2 : PAD_LEFT + (i / (rows.length - 1)) * plotWidth);
  const yFor = (v: number) => PAD_TOP + plotHeight - ((v - yMin) / (yMax - yMin)) * plotHeight;
  const zeroY = yFor(0);

  return (
    <div className="evolution-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="evolution-chart-svg" role="img" aria-label="Gráfico evolutivo de horas trabalhadas, faturadas e delta de performance por mês">
        {/* linha de base em 0 — destacada porque o Delta pode ficar negativo */}
        <line x1={PAD_LEFT} y1={zeroY} x2={WIDTH - PAD_RIGHT} y2={zeroY} className="evolution-chart-zero-line" />

        {rows.map((r, i) => (
          <text key={r.month} x={xFor(i)} y={HEIGHT - 8} textAnchor="middle" className="evolution-chart-axis-label">
            {r.month}
          </text>
        ))}

        {series.map((s) => {
          const points = s.values.map((v, i) => (v === null ? null : { x: xFor(i), y: yFor(v) }));
          const segments = buildSegments(points);
          return (
            <g key={s.key}>
              {segments.map((seg, si) => (
                <polyline
                  key={si}
                  points={seg.map((p) => `${p.x},${p.y}`).join(" ")}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2.25}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  className="evolution-chart-line"
                />
              ))}
              {points.map((p, i) =>
                p === null ? null : (
                  <circle key={i} cx={p.x} cy={p.y} r={3.25} fill={s.color} className="evolution-chart-point">
                    <title>{`${rows[i].month} — ${s.label}: ${fmtNum(s.values[i] as number)}h`}</title>
                  </circle>
                )
              )}
            </g>
          );
        })}
      </svg>

      <div className="evolution-chart-legend">
        {series.map((s) => (
          <span key={s.key} className="evolution-chart-legend-item">
            <span className="evolution-chart-legend-dot" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
