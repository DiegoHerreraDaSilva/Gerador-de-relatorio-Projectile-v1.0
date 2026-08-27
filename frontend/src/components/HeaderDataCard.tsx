import { useReportStore } from "../store/useReportStore";

export function HeaderDataCard() {
  const header = useReportStore((s) => s.header);
  const setHeaderField = useReportStore((s) => s.setHeaderField);
  const activePkg = useReportStore((s) => s.packages.find((p) => p.id === s.activePackageId) ?? null);
  const updateProjectCode = useReportStore((s) => s.updateProjectCode);
  const updateProjectName = useReportStore((s) => s.updateProjectName);
  const collapsed = useReportStore((s) => s.headerCollapsed);
  const setCollapsed = useReportStore((s) => s.setHeaderCollapsed);
  const pushUndo = useReportStore((s) => s.pushUndo);

  const projectCodeMissing = !activePkg || (activePkg.projectCode || "").trim() === "";

  return (
    <div className="card" id="headerDataCard">
      <div className="card-header-row">
        <h2>Dados do relatório</h2>
        <button type="button" className="btn-toggle" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? "✎ Editar dados" : "▾ Recolher"}
        </button>
      </div>
      <div id="headerDataExpanded" style={{ display: collapsed ? "none" : "block" }}>
        <label>
          Código do projeto (ex: SE.26.048) <span className="required-mark">*</span>
        </label>
        <input
          type="text"
          value={activePkg?.projectCode ?? ""}
          className={projectCodeMissing ? "field-missing" : ""}
          onFocus={() => pushUndo()}
          onChange={(e) => updateProjectCode(e.target.value)}
        />
        <label>Nome do projeto (ex: CAD_Cabina - Série)</label>
        <input
          type="text"
          value={activePkg?.projectName ?? ""}
          onFocus={() => pushUndo()}
          onChange={(e) => updateProjectName(e.target.value)}
        />
        <label>Local e data (ex: Santo André, 13.08.2026)</label>
        <input type="text" value={header.locationDate} onFocus={() => pushUndo()} onChange={(e) => setHeaderField("locationDate", e.target.value)} />
        <label>Mês de referência (ex: Julho/2026)</label>
        <input type="text" value={header.monthLabel} onFocus={() => pushUndo()} onChange={(e) => setHeaderField("monthLabel", e.target.value)} />
        <label>Nome do engenheiro (assinatura 1)</label>
        <input type="text" placeholder="Nome completo" value={header.signer1Name} onFocus={() => pushUndo()} onChange={(e) => setHeaderField("signer1Name", e.target.value)} />
        <label>Empresa (assinatura 1)</label>
        <input type="text" value={header.signer1Company} onFocus={() => pushUndo()} onChange={(e) => setHeaderField("signer1Company", e.target.value)} />
        <label>Nome do engenheiro (assinatura 2)</label>
        <input type="text" placeholder="Nome completo" value={header.signer2Name} onFocus={() => pushUndo()} onChange={(e) => setHeaderField("signer2Name", e.target.value)} />
        <label>Empresa (assinatura 2)</label>
        <input type="text" value={header.signer2Company} onFocus={() => pushUndo()} onChange={(e) => setHeaderField("signer2Company", e.target.value)} />
      </div>
      <div id="headerDataSummary" className="header-data-summary" style={{ display: collapsed ? "flex" : "none" }}>
        {[
          ["Código", activePkg?.projectCode ?? ""],
          ["Nome", activePkg?.projectName ?? ""],
          ["Local/Data", header.locationDate],
          ["Mês", header.monthLabel],
        ].map(([label, value]) => (
          <div className="field" key={label}>
            <span className="field-label">{label}</span>
            <span className="field-value">{value || "—"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
