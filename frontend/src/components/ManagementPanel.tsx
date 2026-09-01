import { useEffect, useState } from "react";
import { Clock, FileText, DollarSign, RefreshCw, MailSearch } from "lucide-react";
import { Gauge } from "./Gauge";
import { ManagementFilters } from "./ManagementFilters";
import { ExtraHoursInput } from "./ExtraHoursInput";
import { fmtNum } from "../utils/fmt";
import { useManagementStore, type MonthRow } from "../store/useManagementStore";

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

async function putJson(url: string, body: unknown) {
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
}

type CheckEmailsResult = { messages_found: number; samples_added: number; skipped: number };

async function checkEmails(): Promise<CheckEmailsResult> {
  const res = await fetch("/management/kpis/check-emails", { method: "POST" });
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
  return res.json();
}

export function ManagementPanel() {
  const rows = useManagementStore((s) => s.rows);
  const nonbillableBreakdown = useManagementStore((s) => s.nonbillableBreakdown);
  const selectedMonths = useManagementStore((s) => s.selectedMonths);
  const error = useManagementStore((s) => s.error);
  const refreshing = useManagementStore((s) => s.refreshing);
  const load = useManagementStore((s) => s.load);
  const updateRow = useManagementStore((s) => s.updateRow);
  const setError = useManagementStore((s) => s.setError);

  const [checkingEmails, setCheckingEmails] = useState(false);
  const [checkEmailsMessage, setCheckEmailsMessage] = useState("");

  useEffect(() => {
    load();
  }, [load]);

  const saveEntry = async (month: string, row: MonthRow) => {
    try {
      await putJson(`/management/kpis/${month}`, { billed_hours: row.billed_hours, elaboration_days: row.elaboration_days });
    } catch {
      setError("Não consegui salvar essa alteração. Tenta de novo.");
    }
  };

  const handleCheckEmails = async () => {
    setCheckingEmails(true);
    setCheckEmailsMessage("");
    try {
      const result = await checkEmails();
      setCheckEmailsMessage(
        result.samples_added > 0
          ? `${result.samples_added} relatório(s) novo(s) processado(s).`
          : result.messages_found > 0
            ? `${result.messages_found} e-mail(s) verificado(s), nenhum gerou dado novo.`
            : "Nenhum e-mail novo do Alberto."
      );
      await load(true, true);
    } catch {
      setCheckEmailsMessage("Não consegui verificar os e-mails agora. Tenta de novo em instantes.");
    } finally {
      setCheckingEmails(false);
    }
  };

  if (!rows) {
    return (
      <div className="card management-panel">
        <h2>Painel de Gerência</h2>
        <p className="muted">{error || "Carregando..."}</p>
      </div>
    );
  }

  // Competência filtra só a exibição/agregação — os 12 meses continuam
  // carregados na store, sem novo fetch, só muda o que entra nas somas.
  const displayRows = selectedMonths.length ? rows.filter((r) => selectedMonths.includes(r.month)) : rows;

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

  return (
    <div className="management-layout">
      <ManagementFilters />
      <div className="management-panel">
      {error && <div className="card"><p className="muted">{error}</p></div>}

      <div className="management-toolbar">
        <button type="button" className="btn-secondary" onClick={() => load(true, true)} disabled={refreshing}>
          <RefreshCw size={14} strokeWidth={2} className={refreshing ? "spin" : ""} />
          {refreshing ? "Atualizando..." : "Atualizar"}
        </button>
        <button type="button" className="btn-secondary" onClick={handleCheckEmails} disabled={checkingEmails}>
          <MailSearch size={14} strokeWidth={2} className={checkingEmails ? "spin" : ""} />
          {checkingEmails ? "Verificando..." : "Verificar horas faturadas"}
        </button>
        {checkEmailsMessage && <span className="muted management-toolbar-message">{checkEmailsMessage}</span>}
      </div>

      <div className="kpi-grid">
        <div className="card kpi-card">
          <div className="kpi-card-head">
            <Clock size={18} strokeWidth={1.8} />
            <div>
              <h3>Performance em Horas</h3>
              <p className="muted">Meta = mínimo 10%</p>
            </div>
          </div>
          <Gauge value={totalPerfPct === null ? null : totalPerfPct * 100} metaValue={10} metaType="min" gaugeMax={30} label={fmtPct(totalPerfPct)} />
          <div className="kpi-table-wrap">
            <table className="kpi-table">
              <thead>
                <tr><th>Competência</th><th>Trabalhadas</th><th>Faturadas</th><th>Perf. H</th><th>KPI %</th></tr>
              </thead>
              <tbody>
                {displayRows.map((r) => (
                  <tr key={r.month}>
                    <td>{r.month}</td>
                    <td>{fmtNum(r.worked_hours)}</td>
                    <td>
                      <ExtraHoursInput
                        className="kpi-input"
                        value={r.billed_hours}
                        placeholder="—"
                        onCommit={(v) => updateRow(r.month, { billed_hours: v })}
                        onBlur={() => saveEntry(r.month, r)}
                      />
                    </td>
                    <td>{r.perf_hours === null ? "—" : fmtNum(r.perf_hours)}</td>
                    <td className={`kpi-pct ${pctClass(r.perf_kpi_pct, 10, "min")}`}>{fmtPct(r.perf_kpi_pct)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total</td>
                  <td>{fmtNum(totalWorkedForPerf)}</td>
                  <td>{fmtNum(totalBilled)}</td>
                  <td>{fmtNum(totalPerf)}</td>
                  <td className={`kpi-pct ${pctClass(totalPerfPct, 10, "min")}`}>{fmtPct(totalPerfPct)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-card-head">
            <FileText size={18} strokeWidth={1.8} />
            <div>
              <h3>Elaboração dos relatórios</h3>
              <p className="muted">Meta = máximo 5 dias úteis</p>
            </div>
          </div>
          <Gauge value={avgDays} metaValue={5} metaType="max" gaugeMax={15} label={avgDays === null ? "—" : fmtNum(avgDays)} />
          <div className="kpi-table-wrap">
            <table className="kpi-table">
              <thead>
                <tr><th>Competência</th><th>KPI (Dias)</th></tr>
              </thead>
              <tbody>
                {displayRows.map((r) => (
                  <tr key={r.month}>
                    <td>{r.month}</td>
                    <td>
                      <ExtraHoursInput
                        className="kpi-input kpi-input-days"
                        value={r.elaboration_days}
                        placeholder="—"
                        onCommit={(v) => updateRow(r.month, { elaboration_days: v })}
                        onBlur={() => saveEntry(r.month, r)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr><td>Total</td><td>{avgDays === null ? "—" : fmtNum(avgDays)}</td></tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div className="card kpi-card">
          <div className="kpi-card-head">
            <DollarSign size={18} strokeWidth={1.8} />
            <div>
              <h3>Horas não faturáveis</h3>
              <p className="muted">Meta = máximo 10%</p>
            </div>
          </div>
          <Gauge value={totalNonbillablePct === null ? null : totalNonbillablePct * 100} metaValue={10} metaType="max" gaugeMax={30} label={fmtPct(totalNonbillablePct)} />
          <div className="kpi-table-wrap">
            <table className="kpi-table">
              <thead>
                <tr><th>Competência</th><th>Total Horas</th><th>Horas NãoFat</th><th>KPI %</th></tr>
              </thead>
              <tbody>
                {displayRows.map((r) => (
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
            </table>
          </div>
        </div>
      </div>

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
              <tr><th>Pacote de trabalho</th><th>Horas</th><th>% do não faturável</th></tr>
            </thead>
            <tbody>
              {packageRows.length === 0 && (
                <tr><td colSpan={3} className="muted">Nenhum pacote não faturável no período selecionado.</td></tr>
              )}
              {packageRows.map((p) => (
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
  );
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
