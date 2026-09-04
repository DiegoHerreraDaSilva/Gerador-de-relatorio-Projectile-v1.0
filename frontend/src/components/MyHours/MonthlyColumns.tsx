import { useState } from "react";
import { fmtNum } from "../../utils/fmt";
import type { MonthlyPoint } from "../../utils/myHours";

const MONTH_ABBR = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function label(month: string): string {
  const [year, m] = month.split("-");
  return `${MONTH_ABBR[Number(m) - 1]}/${year.slice(2)}`;
}

/** Tendência de 13 meses em COLUNAS, não em linha.
 *
 * Linha foi rejeitada por um motivo concreto: ligar ago (126,9 h) a set
 * (6,0 h, dia 4 do mês) desenha um despencar catastrófico que é só o mês em
 * curso — o pior erro de leitura possível desta tela. Coluna separada, com o
 * mês corrente hachurado e rotulado "parcial", não sugere continuidade.
 *
 * Ignora o seletor de período de propósito: com "Mês atual" selecionado, uma
 * tendência restrita ao recorte mostraria uma coluna só.
 *
 * O toggle h/mês ↔ h/dia útil é obrigatório porque o tamanho do mês distorce
 * a comparação — jun (94,7 h em 21 dias úteis) vs mar (132,7 h em 22) parece
 * uma queda de 29% que em grande parte é calendário. */
export function MonthlyColumns({ series }: { series: MonthlyPoint[] }) {
  const [perDay, setPerDay] = useState(false);

  const valueOf = (m: MonthlyPoint) => {
    if (m.no_data) return 0;
    if (!perDay) return m.hours;
    const days = m.business_days_closed || m.business_days;
    return days > 0 ? Math.round((m.hours / days) * 100) / 100 : 0;
  };

  const withData = series.filter((m) => !m.no_data);
  const max = Math.max(...series.map(valueOf), 1);
  const closed = withData.filter((m) => !m.partial).map(valueOf).sort((a, b) => a - b);
  const medianClosed =
    closed.length >= 3
      ? closed.length % 2
        ? closed[(closed.length - 1) / 2]
        : (closed[closed.length / 2 - 1] + closed[closed.length / 2]) / 2
      : null;

  const unit = perDay ? "h/dia útil" : "h";

  return (
    <div className="monthcols">
      <div className="monthcols-toolbar">
        <div className="monthcols-toggle" role="group" aria-label="Unidade da tendência">
          <button
            type="button"
            className={!perDay ? "active" : ""}
            aria-pressed={!perDay}
            onClick={() => setPerDay(false)}
          >
            h/mês
          </button>
          <button
            type="button"
            className={perDay ? "active" : ""}
            aria-pressed={perDay}
            onClick={() => setPerDay(true)}
          >
            h/dia útil
          </button>
        </div>
        {medianClosed !== null && (
          <span className="muted">
            Mediana dos meses fechados: {fmtNum(medianClosed)} {unit}
          </span>
        )}
      </div>

      <div className="monthcols-plot">
        {medianClosed !== null && (
          <div
            className="monthcols-median"
            style={{ bottom: `${(medianClosed / max) * 100}%` }}
            aria-hidden="true"
          />
        )}
        {series.map((m) => {
          const value = valueOf(m);
          const height = m.no_data ? 0 : Math.max(2, (value / max) * 100);
          const title = m.no_data
            ? `${label(m.month)}: sem informação`
            : `${label(m.month)}: ${fmtNum(m.hours)} h em ${m.days_worked} dias` +
              ` (${m.business_days} dias úteis)${m.partial ? " · Mês em curso" : ""}`;
          return (
            <div className="monthcols-col" key={m.month} title={title}>
              <div className="monthcols-bar-area">
                {m.no_data ? (
                  <div className="monthcols-nodata" aria-hidden="true" />
                ) : (
                  <div
                    className={`monthcols-bar ${m.partial ? "monthcols-bar--partial" : ""}`}
                    style={{ height: `${height}%` }}
                  />
                )}
              </div>
              <div className="monthcols-value">
                {m.no_data ? "—" : fmtNum(value)}
              </div>
              <div className={`monthcols-label ${m.partial ? "monthcols-label--partial" : ""}`}>
                {label(m.month)}
              </div>
            </div>
          );
        })}
      </div>

      <table className="sr-only">
        <caption>Horas por mês nos últimos 13 meses</caption>
        <thead>
          <tr><th scope="col">Mês</th><th scope="col">Horas</th><th scope="col">Dias com apontamento</th></tr>
        </thead>
        <tbody>
          {series.map((m) => (
            <tr key={m.month}>
              <td>{label(m.month)}{m.partial ? " (parcial)" : ""}</td>
              <td>{m.no_data ? "Sem informação" : `${fmtNum(m.hours)} h`}</td>
              <td>{m.no_data ? "—" : m.days_worked}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="monthcols-note muted">
        Mês em curso aparece hachurado e não entra na mediana. “—” é mês sem
        informação, não mês de zero hora.
      </p>
    </div>
  );
}
