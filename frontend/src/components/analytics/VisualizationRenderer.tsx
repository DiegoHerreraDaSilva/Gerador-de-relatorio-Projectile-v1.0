import type { AnalyticsTable, ChartVisualization, Visualization } from "../../store/useAnalyticsChatStore";

/** Desenha o contrato de visualização do chat analítico
 * (`backend/app/analytics/visualization.py`). Nunca recebe HTML/SVG do
 * servidor — só dados; todo texto passa pelo escape do React. */

function fmt(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "—";
  const text = value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  return unit ? `${text} ${unit}` : text;
}

function summary(v: ChartVisualization): string {
  const data = v.series[0]?.data ?? [];
  return v.categories.map((c, i) => `${c}: ${fmt(data[i], v.unit)}`).join("; ");
}

function Bars({ v, horizontal }: { v: ChartVisualization; horizontal: boolean }) {
  const data = v.series[0]?.data ?? [];
  const max = Math.max(...data.map((d) => Math.abs(d ?? 0)), 0) || 1;
  const hasNegative = data.some((d) => (d ?? 0) < 0);
  return (
    <div
      className={horizontal ? "achat-hbars" : "achat-vbars"}
      role="img"
      aria-label={`${v.title}. ${summary(v)}`}
    >
      {v.categories.map((category, i) => {
        const value = data[i] ?? 0;
        const size = `${Math.max((Math.abs(value) / max) * 100, value === 0 ? 0 : 2)}%`;
        const tone = value < 0 ? "is-negative" : "";
        return horizontal ? (
          <div className="achat-hbar-row" key={category}>
            <span className="achat-hbar-label" title={category}>{category}</span>
            <span className={`achat-hbar-track ${hasNegative ? "is-diverging" : ""}`}>
              <span className={`achat-hbar-fill ${tone}`} style={{ width: hasNegative ? `calc(${size} / 2)` : size }} />
            </span>
            <span className="achat-hbar-value">{value > 0 && hasNegative ? "+" : ""}{fmt(value, v.unit)}</span>
          </div>
        ) : (
          <div className="achat-vbar-col" key={category}>
            <span className="achat-vbar-value">{fmt(value, v.unit)}</span>
            <span className="achat-vbar-track">
              <span className={`achat-vbar-fill ${tone}`} style={{ height: size }} />
            </span>
            <span className="achat-vbar-label" title={category}>{category}</span>
          </div>
        );
      })}
    </div>
  );
}

const W = 640;
const H = 220;
const PAD = { top: 28, right: 16, bottom: 34, left: 16 };

/** "setembro/2025" → "set/25" no eixo; o nome inteiro fica no tooltip do ponto. */
export function axisLabel(category: string): string {
  const match = /^(\p{L}+)\/(\d{4})$/u.exec(category);
  return match ? `${match[1].slice(0, 3)}/${match[2].slice(2)}` : category;
}

function Line({ v }: { v: ChartVisualization }) {
  const data = v.series[0]?.data ?? [];
  const values = data.map((d) => d ?? 0);
  const max = Math.max(...values, 0) || 1;
  const x = (i: number) => PAD.left + (values.length === 1 ? 0.5 : i / (values.length - 1)) * (W - PAD.left - PAD.right);
  const y = (value: number) => PAD.top + (1 - value / max) * (H - PAD.top - PAD.bottom);
  const points = values.map((value, i) => `${x(i)},${y(value)}`).join(" ");
  // rótulo de mês a cada N pontos pra não encavalar; valor em cima do ponto
  // só até 14 pontos, ~44 unidades entre eles (acima disso, só no tooltip)
  const every = Math.ceil(values.length / 12);
  const showValues = values.length <= 14;
  // primeiro e último rótulo alinhados pra dentro — centralizados, cortavam na borda
  const anchor = (i: number) =>
    values.length === 1 ? "middle" : i === 0 ? "start" : i === values.length - 1 ? "end" : "middle";
  return (
    <svg className="achat-line" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${v.title}. ${summary(v)}`}>
      <line className="achat-line-axis" x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} />
      <polyline className="achat-line-path" points={points} />
      {values.map((value, i) => (
        <g key={v.categories[i]}>
          <circle className="achat-line-dot" cx={x(i)} cy={y(value)} r={4}>
            <title>{`${v.categories[i]}: ${fmt(data[i], v.unit)}`}</title>
          </circle>
          {showValues && data[i] != null && (
            <text className="achat-line-value" x={x(i)} y={y(value) - 10} textAnchor={anchor(i)}>
              {fmt(data[i])}
            </text>
          )}
          {i % every === 0 && (
            <text className="achat-line-label" x={x(i)} y={H - 12} textAnchor={anchor(i)}>
              {axisLabel(v.categories[i])}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

export function VisualizationRenderer({ visualization }: { visualization: Visualization }) {
  if (visualization.type === "kpi") {
    return (
      <p className="achat-kpi">
        <span className="achat-kpi-value">{fmt(visualization.value)}</span>
        {visualization.unit && <span className="achat-kpi-unit">{visualization.unit}</span>}
      </p>
    );
  }
  return (
    <figure className="achat-chart">
      <figcaption>{visualization.title}</figcaption>
      {visualization.type === "line" ? (
        <Line v={visualization} />
      ) : (
        <Bars v={visualization} horizontal={visualization.type === "horizontal_bar"} />
      )}
    </figure>
  );
}

export function AnalyticsTableView({ table }: { table: AnalyticsTable }) {
  return (
    <details className="achat-table">
      <summary>
        Ver tabela com {table.rows.length} {table.rows.length === 1 ? "linha" : "linhas"}
        {table.truncated ? " (só as primeiras)" : ""}
      </summary>
      <div className="achat-table-wrap">
        <table className="kpi-table">
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{typeof cell === "number" ? fmt(cell) : cell ?? "—"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
