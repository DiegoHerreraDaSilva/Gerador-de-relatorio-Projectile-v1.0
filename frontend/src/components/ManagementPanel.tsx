import { useEffect, useState } from "react";
import { Clock, FileText, DollarSign, RefreshCw, MailSearch, LayoutDashboard } from "lucide-react";
import { KpiCard } from "./KpiCard";
import { ManagementFilters } from "./ManagementFilters";
import { EvolutionChart } from "./EvolutionChart";
import { SortableTh } from "./SortableTh";
import { PageHeader } from "./PageHeader";
import { useSortableRows } from "../hooks/useSortableRows";
import { fmtNum } from "../utils/fmt";
import { useManagementStore, round2 } from "../store/useManagementStore";
import type { MonthRow } from "../store/useManagementStore";

function pctClass(value: number | null, metaValue: number, metaType: "min" | "max"): string {
  if (value === null) return "";
  const pct = value * 100;
  const good = metaType === "min" ? pct >= metaValue : pct <= metaValue;
  if (good) return "good";
  const nearMiss = metaType === "min" ? pct >= metaValue * 0.85 : pct <= metaValue * 1.15;
  return nearMiss ? "warn" : "bad";
}

function fmtPct(value: number | null): string {
  return value === null ? "—" : `${fmtNum(value * 100)}%`;
}

// Faturado/Performance/Elaboração vêm de e-mail/manual, por PROJETO — sem
// dimensão de pessoa (ver _build_month_row no backend). Quando o filtro de
// Pessoa está ativo, o backend já manda esses campos como `null`; aqui só
// explicamos o "—" resultante em vez de deixá-lo parecer "sem dado".
const NO_PERSON_DIMENSION_TITLE = "Faturado/Performance não têm recorte por pessoa — são por projeto inteiro.";

type CheckEmailsResult = { messages_found: number; samples_added: number; duplicates_found: number; skipped: number };

async function checkEmails(): Promise<CheckEmailsResult> {
  const res = await fetch("/management/kpis/check-emails", { method: "POST" });
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
  return res.json();
}

export function ManagementPanel() {
  const rows = useManagementStore((s) => s.rows);
  const nonbillableBreakdown = useManagementStore((s) => s.nonbillableBreakdown);
  const selectedMonths = useManagementStore((s) => s.selectedMonths);
  const persons = useManagementStore((s) => s.persons);
  const error = useManagementStore((s) => s.error);
  const refreshing = useManagementStore((s) => s.refreshing);
  const load = useManagementStore((s) => s.load);
  const setError = useManagementStore((s) => s.setError);

  const [checkingEmails, setCheckingEmails] = useState(false);
  const [checkEmailsMessage, setCheckEmailsMessage] = useState("");

  useEffect(() => {
    load();
  }, [load]);

  const handleCheckEmails = async () => {
    setCheckingEmails(true);
    setCheckEmailsMessage("");
    try {
      const result = await checkEmails();
      const duplicateNote =
        result.duplicates_found > 0
          ? ` ${result.duplicates_found} duplicata(s) ignorada(s) (não contou horas).`
          : "";
      setCheckEmailsMessage(
        (result.samples_added > 0
          ? `${result.samples_added} relatório(s) novo(s) processado(s).`
          : result.messages_found > 0
            ? `${result.messages_found} e-mail(s) verificado(s), nenhum gerou dado novo.`
            : "Nenhum relatório enviado.") + duplicateNote
      );
      await load(true, true);
    } catch {
      setCheckEmailsMessage("Não consegui verificar os e-mails agora. Tenta de novo em instantes.");
    } finally {
      setCheckingEmails(false);
    }
  };

  // Competência filtra só a exibição/agregação — os 12 meses continuam
  // carregados na store, sem novo fetch, só muda o que entra nas somas.
  //
  // `rows ?? []` (em vez de um `return` antes disto) é obrigatório: os
  // `useSortableRows` mais abaixo são Hooks, e Hooks não podem vir depois de
  // um `return` condicional — o número de Hooks chamados precisa ser IGUAL
  // em todo render. Antes disto, o primeiro render (rows ainda null,
  // carregando) chamava menos Hooks que o render seguinte (rows populado),
  // e o React quebra o componente inteiro nessa transição — como não existe
  // error boundary alguma, a página inteira sumia. Só não estourava quando
  // `rows` já vinha populado no MESMO carregamento (Zustand mantém o dado de
  // uma visita anterior), daí o "às vezes abre, às vezes não".
  const displayRows = selectedMonths.length
    ? (rows ?? []).filter((r) => selectedMonths.includes(r.month))
    : rows ?? [];

  const totalWorked = round2(displayRows.reduce((s, r) => s + r.worked_hours, 0));
  // total de Faturadas/Perf.H só soma os meses com "Faturadas" preenchida —
  // misturar isso com o total de Trabalhadas de TODOS os meses (incluindo os
  // ainda sem input manual) dava um KPI% total sem sentido (podia até ficar
  // negativo), já que as duas somas cobririam populações de meses diferentes.
  const enteredBilled = displayRows.filter((r) => r.billed_hours !== null);
  const totalWorkedForPerf = round2(enteredBilled.reduce((s, r) => s + r.worked_hours, 0));
  const totalBilled = round2(enteredBilled.reduce((s, r) => s + (r.billed_hours ?? 0), 0));
  const totalPerf = round2(totalBilled - totalWorkedForPerf);
  const totalPerfPct = totalWorkedForPerf > 0 ? totalPerf / totalWorkedForPerf : null;

  // Faturado/Performance/Elaboração ficam `null` em TODA linha quando o
  // filtro de Pessoa está ativo (ver _build_month_row no backend) — nesse
  // caso os totais acima (enteredBilled vazio) colapsam pra 0 em vez de
  // "sem dado", o que mostraria um "0" enganoso na linha de Total. Usa esse
  // flag pra mostrar "—" em vez do 0 calculado, e pro tooltip explicativo.
  const personsFilterActive = persons.length > 0;

  const enteredDays = displayRows.filter((r) => r.elaboration_days !== null);
  const avgDays = enteredDays.length ? enteredDays.reduce((s, r) => s + (r.elaboration_days ?? 0), 0) / enteredDays.length : null;

  const totalNonbillable = round2(displayRows.reduce((s, r) => s + r.nonbillable_hours, 0));
  const totalNonbillablePct = totalWorked > 0 ? totalNonbillable / totalWorked : null;

  // segue os mesmos filtros da tela: Centro de Custo/Cliente/Projeto já vêm
  // recortados do backend (ver compute_monthly_kpis), Competência é aplicada
  // aqui do mesmo jeito que displayRows, filtrando por mês antes de somar por
  // pacote.
  const displayMonths = new Set(displayRows.map((r) => r.month));
  const packageTotals = new Map<string, number>();
  for (const row of nonbillableBreakdown) {
    if (!displayMonths.has(row.month)) continue;
    packageTotals.set(row.package, (packageTotals.get(row.package) ?? 0) + row.hours);
  }
  const packageRows = Array.from(packageTotals.entries())
    .map(([pkg, hours]) => ({ pkg, hours: round2(hours) }))
    .sort((a, b) => b.hours - a.hours);

  // ordenação clicável de cabeçalho — cada tabela tem seu próprio estado
  // (mesmo as 3 primeiras, que mostram os mesmos meses: colunas diferentes,
  // então faz sentido cada uma ordenar independente das outras). Sem coluna
  // clicada, mantém a ordem que já vinha (cronológica pros meses, maior
  // hora primeiro pra pacotes não faturáveis).
  const perfSort = useSortableRows<MonthRow>(displayRows, (r, key) => {
    if (key === "month") return r.month;
    if (key === "worked") return r.worked_hours;
    if (key === "billed") return r.billed_hours;
    if (key === "perfHours") return r.perf_hours;
    return r.perf_kpi_pct;
  });
  const elaborationSort = useSortableRows<MonthRow>(displayRows, (r, key) =>
    key === "month" ? r.month : r.elaboration_days
  );
  const nonbillableSort = useSortableRows<MonthRow>(displayRows, (r, key) => {
    if (key === "month") return r.month;
    if (key === "worked") return r.worked_hours;
    if (key === "nonbillable") return r.nonbillable_hours;
    return r.nonbillable_kpi_pct;
  });
  const packageSort = useSortableRows<{ pkg: string; hours: number }>(packageRows, (p, key) =>
    key === "pkg" ? p.pkg : p.hours
  );

  // só agora, DEPOIS de todo Hook já ter sido chamado, é seguro sair mais
  // cedo — ver o comentário grande acima de `displayRows`.
  if (!rows) {
    return (
      <div className="management-layout page-container" aria-busy={!error}>
        <PageHeader
          title="Painel de Gerência"
          description="Acompanhe horas, performance e situação dos relatórios em um único lugar."
          icon={<LayoutDashboard size={20} strokeWidth={1.8} />}
        />
        <div className="card management-panel page-state-card">
          <p className={error ? "error-text" : "muted"}>{error || "Carregando indicadores..."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="management-layout page-container">
      <PageHeader
        title="Painel de Gerência"
        description="Acompanhe horas, performance e situação dos relatórios em um único lugar."
        icon={<LayoutDashboard size={20} strokeWidth={1.8} />}
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={() => load(true, true)} disabled={refreshing}>
              <RefreshCw size={14} strokeWidth={2} className={refreshing ? "spin" : ""} />
              {refreshing ? "Atualizando..." : "Atualizar"}
            </button>
            <button type="button" className="btn-secondary" onClick={handleCheckEmails} disabled={checkingEmails}>
              <MailSearch size={14} strokeWidth={2} className={checkingEmails ? "spin" : ""} />
              {checkingEmails ? "Verificando..." : "Verificar enviados"}
            </button>
          </>
        }
        status={checkEmailsMessage ? <span className="muted">{checkEmailsMessage}</span> : undefined}
      />
      <ManagementFilters />
      <div className="management-panel">
      {error && <div className="card"><p className="error-text">{error}</p></div>}

      <div className="kpi-grid">
        <KpiCard
          icon={<Clock size={18} strokeWidth={1.8} />}
          title="Performance em Horas"
          metaText="Meta = mínimo 10%"
          gauge={{
            value: totalPerfPct === null ? null : totalPerfPct * 100,
            metaValue: 10,
            metaType: "min",
            gaugeMax: 30,
            label: fmtPct(totalPerfPct),
          }}
        >
          <thead>
            <tr>
              <SortableTh sortKey="month" activeKey={perfSort.sortKey} direction={perfSort.direction} onSort={perfSort.toggleSort}>Competência</SortableTh>
              <SortableTh sortKey="worked" activeKey={perfSort.sortKey} direction={perfSort.direction} onSort={perfSort.toggleSort}>Trabalhadas</SortableTh>
              <SortableTh sortKey="billed" activeKey={perfSort.sortKey} direction={perfSort.direction} onSort={perfSort.toggleSort}>Faturadas</SortableTh>
              <SortableTh sortKey="perfHours" activeKey={perfSort.sortKey} direction={perfSort.direction} onSort={perfSort.toggleSort}>Perf. H</SortableTh>
              <SortableTh sortKey="perfPct" activeKey={perfSort.sortKey} direction={perfSort.direction} onSort={perfSort.toggleSort}>KPI %</SortableTh>
            </tr>
          </thead>
          <tbody>
            {perfSort.sortedRows.map((r) => (
              <tr key={r.month}>
                <td>{r.month}</td>
                <td>{fmtNum(r.worked_hours)}</td>
                <td title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}>
                  {r.billed_hours === null ? "—" : fmtNum(r.billed_hours)}
                </td>
                <td title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}>
                  {r.perf_hours === null ? "—" : fmtNum(r.perf_hours)}
                </td>
                <td
                  className={`kpi-pct ${pctClass(r.perf_kpi_pct, 10, "min")}`}
                  title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}
                >
                  {fmtPct(r.perf_kpi_pct)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Total</td>
              <td>{fmtNum(totalWorkedForPerf)}</td>
              <td title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}>
                {personsFilterActive ? "—" : fmtNum(totalBilled)}
              </td>
              <td title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}>
                {personsFilterActive ? "—" : fmtNum(totalPerf)}
              </td>
              <td
                className={`kpi-pct ${pctClass(totalPerfPct, 10, "min")}`}
                title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}
              >
                {fmtPct(totalPerfPct)}
              </td>
            </tr>
          </tfoot>
        </KpiCard>

        <KpiCard
          icon={<FileText size={18} strokeWidth={1.8} />}
          title="Elaboração dos relatórios"
          metaText="Meta = máximo 5 dias úteis"
          gauge={{
            value: avgDays,
            metaValue: 5,
            metaType: "max",
            gaugeMax: 15,
            label: avgDays === null ? "—" : fmtNum(avgDays),
          }}
        >
          <thead>
            <tr>
              <SortableTh sortKey="month" activeKey={elaborationSort.sortKey} direction={elaborationSort.direction} onSort={elaborationSort.toggleSort}>Competência</SortableTh>
              <SortableTh sortKey="days" activeKey={elaborationSort.sortKey} direction={elaborationSort.direction} onSort={elaborationSort.toggleSort}>KPI (Dias)</SortableTh>
            </tr>
          </thead>
          <tbody>
            {elaborationSort.sortedRows.map((r) => (
              <tr key={r.month}>
                <td>{r.month}</td>
                <td title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}>
                  {r.elaboration_days === null ? "—" : fmtNum(r.elaboration_days)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Total</td>
              <td title={personsFilterActive ? NO_PERSON_DIMENSION_TITLE : undefined}>
                {avgDays === null ? "—" : fmtNum(avgDays)}
              </td>
            </tr>
          </tfoot>
        </KpiCard>

        <KpiCard
          icon={<DollarSign size={18} strokeWidth={1.8} />}
          title="Horas não faturáveis"
          metaText="Meta = máximo 10%"
          gauge={{
            value: totalNonbillablePct === null ? null : totalNonbillablePct * 100,
            metaValue: 10,
            metaType: "max",
            gaugeMax: 30,
            label: fmtPct(totalNonbillablePct),
          }}
        >
          <thead>
            <tr>
              <SortableTh sortKey="month" activeKey={nonbillableSort.sortKey} direction={nonbillableSort.direction} onSort={nonbillableSort.toggleSort}>Competência</SortableTh>
              <SortableTh sortKey="worked" activeKey={nonbillableSort.sortKey} direction={nonbillableSort.direction} onSort={nonbillableSort.toggleSort}>Total Horas</SortableTh>
              <SortableTh sortKey="nonbillable" activeKey={nonbillableSort.sortKey} direction={nonbillableSort.direction} onSort={nonbillableSort.toggleSort}>Horas NãoFat</SortableTh>
              <SortableTh sortKey="nonbillablePct" activeKey={nonbillableSort.sortKey} direction={nonbillableSort.direction} onSort={nonbillableSort.toggleSort}>KPI %</SortableTh>
            </tr>
          </thead>
          <tbody>
            {nonbillableSort.sortedRows.map((r) => (
              <tr key={r.month}>
                <td>{r.month}</td>
                <td>{fmtNum(r.worked_hours)}</td>
                <td>{fmtNum(r.nonbillable_hours)}</td>
                <td className={`kpi-pct ${pctClass(r.nonbillable_kpi_pct, 10, "max")}`}>{fmtPct(r.nonbillable_kpi_pct)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>Total</td>
              <td>{fmtNum(totalWorked)}</td>
              <td>{fmtNum(totalNonbillable)}</td>
              <td className={`kpi-pct ${pctClass(totalNonbillablePct, 10, "max")}`}>{fmtPct(totalNonbillablePct)}</td>
            </tr>
          </tfoot>
        </KpiCard>
      </div>

      <div className="card evolution-chart-card">
        <div className="kpi-card-head">
          <Clock size={18} strokeWidth={1.8} />
          <div>
            <h3>Evolução: Trabalhado, Faturado e Delta</h3>
          </div>
        </div>
        <EvolutionChart rows={displayRows} />
      </div>

      <div className="side-by-side-cards">
        <div className="card nonbillable-packages-card">
          <div className="kpi-card-head">
            <DollarSign size={18} strokeWidth={1.8} />
            <div>
              <h3>Pacotes de trabalho não faturáveis</h3>
            </div>
          </div>
          <div className="kpi-table-wrap nonbillable-packages-table-wrap">
            <table className="kpi-table">
              <thead>
                <tr>
                  <SortableTh sortKey="pkg" activeKey={packageSort.sortKey} direction={packageSort.direction} onSort={packageSort.toggleSort}>Pacote de trabalho</SortableTh>
                  <SortableTh sortKey="hours" activeKey={packageSort.sortKey} direction={packageSort.direction} onSort={packageSort.toggleSort}>Horas</SortableTh>
                  <SortableTh sortKey="pct" activeKey={packageSort.sortKey} direction={packageSort.direction} onSort={packageSort.toggleSort}>% do não faturável</SortableTh>
                </tr>
              </thead>
              <tbody>
                {packageRows.length === 0 && (
                  <tr><td colSpan={3} className="muted">Nenhum pacote não faturável no período selecionado.</td></tr>
                )}
                {packageSort.sortedRows.map((p) => (
                  <tr key={p.pkg}>
                    <td>{p.pkg}</td>
                    <td>{fmtNum(p.hours)}</td>
                    <td>{totalNonbillable > 0 ? `${fmtNum((p.hours / totalNonbillable) * 100)}%` : "—"}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total</td>
                  <td>{fmtNum(totalNonbillable)}</td>
                  <td>{totalNonbillable > 0 ? "100%" : "—"}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}
