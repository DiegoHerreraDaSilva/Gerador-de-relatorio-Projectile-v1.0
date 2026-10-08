import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Download, FileSpreadsheet, UserPlus, X } from "lucide-react";
import { useModal } from "../hooks/useModal";
import { Select, type SelectOption } from "./Select";
import { ErrorState, LoadingState } from "./PageStates";
import { toast } from "../store/useToastStore";
import { useReportStore } from "../store/useReportStore";
import type { ExternalIssue, ExternalRow } from "../api/types";
import { fmtNum } from "../utils/fmt";
import {
  downloadExternalTemplate,
  parseExternalFile,
  planExternalMerge,
  resolvePending,
  totalHours,
  type ExternalPlan,
} from "../utils/externalHours";

const MAX_BYTES = 25 * 1024 * 1024;
const DISCARD = "";

function fmtDate(iso: string): string {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
}

function RowList({ title, rows, hint }: { title: string; rows: ExternalRow[]; hint: string }) {
  if (rows.length === 0) return null;
  return (
    <details className="ext-hours-details">
      <summary>
        {title} ({rows.length}) <span className="muted">— {hint}</span>
      </summary>
      <ul>
        {rows.map((r) => (
          <li key={`${r.row}-${r.date}`}>
            Linha {r.row}: {fmtDate(r.date)} · {r.collaborator} · {r.project} › {r.package} · {fmtNum(r.hours)} h
          </li>
        ))}
      </ul>
    </details>
  );
}

/** "Adicionar horas externas": anexa a planilha de colaboradores que NÃO apontam no Projectile ao relatório
 * aberto. Mostra, antes de aplicar, o que entra, o que fica pendente (você escolhe o destino ou descarta) e o
 * que foi descartado (repetido, fora do período, linha inválida). Aplicar é um passo só, com Desfazer. */
export function ExternalHoursModal({ onClose }: { onClose: () => void }) {
  const modalRef = useModal({ onClose });
  const packages = useReportStore((s) => s.packages);
  const monthLabel = useReportStore((s) => s.header.monthLabel);
  const applyExternalHours = useReportStore((s) => s.applyExternalHours);
  const fileInput = useRef<HTMLInputElement>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [fileName, setFileName] = useState("");
  const [plan, setPlan] = useState<ExternalPlan | null>(null);
  const [issues, setIssues] = useState<ExternalIssue[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [choices, setChoices] = useState<Record<string, string>>({});

  const destinations: SelectOption[] = useMemo(
    () => [
      { value: DISCARD, label: "Descartar estas linhas" },
      ...packages.flatMap((p) =>
        p.groups.map((g) => ({ value: `${p.id}::${g.id}`, label: `${p.projectName || p.key} › ${g.name}` })),
      ),
    ],
    [packages],
  );

  const placements = useMemo(() => (plan ? resolvePending(plan, choices) : []), [plan, choices]);
  const toAdd = totalHours(placements);

  const summaryByGroup = useMemo(() => {
    const byGroup = new Map<string, { pkg: string; group: string; hours: number; rows: number }>();
    placements.forEach((p) => {
      const pkg = packages.find((x) => x.id === p.packageId);
      const group = pkg?.groups.find((g) => g.id === p.groupId);
      const key = `${p.packageId}::${p.groupId}`;
      const entry = byGroup.get(key) ?? {
        pkg: pkg?.projectName || pkg?.key || "",
        group: group?.name ?? "",
        hours: 0,
        rows: 0,
      };
      entry.hours = Math.round((entry.hours + p.hours) * 1000) / 1000;
      entry.rows += 1;
      byGroup.set(key, entry);
    });
    return [...byGroup.values()];
  }, [placements, packages]);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setError("Envie um arquivo .xlsx (use o modelo).");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("Arquivo muito grande. O limite é 25 MB.");
      return;
    }
    setLoading(true);
    try {
      const response = await parseExternalFile(file);
      setFileName(file.name);
      setIssues(response.issues);
      setTotalRows(response.rows.length);
      setChoices({});
      setPlan(planExternalMerge(packages, response.rows, monthLabel));
    } catch (e) {
      setPlan(null);
      setError(e instanceof Error ? e.message : "Não consegui ler a planilha.");
    } finally {
      setLoading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const downloadTemplate = async () => {
    try {
      await downloadExternalTemplate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Não consegui baixar o modelo.");
    }
  };

  const apply = () => {
    if (!placements.length) return;
    const ok = applyExternalHours(placements);
    if (!ok) {
      setError("Os destinos escolhidos não existem mais neste relatório. Escolha de novo.");
      return;
    }
    toast.success(
      `${fmtNum(toAdd)} h de ${placements.length} ${placements.length === 1 ? "linha adicionada" : "linhas adicionadas"} ao relatório.`,
      {
        actionLabel: "Desfazer",
        onAction: () => useReportStore.getState().undo(),
      },
    );
    onClose();
  };

  const discarded = plan ? plan.duplicates.length + plan.outOfPeriod.length + issues.length : 0;

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={modalRef}
        tabIndex={-1}
        className="modal-card ext-hours-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ext-hours-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="ext-hours-title">
            <UserPlus size={17} strokeWidth={2} aria-hidden="true" /> Adicionar horas externas
          </h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar">
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <div className="modal-body ext-hours-body">
          <p className="muted ext-hours-intro">
            Para colaboradores que não apontam no Projectile. Cada linha da planilha entra no pacote e no grupo de mesmo
            nome deste relatório, com o nome do colaborador no início da descrição.
          </p>

          <div className="ext-hours-pick">
            <input
              ref={fileInput}
              type="file"
              accept=".xlsx"
              className="sr-only"
              id="ext-hours-file"
              onChange={(e) => void pick(e.target.files?.[0])}
            />
            <button type="button" className="primary" onClick={() => fileInput.current?.click()} disabled={loading}>
              <FileSpreadsheet size={15} strokeWidth={2} aria-hidden="true" />{" "}
              {plan ? "Escolher outra planilha" : "Escolher planilha"}
            </button>
            <button type="button" className="btn-secondary" onClick={() => void downloadTemplate()}>
              <Download size={15} strokeWidth={2} aria-hidden="true" /> Baixar modelo
            </button>
            {fileName && <span className="muted ext-hours-file">{fileName}</span>}
          </div>

          {loading && <LoadingState label="Lendo a planilha..." rows={3} />}
          {error && <ErrorState message={error} />}

          {plan && !loading && (
            <>
              <dl className="ext-hours-stats">
                <div>
                  <dt>Linhas lidas</dt>
                  <dd>{totalRows}</dd>
                </div>
                <div>
                  <dt>Entram</dt>
                  <dd>
                    {placements.length} · {fmtNum(toAdd)} h
                  </dd>
                </div>
                <div>
                  <dt>Pendentes</dt>
                  <dd>{plan.pending.length}</dd>
                </div>
                <div>
                  <dt>Descartadas</dt>
                  <dd>{discarded}</dd>
                </div>
              </dl>

              {plan.pending.length > 0 && (
                <section className="ext-hours-section" aria-label="Linhas sem destino">
                  <h3>Sem destino ({plan.pending.length})</h3>
                  <p className="muted">
                    Não achei esse projeto ou pacote de trabalho neste relatório. Escolha onde as horas entram ou
                    descarte.
                  </p>
                  {plan.pending.map((bucket) => (
                    <div key={bucket.id} className="ext-hours-pending">
                      <div>
                        <strong>
                          {bucket.project} › {bucket.workPackage}
                        </strong>
                        <span className="muted">
                          {" "}
                          {bucket.rows.length} {bucket.rows.length === 1 ? "linha" : "linhas"} · {fmtNum(bucket.hours)}{" "}
                          h ·{" "}
                          {bucket.missing === "projeto"
                            ? "projeto não encontrado"
                            : "pacote de trabalho não encontrado"}
                        </span>
                      </div>
                      <Select
                        ariaLabel={`Destino de ${bucket.project} › ${bucket.workPackage}`}
                        value={choices[bucket.id] ?? DISCARD}
                        options={destinations}
                        onChange={(value) => setChoices((current) => ({ ...current, [bucket.id]: value }))}
                      />
                    </div>
                  ))}
                </section>
              )}

              {summaryByGroup.length > 0 && (
                <section className="ext-hours-section" aria-label="O que será adicionado">
                  <h3>O que será adicionado</h3>
                  <table className="kpi-table ext-hours-table">
                    <thead>
                      <tr>
                        <th>Pacote</th>
                        <th>Grupo</th>
                        <th>Linhas</th>
                        <th>Horas</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summaryByGroup.map((entry) => (
                        <tr key={`${entry.pkg}::${entry.group}`}>
                          <td>{entry.pkg}</td>
                          <td>{entry.group}</td>
                          <td>{entry.rows}</td>
                          <td>{fmtNum(entry.hours)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}

              <RowList
                title="Já estavam no relatório"
                rows={plan.duplicates}
                hint="anexo repetido, não somei de novo"
              />
              <RowList
                title="Fora do período do relatório"
                rows={plan.outOfPeriod}
                hint={`o relatório é de ${monthLabel}`}
              />
              {issues.length > 0 && (
                <details className="ext-hours-details">
                  <summary>
                    Linhas com problema ({issues.length}){" "}
                    <span className="muted">— corrija na planilha e envie de novo</span>
                  </summary>
                  <ul>
                    {issues.map((i) => (
                      <li key={`${i.row}-${i.reason}`}>{i.message}</li>
                    ))}
                  </ul>
                </details>
              )}
              {placements.length === 0 && plan.pending.length === 0 && (
                <p className="muted">Nenhuma linha nova para adicionar a este relatório.</p>
              )}
            </>
          )}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancelar
          </button>
          <button type="button" className="primary" onClick={apply} disabled={loading || placements.length === 0}>
            {placements.length ? `Adicionar ${fmtNum(toAdd)} h` : "Adicionar"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
