import { fmtNum } from "../../utils/fmt";

const WEEKDAY_LABELS = ["S", "T", "Q", "Q", "S", "S", "D"];
const MONTH_NAMES = [
  "janeiro", "fevereiro", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

type DayCell = {
  date: string;
  hours: number | null;
  state: "worked" | "gap" | "off" | "future" | "outside";
  outlier: boolean;
};

/** "YYYY-MM-DD" -> Date ao meio-dia: evita o deslocamento de um dia que
 * `new Date("2026-08-03")` causa em fuso negativo (o parse é UTC). */
function localDate(iso: string): Date {
  return new Date(`${iso}T12:00:00`);
}

function iso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

/** Índice 0=segunda (o `getDay()` nativo devolve 0=domingo). */
function weekdayIndex(date: Date): number {
  return (date.getDay() + 6) % 7;
}

function buildMonth(
  year: number,
  month: number,
  totals: Map<string, number>,
  businessDays: Set<string>,
  gapDays: Set<string>,
  outliers: Set<string>,
  today: string,
  rangeStart: string,
  rangeEnd: string
): DayCell[] {
  const first = new Date(year, month, 1, 12);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: DayCell[] = [];

  // preenche a semana até a posição real do dia 1 (grade de mês de verdade,
  // não uma fita corrida — a posição no calendário é parte da informação)
  for (let i = 0; i < weekdayIndex(first); i++) {
    cells.push({ date: "", hours: null, state: "outside", outlier: false });
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(year, month, d, 12);
    const key = iso(date);
    const hours = totals.get(key) ?? null;
    let state: DayCell["state"];
    if (key < rangeStart || key > rangeEnd) state = "outside";
    else if (key > today) state = "future";
    else if (hours !== null && hours > 0) state = "worked";
    else if (gapDays.has(key)) state = "gap";
    else if (businessDays.has(key)) state = "future"; // dia útil de hoje ainda em curso
    else state = "off";
    cells.push({ date: key, hours, state, outlier: outliers.has(key) });
  }
  return cells;
}

/** Calendário-heatmap em grade de mês real.
 *
 * Substitui o gráfico de linha "Horas por dia", que num mês recém-começado
 * desenhava um ponto solto no meio de um card vazio. Aqui o mês inteiro
 * aparece desde o dia 1: o que ainda não aconteceu fica fantasma, o dia útil
 * encerrado sem apontamento fica contornado, e feriado/fim de semana fica
 * neutro. Um dia sem apontamento passa a ser visível — e é exatamente o que
 * uma tabela de lançamentos é incapaz de mostrar, porque ali ele é uma linha
 * que não existe.
 *
 * A intensidade é `horas / referência do dia`; sem referência de jornada cai
 * pro máximo do próprio período, e a legenda diz isso. */
export function CalendarHeat({
  totals,
  businessDays,
  gapDays,
  holidays,
  outlierDays,
  today,
  rangeStart,
  rangeEnd,
  referenceHours,
  selectedDate,
  onSelectDate,
}: {
  totals: Map<string, number>;
  businessDays: string[];
  gapDays: string[];
  holidays: string[];
  outlierDays: string[];
  today: string;
  rangeStart: string;
  rangeEnd: string;
  referenceHours: number | null;
  selectedDate: string | null;
  onSelectDate: (date: string) => void;
}) {
  const businessSet = new Set(businessDays);
  const gapSet = new Set(gapDays);
  const holidaySet = new Set(holidays);
  const outlierSet = new Set(outlierDays);

  const maxHours = Math.max(...Array.from(totals.values()), 0);
  const scale = referenceHours && referenceHours > 0 ? referenceHours : maxHours || 1;

  // meses que o período cobre
  const months: { year: number; month: number }[] = [];
  const cursor = localDate(rangeStart);
  const last = localDate(rangeEnd);
  while (cursor <= last) {
    months.push({ year: cursor.getFullYear(), month: cursor.getMonth() });
    cursor.setMonth(cursor.getMonth() + 1, 1);
  }

  return (
    // grade compacta já a partir de 2 meses: em tamanho cheio, 3 meses
    // quebravam em 2 linhas e faziam o card passar de 900px de altura,
    // abrindo um vão enorme ao lado da coluna da direita
    <div className={`calheat ${months.length > 1 ? "calheat--compact" : ""}`}>
      <div className="calheat-months">
      {months.map(({ year, month }) => {
        const cells = buildMonth(
          year, month, totals, businessSet, gapSet, outlierSet, today, rangeStart, rangeEnd
        );
        return (
          <div className="calheat-month" key={`${year}-${month}`}>
            <div className="calheat-month-name">
              {MONTH_NAMES[month]}
              {months.length > 1 && ` ${String(year).slice(2)}`}
            </div>
            <div className="calheat-grid">
              {WEEKDAY_LABELS.map((label, i) => (
                <div className="calheat-weekday" key={`wd-${i}`} aria-hidden="true">
                  {label}
                </div>
              ))}
              {cells.map((cell, i) => {
                if (cell.state === "outside" && !cell.date) {
                  return <div className="calheat-cell calheat-cell--blank" key={`b-${i}`} />;
                }
                const dayNumber = Number(cell.date.slice(8, 10));
                const intensity =
                  cell.hours && cell.hours > 0 ? Math.min(1, cell.hours / scale) : 0;
                const isHoliday = holidaySet.has(cell.date);
                const title = [
                  cell.date.split("-").reverse().join("/"),
                  cell.state === "worked" ? `${fmtNum(cell.hours ?? 0)} h` : null,
                  cell.state === "gap" ? "dia útil sem apontamento" : null,
                  isHoliday ? "feriado nacional" : null,
                  cell.state === "off" && !isHoliday ? "fim de semana" : null,
                  cell.state === "future" ? "ainda não encerrado" : null,
                  cell.outlier ? "fora do seu padrão" : null,
                ]
                  .filter(Boolean)
                  .join(" · ");

                const clickable = cell.state === "worked";
                const className = [
                  "calheat-cell",
                  `calheat-cell--${cell.state}`,
                  cell.outlier ? "calheat-cell--outlier" : "",
                  selectedDate === cell.date ? "calheat-cell--selected" : "",
                ]
                  .filter(Boolean)
                  .join(" ");

                const style =
                  cell.state === "worked"
                    ? { opacity: 0.25 + intensity * 0.75 }
                    : undefined;

                return clickable ? (
                  <button
                    type="button"
                    key={cell.date}
                    className={className}
                    style={style}
                    title={title}
                    aria-label={title}
                    aria-pressed={selectedDate === cell.date}
                    onClick={() => onSelectDate(cell.date)}
                  >
                    {dayNumber}
                  </button>
                ) : (
                  <div key={cell.date || `x-${i}`} className={className} title={title}>
                    {dayNumber}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
      </div>

      <div className="calheat-legend">
        <span className="calheat-legend-item">
          <span className="calheat-swatch calheat-cell--worked" style={{ opacity: 1 }} />
          apontado
        </span>
        <span className="calheat-legend-item">
          <span className="calheat-swatch calheat-cell--gap" />
          dia útil sem apontamento
        </span>
        <span className="calheat-legend-item">
          <span className="calheat-swatch calheat-cell--off" />
          fim de semana / feriado
        </span>
        <span className="calheat-legend-item">
          <span className="calheat-swatch calheat-cell--future" />
          não encerrado
        </span>
        <span className="calheat-legend-note muted">
          {referenceHours && referenceHours > 0
            ? `intensidade = horas ÷ ${fmtNum(referenceHours)} h de referência`
            : `intensidade relativa ao maior dia do período (${fmtNum(maxHours)} h)`}
        </span>
      </div>
    </div>
  );
}
