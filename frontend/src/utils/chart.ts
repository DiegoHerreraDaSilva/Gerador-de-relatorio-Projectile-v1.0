import type { Group } from "../api/types";
import { computeGroupTotals } from "./calc";

// paleta variada (não só o teal da marca) pra diferenciar bem cada grupo num
// relatório com muitos grupos — mantém o teal como primeira cor por identidade,
// intercalando com tons distintos entre si (contraste testado, sem repetir hue)
const PALETTE = [
  "#3bbdc9", "#e8934a", "#7c6fd8", "#5ab562", "#e05c74",
  "#d8b64a", "#4a90d8", "#c766c2", "#8a9a4a", "#d87f4a",
];

function colorFor(index: number): string {
  return PALETTE[index % PALETTE.length];
}

function chartableGroups(groups: Group[]): Array<{ name: string; value: number }> {
  return groups
    .map((g) => ({ name: g.name || "Sem nome", ...computeGroupTotals(g) }))
    .filter((g) => g.hasRealActivities && g.resultado > 0)
    .map((g) => ({ name: g.name, value: g.resultado }));
}

function setupCanvas(canvas: HTMLCanvasElement, width: number, height: number): CanvasRenderingContext2D {
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D não suportado.");
  ctx.clearRect(0, 0, width, height);
  return ctx;
}

function drawEmptyState(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.fillStyle = "#8a97a8";
  ctx.font = "28px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("Sem horas apontadas pra exibir no gráfico ainda.", width / 2, height / 2);
}

function drawBarChart(ctx: CanvasRenderingContext2D, width: number, height: number, data: Array<{ name: string; value: number }>) {
  const padding = 40;
  const minLabelWidth = 200;
  const maxLabelWidth = 420;

  ctx.font = "bold 26px system-ui, sans-serif";
  const widestLabel = Math.max(...data.map((d) => ctx.measureText(d.name).width));
  const labelWidth = Math.min(maxLabelWidth, Math.max(minLabelWidth, widestLabel + 16));

  const chartLeft = padding + labelWidth;
  const chartRight = width - padding - 90;
  const chartWidth = chartRight - chartLeft;
  const rowHeight = (height - padding * 2) / data.length;
  const maxValue = Math.max(...data.map((d) => d.value));

  ctx.textBaseline = "middle";

  data.forEach((d, i) => {
    const y = padding + rowHeight * i + rowHeight / 2;
    const barHeight = Math.min(rowHeight * 0.55, 46);
    const barWidth = maxValue > 0 ? (d.value / maxValue) * chartWidth : 0;

    ctx.fillStyle = "#2a3542";
    ctx.textAlign = "right";
    ctx.fillText(d.name, chartLeft - 16, y);

    ctx.fillStyle = colorFor(i);
    ctx.fillRect(chartLeft, y - barHeight / 2, barWidth, barHeight);

    ctx.fillStyle = "#2a3542";
    ctx.textAlign = "left";
    ctx.fillText(d.value.toFixed(1), chartLeft + barWidth + 14, y);
  });
}

function drawPieChart(ctx: CanvasRenderingContext2D, width: number, height: number, data: Array<{ name: string; value: number }>) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const cx = width * 0.22;
  const cy = height / 2;
  const radius = Math.min(cx, height / 2) - 40;

  let angle = -Math.PI / 2;
  data.forEach((d, i) => {
    const slice = total > 0 ? (d.value / total) * Math.PI * 2 : 0;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, angle, angle + slice);
    ctx.closePath();
    ctx.fillStyle = colorFor(i);
    ctx.fill();
    angle += slice;
  });

  const legendX = width * 0.42;
  const legendPadding = 30;
  const legendRowHeight = Math.min(46, (height - legendPadding * 2) / data.length);
  const legendCenteredTop = height / 2 - (data.length * legendRowHeight) / 2;
  const legendTop = Math.max(legendPadding, legendCenteredTop);
  ctx.font = "bold 24px system-ui, sans-serif";
  ctx.textBaseline = "middle";
  ctx.textAlign = "left";
  data.forEach((d, i) => {
    const y = legendTop + i * legendRowHeight;
    const pct = total > 0 ? (d.value / total) * 100 : 0;
    ctx.fillStyle = colorFor(i);
    ctx.fillRect(legendX, y - 12, 24, 24);
    ctx.fillStyle = "#2a3542";
    ctx.fillText(`${d.name} (${pct.toFixed(0)}%)`, legendX + 34, y);
  });
}

export function drawGroupsChart(canvas: HTMLCanvasElement, groups: Group[], type: "bar" | "pie") {
  const width = 1000;
  const height = 560;
  const ctx = setupCanvas(canvas, width, height);
  const data = chartableGroups(groups);

  if (data.length === 0) {
    drawEmptyState(ctx, width, height);
    return;
  }

  if (type === "pie") {
    drawPieChart(ctx, width, height, data);
  } else {
    drawBarChart(ctx, width, height, data);
  }
}
