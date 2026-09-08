import { useState } from "react";
import { useReportStore } from "../store/useReportStore";
import type { RowIssue } from "../api/types";

const ISSUE_HIGHLIGHT_PHRASES: Record<string, string[]> = {
  sem_separador: ['sem "-" ou "_" separando prefixo e descrição'],
  descricao_vazia: ["prefixo vazio", "descrição vazia"],
  dados_incompletos: ["apontamento incompleto, falta preencher"],
  hs_invalido: ["não é um número válido"],
  pacote_nao_identificado: ["não consegui identificar o projeto"],
};

function renderIssueDetail(reason: string, message: string) {
  const rawDetail = message.replace(/^Linha \d+:\s*/, "");
  // React já escapa o texto renderizado — o destaque abaixo só recorta o
  // texto em pedaços e envolve o trecho da frase com um <span>.
  let parts: Array<string | JSX.Element> = [rawDetail];
  const phrases = ISSUE_HIGHLIGHT_PHRASES[reason] || [];
  phrases.forEach((phrase) => {
    const newParts: Array<string | JSX.Element> = [];
    parts.forEach((part) => {
      if (typeof part !== "string") {
        newParts.push(part);
        return;
      }
      const split = part.split(phrase);
      split.forEach((chunk, idx) => {
        if (chunk) newParts.push(chunk);
        if (idx < split.length - 1) newParts.push(<span key={idx} className="issue-highlight">{phrase}</span>);
      });
    });
    parts = newParts;
  });
  return parts;
}

// só linhas com hora conhecida (raw_hours) entram na recuperação em lote —
// a hora vira fixa/não editável (ver addActivitiesFromIssues), então sem um
// número confiável não tem o que recuperar de forma segura (ex: "hs_invalido"
// tem descrição válida, mas a própria hora é o dado quebrado).
function isRecoverable(issue: RowIssue): boolean {
  return issue.raw_hours !== null;
}

export function ValidationBanner() {
  const issues = useReportStore((s) => s.currentIssues);
  const setIssues = useReportStore((s) => s.setIssues);
  const collapsed = useReportStore((s) => s.validationCollapsed);
  const setCollapsed = useReportStore((s) => s.setValidationCollapsed);
  const packages = useReportStore((s) => s.packages);
  const addActivitiesFromIssues = useReportStore((s) => s.addActivitiesFromIssues);

  // `issue.row` é único dentro da resposta de uma mesma importação (vem de
  // um contador incremental por linha/lançamento — ver parser.py/
  // projectile_db.py), então serve de chave estável mesmo com o array
  // encolhendo a cada lote adicionado.
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [target, setTarget] = useState("");

  if (!issues.length) return null;

  const groupOptions = packages.flatMap((pkg) =>
    pkg.groups.map((g) => ({
      value: `${pkg.id}::${g.id}`,
      label: `${pkg.projectCode || pkg.projectName || "Pacote"} — ${g.name}`,
    }))
  );

  function toggleChecked(row: number) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(row)) next.delete(row);
      else next.add(row);
      return next;
    });
  }

  function handleAddSelected() {
    const [packageId, groupId] = target.split("::");
    if (!packageId || !groupId) return;
    const selected = issues.filter((i) => checked.has(i.row) && isRecoverable(i));
    if (!selected.length) return;
    addActivitiesFromIssues(
      groupId,
      packageId,
      selected.map((i) => ({ description: i.raw_description ?? "", hours: i.raw_hours as number }))
    );
    setIssues(issues.filter((i) => !checked.has(i.row) || !isRecoverable(i)));
    setChecked(new Set());
  }

  const hasRecoverable = issues.some(isRecoverable);
  const checkedCount = checked.size;

  return (
    <div className={`validation-banner ${collapsed ? "collapsed" : ""} visible`}>
      <div className="validation-banner-header">
        <span className="validation-banner-title">⚠ <span>{issues.length}</span> linha(s) ignorada(s) com possível erro de apontamento</span>
        {hasRecoverable && groupOptions.length > 0 && (
          <div className="issue-recover-bulk">
            <select
              className="pane-package-select issue-recover-select"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              disabled={collapsed}
            >
              <option value="">Escolher grupo...</option>
              {groupOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <button
              type="button"
              className="primary issue-recover-btn"
              disabled={!target || checkedCount === 0}
              onClick={handleAddSelected}
            >
              Adicionar selecionada(s){checkedCount > 0 ? ` (${checkedCount})` : ""}
            </button>
          </div>
        )}
        <button type="button" className="btn-toggle" onClick={() => setCollapsed(!collapsed)}>{collapsed ? "▸ Expandir" : "▾ Recolher"}</button>
      </div>
      <ul className="validation-list">
        {issues.map((issue) => {
          const recoverable = isRecoverable(issue);
          return (
            <li key={issue.row}>
              <span className="issue-row">Linha {issue.row}</span>
              <span className="issue-detail">{renderIssueDetail(issue.reason, issue.message)}</span>
              {recoverable && (
                <input
                  type="checkbox"
                  className="issue-checkbox"
                  checked={checked.has(issue.row)}
                  onChange={() => toggleChecked(issue.row)}
                  title="Selecionar pra adicionar como atividade"
                />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
