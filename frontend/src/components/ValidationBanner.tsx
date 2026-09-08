import { useState } from "react";
import { useReportStore } from "../store/useReportStore";

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

export function ValidationBanner() {
  const issues = useReportStore((s) => s.currentIssues);
  const setIssues = useReportStore((s) => s.setIssues);
  const collapsed = useReportStore((s) => s.validationCollapsed);
  const setCollapsed = useReportStore((s) => s.setValidationCollapsed);
  const packages = useReportStore((s) => s.packages);
  const addActivityFromIssue = useReportStore((s) => s.addActivityFromIssue);

  // qual issue está com o seletor de grupo aberto (índice no array `issues`,
  // não um id — a lista não tem chave estável própria, mas o índice serve
  // bem aqui porque o array só encolhe, nunca reordena, entre um clique e o
  // próximo render).
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  // valor combinado "packageId::groupId" do <select> — string única porque
  // um <select> nativo não carrega dois ids ao mesmo tempo.
  const [target, setTarget] = useState("");

  if (!issues.length) return null;

  const groupOptions = packages.flatMap((pkg) =>
    pkg.groups.map((g) => ({
      value: `${pkg.id}::${g.id}`,
      label: `${pkg.projectCode || pkg.projectName || "Pacote"} — ${g.name}`,
    }))
  );

  function handleAdd(idx: number) {
    const issue = issues[idx];
    const [packageId, groupId] = target.split("::");
    if (!packageId || !groupId) return;
    addActivityFromIssue(groupId, packageId, issue.raw_description ?? "", issue.raw_hours ?? null);
    setIssues(issues.filter((_, i) => i !== idx));
    setExpandedIdx(null);
    setTarget("");
  }

  return (
    <div className={`validation-banner ${collapsed ? "collapsed" : ""} visible`}>
      <div className="validation-banner-header">
        <span className="validation-banner-title">⚠ <span>{issues.length}</span> linha(s) ignorada(s) com possível erro de apontamento</span>
        <button type="button" className="btn-toggle" onClick={() => setCollapsed(!collapsed)}>{collapsed ? "▸ Expandir" : "▾ Recolher"}</button>
      </div>
      <ul className="validation-list">
        {issues.map((issue, idx) => {
          const recoverable = issue.raw_hours !== null || issue.raw_description !== null;
          return (
            <li key={idx}>
              <div className="issue-line">
                <span className="issue-row">Linha {issue.row}</span>
                <span className="issue-detail">{renderIssueDetail(issue.reason, issue.message)}</span>
                {recoverable && groupOptions.length > 0 && (
                  <button
                    type="button"
                    className="btn-toggle issue-recover-toggle"
                    onClick={() => {
                      setExpandedIdx(expandedIdx === idx ? null : idx);
                      setTarget("");
                    }}
                  >
                    {expandedIdx === idx ? "Cancelar" : "+ Adicionar como atividade"}
                  </button>
                )}
              </div>
              {expandedIdx === idx && (
                <div className="issue-recover-form">
                  <select value={target} onChange={(e) => setTarget(e.target.value)}>
                    <option value="">Escolher grupo...</option>
                    {groupOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                  <button type="button" className="btn-primary" disabled={!target} onClick={() => handleAdd(idx)}>
                    Adicionar
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
