import { fmtNum } from "../../utils/fmt";
import { median, type DayWindow } from "../../utils/myHours";

const AXIS_START = 6 * 60; // 06:00
const AXIS_END = 20 * 60; // 20:00
const AXIS_TICKS = [6, 8, 10, 12, 14, 16, 18, 20];

function hhmm(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(
    Math.round(minutes % 60)
  ).padStart(2, "0")}`;
}

/** Faixas entrada→saída por dia, a partir de `ttimebit.pStart`/`pEnd`.
 *
 * Este é o sinal mais subaproveitado do banco: medido 100% preenchido nos
 * 11.278 lançamentos de 2026 e completamente ignorado pelo dashboard antigo.
 *
 * O valor analítico está na diferença entre a JANELA presente (primeira
 * entrada até última saída) e as horas APONTADAS: com janela mediana de
 * 08:47–16:05 (~7,3 h) e 6,0 h apontadas, sobram ~1,3 h que incluem o
 * intervalo. Se o intervalo real é 1 h, está tudo certo; se é 30 min, faltam
 * ~40 min/dia — ~14 h/mês não apontadas. Nenhuma tabela de lançamentos
 * responde isso, porque ali só existe o total do dia.
 *
 * Deliberadamente NÃO chama a diferença de "hora perdida": almoço é legítimo.
 * O rótulo é "não apontadas (inclui intervalo)". */
export function DayWindows({ windows }: { windows: DayWindow[] }) {
  if (windows.length === 0) {
    return (
      <p className="muted">
        Nenhum lançamento com horário válido no período — sem isso a janela do
        dia não pode ser calculada (horário não é inferido a partir do total
        de horas).
      </p>
    );
  }

  const medianStart = median(windows.map((w) => w.startMin));
  const medianEnd = median(windows.map((w) => w.endMin));
  const medianSpan = median(windows.map((w) => w.spanHours));
  const medianLogged = median(windows.map((w) => w.loggedHours));
  const uncovered =
    medianSpan !== null && medianLogged !== null
      ? Math.round((medianSpan - medianLogged) * 100) / 100
      : null;

  const left = (minutes: number) =>
    `${((Math.max(AXIS_START, minutes) - AXIS_START) / (AXIS_END - AXIS_START)) * 100}%`;
  const width = (from: number, to: number) =>
    `${((Math.min(AXIS_END, to) - Math.max(AXIS_START, from)) / (AXIS_END - AXIS_START)) * 100}%`;

  return (
    <div className="daywin">
      {medianStart !== null && medianEnd !== null && (
        <p className="daywin-summary">
          Janela mediana <strong>{hhmm(medianStart)}–{hhmm(medianEnd)}</strong>
          {medianSpan !== null && <> ({fmtNum(medianSpan)} h)</>}
          {medianLogged !== null && <> · Apontado <strong>{fmtNum(medianLogged)} h</strong></>}
          {uncovered !== null && uncovered > 0 && (
            <> · <strong>{fmtNum(uncovered)} h</strong> não apontadas (inclui intervalo)</>
          )}
        </p>
      )}

      <div className="daywin-axis" aria-hidden="true">
        {AXIS_TICKS.map((hour) => (
          <span
            className="daywin-tick"
            key={hour}
            style={{ left: left(hour * 60) }}
          >
            {String(hour).padStart(2, "0")}h
          </span>
        ))}
      </div>

      <div
        className="daywin-rows"
        role="img"
        aria-label={
          medianStart !== null && medianEnd !== null
            ? `Janela de trabalho por dia, mediana de ${hhmm(medianStart)} a ${hhmm(medianEnd)}`
            : "Janela de trabalho por dia"
        }
      >
        {windows.length > 1 && medianStart !== null && (
          <div className="daywin-guide" style={{ left: left(medianStart) }} aria-hidden="true" />
        )}
        {windows.length > 1 && medianEnd !== null && (
          <div className="daywin-guide" style={{ left: left(medianEnd) }} aria-hidden="true" />
        )}
        {windows.map((w) => (
          <div className="daywin-row" key={w.date}>
            <span className="daywin-date">{w.date.slice(8, 10)}/{w.date.slice(5, 7)}</span>
            <span className="daywin-track">
              <span
                className="daywin-span"
                style={{ left: left(w.startMin), width: width(w.startMin, w.endMin) }}
                title={`${w.date.split("-").reverse().join("/")}: ${hhmm(w.startMin)}–${hhmm(
                  w.endMin
                )} (${fmtNum(w.spanHours)} h de janela, ${fmtNum(w.loggedHours)} h apontadas)`}
              />
            </span>
            <span className="daywin-hours">{fmtNum(w.loggedHours)} h</span>
          </div>
        ))}
      </div>
    </div>
  );
}
