import { fmtNum } from "../../utils/fmt";

/** Bullet horizontal: barra = realizado, marcador = referência até hoje,
 * faixa de fundo = referência do período inteiro.
 *
 * Substitui o card "Total de horas" com número solto. Um total sem âncora não
 * responde nada — "126,9 h" só informa ao lado de "de 126,0 h esperadas".
 *
 * A barra NÃO clampa em 100%: hora além do esperado transborda o alvo de
 * propósito, porque excedente é sinal, não erro de renderização.
 *
 * `expectedClosed`/`expectedPeriod` chegam `null` quando não há referência de
 * jornada — nesse caso nada de marcador ou faixa é desenhado, e o componente
 * mostra só o realizado. `allowsPercentage` (só jornada de contrato) é o que
 * autoriza exibir o percentual de aderência. */
export function BulletBar({
  actual,
  expectedClosed,
  expectedPeriod,
  allowsPercentage,
  referenceLabel,
}: {
  actual: number;
  expectedClosed: number | null;
  expectedPeriod: number | null;
  allowsPercentage: boolean;
  referenceLabel: string;
}) {
  // escala: o maior entre realizado e alvo do período, com folga de 8% pro
  // marcador não colar na borda quando realizado == esperado
  const scaleMax = Math.max(actual, expectedPeriod ?? 0, 1) * 1.08;
  const pct = (value: number) => `${Math.min(100, (value / scaleMax) * 100)}%`;

  const adherence =
    allowsPercentage && expectedClosed && expectedClosed > 0 ? actual / expectedClosed : null;

  const ariaLabel = expectedClosed
    ? `${fmtNum(actual)} horas apontadas de ${fmtNum(expectedClosed)} horas de referência até hoje`
    : `${fmtNum(actual)} horas apontadas, sem referência de jornada`;

  return (
    <div className="bullet" role="img" aria-label={ariaLabel}>
      <div className="bullet-track">
        {expectedPeriod !== null && (
          <div
            className="bullet-band"
            style={{ width: pct(expectedPeriod) }}
            title={`Referência do período inteiro: ${fmtNum(expectedPeriod)} h`}
          />
        )}
        <div className="bullet-fill" style={{ width: pct(actual) }} />
        {expectedClosed !== null && expectedClosed > 0 && (
          <div
            className={`bullet-marker ${allowsPercentage ? "" : "bullet-marker--estimated"}`}
            style={{ left: pct(expectedClosed) }}
            title={
              allowsPercentage
                ? `Esperado até hoje: ${fmtNum(expectedClosed)} h`
                : `Referência estimada até hoje: ${fmtNum(expectedClosed)} h`
            }
          />
        )}
      </div>

      <div className="bullet-legend">
        <span className="bullet-legend-item">
          <span className="bullet-swatch bullet-swatch--fill" />
          apontado <strong>{fmtNum(actual)} h</strong>
        </span>
        {expectedClosed !== null && expectedClosed > 0 ? (
          <span className="bullet-legend-item">
            <span
              className={`bullet-swatch bullet-swatch--marker ${
                allowsPercentage ? "" : "bullet-swatch--estimated"
              }`}
            />
            {allowsPercentage ? "esperado até hoje" : "referência estimada até hoje"}{" "}
            <strong>{fmtNum(expectedClosed)} h</strong>
            {adherence !== null && <> · <strong>{Math.round(adherence * 100)}%</strong></>}
          </span>
        ) : (
          <span className="bullet-legend-item muted">{referenceLabel}</span>
        )}
        {expectedPeriod !== null && (
          <span className="bullet-legend-item muted">
            período inteiro {fmtNum(expectedPeriod)} h
          </span>
        )}
      </div>
    </div>
  );
}
