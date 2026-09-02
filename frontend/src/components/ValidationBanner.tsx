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
  const collapsed = useReportStore((s) => s.validationCollapsed);
  const setCollapsed = useReportStore((s) => s.setValidationCollapsed);

  if (!issues.length) return null;

  return (
    <div className={`validation-banner ${collapsed ? "collapsed" : ""} visible`}>
      <div className="validation-banner-header">
        <span className="validation-banner-title">⚠ <span>{issues.length}</span> linha(s) ignorada(s) com possível erro de apontamento</span>
        <button type="button" className="btn-toggle" onClick={() => setCollapsed(!collapsed)}>{collapsed ? "▸ Expandir" : "▾ Recolher"}</button>
      </div>
      <ul className="validation-list">
        {issues.map((issue, idx) => (
          <li key={idx}>
            <span className="issue-row">Linha {issue.row}</span>
            <span className="issue-detail">{renderIssueDetail(issue.reason, issue.message)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
