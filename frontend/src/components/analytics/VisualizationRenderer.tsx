import { useMemo, useState } from "react";
import { Download } from "lucide-react";
import type {
  AnalyticsTable,
  ChartVisualization,
  HeatmapVisualization,
  KpiVisualization,
  Series,
  Visualization,
} from "../../store/useAnalyticsChatStore";

/** Desenha o contrato de visualização do chat analítico
 * (`backend/app/analytics/cross_output.py` e `visualization.py`). Nunca
 * recebe HTML/SVG do servidor — só dados; todo texto passa pelo escape do
 * React. Cor segue a POSIÇÃO da série (s0..s4) e "Outros" tem cor própria:
 * a paleta nunca cicla, então duas séries nunca dividem cor. */

function fmt(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return "—";
  const text = value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  if (!unit) return text;
  return unit === "%" ? `${text}%` : `${text} ${unit}`;
}

/** valor dentro da célula da tabela, pelo tipo da coluna */
export function formatCell(value: string | number | null | undefined, type?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  const number = value.toLocaleString("pt-BR", { maximumFractionDigits: type === "count" ? 0 : 2 });
  if (type === "percent") return `${number}%`;
  if (type === "ms") return `${number} ms`;
  return number;
}

function summary(v: ChartVisualization): string {
  return v.series
    .map((s) => `${s.name}: ${v.categories.map((c, i) => `${c} ${fmt(s.data[i], v.unit)}`).join(", ")}`)
    .join("; ");
}

const seriesClass = (s: Series, i: number) => (s.tail ? "achat-s-tail" : `achat-s${i % 5}`);

function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <ul className="achat-legend">
      {series.map((s, i) => (
        <li key={s.name}>
          <span className={`achat-swatch ${seriesClass(s, i)}`} aria-hidden="true" />
          {s.name}
        </li>
      ))}
    </ul>
  );
}

// --- barras --------------------------------------------------------------------

function HorizontalBars({ v }: { v: ChartVisualization }) {
  const multi = v.series.length > 1;
  const stacked = Boolean(v.stacked) && multi;
  const single = v.series[0]?.data ?? [];
  const hasNegative = !multi && single.some((d) => (d ?? 0) < 0);
  const max = stacked
    ? Math.max(...v.categories.map((_, i) => v.series.reduce((sum, s) => sum + Math.max(s.data[i] ?? 0, 0), 0)), 0) || 1
    : Math.max(...v.series.flatMap((s) => s.data.map((d) => Math.abs(d ?? 0))), 0) || 1;
  const width = (value: number) => `${Math.max((Math.abs(value) / max) * 100, value === 0 ? 0 : 1.5)}%`;
  return (
    <>
      <div className={`achat-hbars ${multi && !stacked ? "is-grouped" : ""}`} role="img" aria-label={`${v.title}. ${summary(v)}`}>
        {v.categories.map((category, i) => {
          const total = v.series.reduce((sum, s) => sum + (s.data[i] ?? 0), 0);
          return (
            <div className="achat-hbar-row" key={category}>
              <span className="achat-hbar-label" title={category}>{category}</span>
              {stacked ? (
                <span className="achat-hbar-track">
                  <span className="achat-hbar-stack">
                    {v.series.map((s, si) => {
                      const value = s.data[i] ?? 0;
                      return value > 0 ? (
                        <span
                          key={s.name}
                          className={`achat-hbar-seg ${seriesClass(s, si)}`}
                          style={{ width: width(value) }}
                          title={`${s.name}: ${fmt(value, v.unit)}`}
                        />
                      ) : null;
                    })}
                  </span>
                </span>
              ) : multi ? (
                <span className="achat-hbar-group">
                  {v.series.map((s, si) => (
                    <span className="achat-hbar-track is-thin" key={s.name} title={`${s.name}: ${fmt(s.data[i], v.unit)}`}>
                      <span
                        className={`achat-hbar-fill ${seriesClass(s, si)} ${(s.data[i] ?? 0) < 0 ? "is-negative" : ""}`}
                        style={{ width: width(s.data[i] ?? 0) }}
                      />
                    </span>
                  ))}
                </span>
              ) : (
                <span className={`achat-hbar-track ${hasNegative ? "is-diverging" : ""}`}>
                  <span
                    className={`achat-hbar-fill ${(single[i] ?? 0) < 0 ? "is-negative" : ""}`}
                    style={{ width: hasNegative ? `calc(${width(single[i] ?? 0)} / 2)` : width(single[i] ?? 0) }}
                  />
                </span>
              )}
              <span className="achat-hbar-value">
                {stacked
                  ? fmt(total, v.unit)
                  : multi
                    ? v.series.map((s) => fmt(s.data[i], v.unit)).join(" · ")
                    : `${(single[i] ?? 0) > 0 && hasNegative ? "+" : ""}${fmt(single[i], v.unit)}`}
              </span>
            </div>
          );
        })}
      </div>
      <Legend series={v.series} />
    </>
  );
}

function VerticalBars({ v }: { v: ChartVisualization }) {
  const max = Math.max(...v.series.flatMap((s) => s.data.map((d) => Math.abs(d ?? 0))), 0) || 1;
  return (
    <>
      <div className="achat-vbars" role="img" aria-label={`${v.title}. ${summary(v)}`}>
        {v.categories.map((category, i) => (
          <div className="achat-vbar-col" key={category}>
            <span className="achat-vbar-value">{v.series.map((s) => fmt(s.data[i], v.unit)).join(" · ")}</span>
            <span className="achat-vbar-track">
              {v.series.map((s, si) => {
                const value = s.data[i] ?? 0;
                return (
                  <span
                    key={s.name}
                    className={`achat-vbar-fill ${v.series.length > 1 ? seriesClass(s, si) : ""} ${value < 0 ? "is-negative" : ""}`}
                    style={{ height: `${Math.max((Math.abs(value) / max) * 100, value === 0 ? 0 : 2)}%` }}
                    title={`${s.name}: ${fmt(s.data[i], v.unit)}`}
                  />
                );
              })}
            </span>
            <span className="achat-vbar-label" title={category}>{category}</span>
          </div>
        ))}
      </div>
      <Legend series={v.series} />
    </>
  );
}

// --- linha ---------------------------------------------------------------------

const W = 640;
const H = 220;
const PAD = { top: 28, right: 16, bottom: 34, left: 16 };

/** "setembro/2025" → "set/25" no eixo; o nome inteiro fica no tooltip do ponto. */
export function axisLabel(category: string): string {
  const match = /^(\p{L}+)\/(\d{4})$/u.exec(category);
  return match ? `${match[1].slice(0, 3)}/${match[2].slice(2)}` : category;
}

function Line({ v }: { v: ChartVisualization }) {
  const count = v.categories.length;
  const all = v.series.flatMap((s) => s.data.filter((d): d is number => d !== null && d !== undefined));
  const max = Math.max(...all, 0);
  const min = Math.min(...all, 0);
  const span = max - min || 1;
  const x = (i: number) => PAD.left + (count === 1 ? 0.5 : i / (count - 1)) * (W - PAD.left - PAD.right);
  const y = (value: number) => PAD.top + (1 - (value - min) / span) * (H - PAD.top - PAD.bottom);
  // rótulo de mês a cada N pontos pra não encavalar; valor em cima do ponto
  // só com uma série e até 14 pontos (acima disso, só no tooltip)
  const every = Math.ceil(count / 12);
  const single = v.series.length === 1;
  const showValues = single && count <= 14;
  const anchor = (i: number) => (count === 1 ? "middle" : i === 0 ? "start" : i === count - 1 ? "end" : "middle");
  return (
    <>
      <svg className="achat-line" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${v.title}. ${summary(v)}`}>
        <line className="achat-line-axis" x1={PAD.left} x2={W - PAD.right} y1={y(0)} y2={y(0)} />
        {v.series.map((s, si) => {
          // período sem valor fica fora da linha — não inventa zero no meio
          const segments: string[][] = [[]];
          s.data.forEach((d, i) => {
            if (d === null || d === undefined) segments.push([]);
            else segments[segments.length - 1].push(`${x(i)},${y(d)}`);
          });
          return (
            <g key={s.name} className={single ? "" : seriesClass(s, si)}>
              {segments.filter((pts) => pts.length > 1).map((pts, k) => (
                <polyline key={k} className="achat-line-path" points={pts.join(" ")} />
              ))}
              {s.data.map((d, i) =>
                d === null || d === undefined ? null : (
                  <circle key={i} className="achat-line-dot" cx={x(i)} cy={y(d)} r={single ? 4 : 3}>
                    <title>{`${s.name} — ${v.categories[i]}: ${fmt(d, v.unit)}`}</title>
                  </circle>
                )
              )}
            </g>
          );
        })}
        {showValues &&
          v.series[0].data.map((d, i) =>
            d === null || d === undefined ? null : (
              <text key={i} className="achat-line-value" x={x(i)} y={y(d) - 10} textAnchor={anchor(i)}>
                {fmt(d)}
              </text>
            )
          )}
        {v.categories.map((c, i) =>
          i % every === 0 ? (
            <text key={c} className="achat-line-label" x={x(i)} y={H - 12} textAnchor={anchor(i)}>
              {axisLabel(c)}
            </text>
          ) : null
        )}
      </svg>
      <Legend series={v.series} />
    </>
  );
}

// --- rosca ---------------------------------------------------------------------

function Donut({ v }: { v: ChartVisualization }) {
  const data = (v.series[0]?.data ?? []).map((d) => Math.max(d ?? 0, 0));
  const total = data.reduce((a, b) => a + b, 0);
  const size = 180;
  const r = size / 2 - 16;
  const gap = data.filter((d) => d > 0).length > 1 ? 0.025 : 0;
  let angle = -Math.PI / 2;
  const arcs = data.map((value) => {
    const sweep = total ? (value / total) * Math.PI * 2 : 0;
    const start = angle + gap / 2;
    const end = angle + sweep - gap / 2;
    angle += sweep;
    if (value <= 0 || end <= start) return null;
    // fatia de 100%: dois arcos (um arco SVG não fecha um círculo inteiro)
    if (sweep >= Math.PI * 2 - 1e-6) return "full";
    const large = end - start > Math.PI ? 1 : 0;
    const p = (a: number) => `${size / 2 + r * Math.cos(a)},${size / 2 + r * Math.sin(a)}`;
    return `M ${p(start)} A ${r} ${r} 0 ${large} 1 ${p(end)}`;
  });
  return (
    <div className="achat-donut" role="img" aria-label={`${v.title}. ${summary(v)}`}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
        <circle className="achat-donut-track" cx={size / 2} cy={size / 2} r={r} />
        {arcs.map((d, i) =>
          d === "full" ? (
            <circle key={i} className={`achat-donut-arc achat-s${i % 5}`} cx={size / 2} cy={size / 2} r={r} />
          ) : d ? (
            <path key={i} d={d} className={`achat-donut-arc achat-s${i % 5}`}>
              <title>{`${v.categories[i]}: ${fmt(data[i], v.unit)}`}</title>
            </path>
          ) : null
        )}
        <text className="achat-donut-total" x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="central">
          {fmt(total, v.unit)}
        </text>
      </svg>
      <ul className="achat-donut-legend">
        {v.categories.map((c, i) => (
          <li key={c}>
            <span className={`achat-swatch achat-s${i % 5}`} aria-hidden="true" />
            <span className="achat-donut-name">{c}</span>
            <span className="achat-donut-value">
              {fmt(data[i], v.unit)} <small>{total ? `${fmt((data[i] / total) * 100)}%` : ""}</small>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- mapa de calor ------------------------------------------------------------------

function Heatmap({ v }: { v: HeatmapVisualization }) {
  const flat = v.values.flat().filter((d): d is number => d !== null && d !== undefined);
  const maxAbs = Math.max(...flat.map(Math.abs), 0) || 1;
  const diverging = flat.some((d) => d < 0);
  return (
    <div className="achat-heatmap-wrap">
      <table className="achat-heatmap" aria-label={v.title}>
        <thead>
          <tr>
            <th scope="col" />
            {v.columns.map((c) => (
              <th scope="col" key={c} title={c}>{axisLabel(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {v.rows.map((row, ri) => (
            <tr key={row}>
              <th scope="row" title={row}>{row}</th>
              {v.values[ri].map((value, ci) => {
                const strength = value === null || value === undefined ? 0 : Math.abs(value) / maxAbs;
                const tone = diverging && (value ?? 0) < 0 ? "var(--bad)" : "var(--accent)";
                return (
                  <td
                    key={ci}
                    title={`${row} — ${v.columns[ci]}: ${fmt(value, v.unit)}`}
                    style={{
                      background: value ? `color-mix(in srgb, ${tone} ${Math.round(10 + strength * 72)}%, transparent)` : undefined,
                    }}
                    className={strength > 0.55 ? "is-strong" : ""}
                  >
                    {value === null || value === undefined ? "—" : fmt(value)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
      {visualization.type === "heatmap" ? (
        <Heatmap v={visualization} />
      ) : visualization.type === "line" ? (
        <Line v={visualization} />
      ) : visualization.type === "donut" ? (
        <Donut v={visualization} />
      ) : visualization.type === "horizontal_bar" ? (
        <HorizontalBars v={visualization} />
      ) : (
        <VerticalBars v={visualization} />
      )}
    </figure>
  );
}

/** vários números lado a lado (resumo de faturado: trabalhadas, faturadas...) */
export function KpiGrid({ items }: { items: KpiVisualization[] }) {
  return (
    <div className="achat-kpis">
      {items.map((k) => (
        <div className="achat-kpi-card" key={k.title}>
          <span className="achat-kpi-card-label">{k.title.split(" — ")[0]}</span>
          <span className="achat-kpi-card-value">
            {fmt(k.value)}
            {k.unit && <small>{k.unit}</small>}
          </span>
        </div>
      ))}
    </div>
  );
}

// --- tabela --------------------------------------------------------------------

export type SortState = { column: number; descending: boolean } | null;

/** ordena sem mexer no original; vazio sempre por último */
export function sortRows(rows: AnalyticsTable["rows"], sort: SortState): AnalyticsTable["rows"] {
  if (!sort) return rows;
  const { column, descending } = sort;
  const empty = (v: unknown) => v === null || v === undefined || v === "";
  return [...rows].sort((a, b) => {
    const x = a[column];
    const y = b[column];
    if (empty(x) && empty(y)) return 0;
    if (empty(x)) return 1;
    if (empty(y)) return -1;
    const cmp =
      typeof x === "number" && typeof y === "number"
        ? x - y
        : String(x).localeCompare(String(y), "pt-BR", { sensitivity: "base", numeric: true });
    return descending ? -cmp : cmp;
  });
}

async function downloadXlsx(table: AnalyticsTable): Promise<void> {
  const res = await fetch("/analytics/chat/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: table.title,
      columns: table.columns,
      column_types: table.column_types ?? null,
      rows: table.rows,
      totals: table.totals ?? null,
    }),
  });
  if (!res.ok) throw new Error(res.status === 401 ? "Sessão expirada" : "Falha ao gerar o Excel");
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "tabela.xlsx";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function AnalyticsTableView({ table, defaultOpen = false }: { table: AnalyticsTable; defaultOpen?: boolean }) {
  const [sort, setSort] = useState<SortState>(null);
  const [exporting, setExporting] = useState<"idle" | "busy" | "error">("idle");
  const rows = useMemo(() => sortRows(table.rows, sort), [table.rows, sort]);
  const types = table.column_types ?? [];
  const numeric = (i: number) => (types[i] ? types[i] !== "text" : typeof table.rows[0]?.[i] === "number");

  // 1º clique: maior→menor; 2º: menor→maior; 3º: ordem original
  const toggleSort = (column: number) =>
    setSort((s) => (s?.column !== column ? { column, descending: true } : s.descending ? { column, descending: false } : null));

  const exportTable = async () => {
    setExporting("busy");
    try {
      await downloadXlsx(table);
      setExporting("idle");
    } catch {
      setExporting("error");
    }
  };

  return (
    <details className="achat-table" open={defaultOpen}>
      <summary>
        Ver tabela com {table.rows.length} {table.rows.length === 1 ? "linha" : "linhas"}
        {table.truncated ? " (só as primeiras)" : ""}
      </summary>
      <div className="achat-table-toolbar">
        <span className="achat-table-title">{table.title}</span>
        <button type="button" className="achat-export" onClick={exportTable} disabled={exporting === "busy"}>
          <Download size={14} aria-hidden="true" />
          {exporting === "busy" ? "Gerando…" : exporting === "error" ? "Falhou — tentar de novo" : "Baixar Excel"}
        </button>
      </div>
      <div className="achat-table-wrap">
        <table className="kpi-table">
          <thead>
            <tr>
              {table.columns.map((column, i) => (
                <th
                  key={`${column}-${i}`}
                  className={numeric(i) ? "is-num" : ""}
                  aria-sort={sort?.column === i ? (sort.descending ? "descending" : "ascending") : "none"}
                >
                  <button type="button" className="achat-sort" onClick={() => toggleSort(i)}>
                    {column}
                    <span aria-hidden="true">{sort?.column === i ? (sort.descending ? " ↓" : " ↑") : ""}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, j) => (
                  <td key={j} className={numeric(j) ? "is-num" : ""}>{formatCell(cell, types[j])}</td>
                ))}
              </tr>
            ))}
          </tbody>
          {table.totals && (
            <tfoot>
              <tr>
                {table.totals.map((cell, j) => (
                  <td key={j} className={numeric(j) ? "is-num" : ""}>{formatCell(cell, types[j])}</td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </details>
  );
}
