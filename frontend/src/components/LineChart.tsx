import { useId } from "react";

export type LinePoint = { label: string; value: number };

const VIEW_WIDTH = 600;
const VIEW_HEIGHT = 160;
const PAD_Y = 12;

/** Linha + área em SVG puro (sem lib de gráfico), no mesmo espírito
 * hand-rolled do Gauge.tsx — cores via `var(--...)`, então acompanha o tema
 * claro/escuro sozinho. Pontos sem lançamento simplesmente não entram em
 * `points` (quem monta os dados, ver utils/myHours.ts, já garante isso) —
 * nunca desenha um "vale" fantasma de dia sem hora apontada.
 *
 * `id` do gradiente precisa ser único por instância (via `useId`) — dois
 * gráficos na mesma página com o mesmo id de gradiente colidem e um deles
 * renderiza sem cor. Sem tooltip/crosshair interativo nesta v1 — mantém o
 * componente enxuto; só a linha, a área e os pontos. */
export function LineChart({ points }: { points: LinePoint[] }) {
  const reactId = useId();
  const strokeGradientId = `line-stroke-${reactId}`;
  const areaGradientId = `line-area-${reactId}`;

  if (points.length === 0) {
    return <p className="muted">Sem dados no período.</p>;
  }

  const maxValue = Math.max(...points.map((p) => p.value), 1);
  const stepX = points.length > 1 ? VIEW_WIDTH / (points.length - 1) : 0;
  const toX = (i: number) => (points.length > 1 ? i * stepX : VIEW_WIDTH / 2);
  const toY = (v: number) => VIEW_HEIGHT - PAD_Y - (v / maxValue) * (VIEW_HEIGHT - PAD_Y * 2);

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(p.value).toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${toX(points.length - 1).toFixed(1)} ${VIEW_HEIGHT} L ${toX(0).toFixed(1)} ${VIEW_HEIGHT} Z`;

  return (
    <div className="line-chart">
      <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} preserveAspectRatio="none" className="line-chart-svg">
        <defs>
          <linearGradient id={strokeGradientId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--accent)" />
            <stop offset="100%" stopColor="var(--accent-hi)" />
          </linearGradient>
          <linearGradient id={areaGradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#${areaGradientId})`} stroke="none" />
        <path d={linePath} fill="none" stroke={`url(#${strokeGradientId})`} strokeWidth={2.5} className="line-chart-line" />
        {points.map((p, i) => (
          <circle key={`${p.label}-${i}`} cx={toX(i)} cy={toY(p.value)} r={3} className="line-chart-point" />
        ))}
      </svg>
      <div className="line-chart-labels">
        <span>{points[0].label}</span>
        {points.length > 1 && <span>{points[points.length - 1].label}</span>}
      </div>
    </div>
  );
}
