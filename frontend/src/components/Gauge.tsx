type Props = {
  value: number | null;
  metaValue: number;
  metaType: "min" | "max";
  gaugeMax: number;
  label: string;
};

const CX = 100;
const CY = 100;
const R = 76;
const STROKE = 26;

function polarToCartesian(angleDeg: number) {
  const angleRad = ((angleDeg - 180) * Math.PI) / 180;
  return { x: CX + R * Math.cos(angleRad), y: CY + R * Math.sin(angleRad) };
}

function arcPath(startDeg: number, endDeg: number): string {
  if (endDeg <= startDeg) return "";
  const start = polarToCartesian(startDeg);
  const end = polarToCartesian(endDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${R} ${R} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

// zonas coloridas: pra meta "mínimo" (maior é melhor), vermelho fica antes da
// meta e verde depois; pra meta "máximo" (menor é melhor), é o oposto — uma
// faixa amarela fina em volta da meta nos dois casos, marcando a transição.
function buildZones(metaValue: number, metaType: "min" | "max", gaugeMax: number) {
  const metaDeg = Math.min(180, (metaValue / gaugeMax) * 180);
  const bandDeg = Math.min(10, metaDeg * 0.15);
  if (metaType === "min") {
    return [
      { color: "var(--bad)", from: 0, to: Math.max(0, metaDeg - bandDeg) },
      { color: "var(--warn)", from: Math.max(0, metaDeg - bandDeg), to: metaDeg },
      { color: "var(--ok)", from: metaDeg, to: 180 },
    ];
  }
  return [
    { color: "var(--ok)", from: 0, to: Math.max(0, metaDeg - bandDeg) },
    { color: "var(--warn)", from: Math.max(0, metaDeg - bandDeg), to: metaDeg },
    { color: "var(--bad)", from: metaDeg, to: 180 },
  ];
}

export function Gauge({ value, metaValue, metaType, gaugeMax, label }: Props) {
  const zones = buildZones(metaValue, metaType, gaugeMax);
  const clamped = value === null ? 0 : Math.max(0, Math.min(gaugeMax, value));
  const needleDeg = (clamped / gaugeMax) * 180;
  const needleTip = polarToCartesian(needleDeg);

  return (
    <div className="gauge">
      <svg viewBox="0 0 200 108" className="gauge-svg">
        {zones.map((z, i) => (
          <path
            key={i}
            d={arcPath(z.from, z.to)}
            fill="none"
            stroke={z.color}
            strokeWidth={STROKE}
            strokeLinecap="butt"
          />
        ))}
        {value !== null && (
          <>
            <line x1={CX} y1={CY} x2={needleTip.x} y2={needleTip.y} stroke="var(--text)" strokeWidth={2.5} strokeLinecap="round" />
            <circle cx={CX} cy={CY} r={5} fill="var(--text)" />
          </>
        )}
      </svg>
      <div className="gauge-value">{value === null ? "—" : label}</div>
    </div>
  );
}
