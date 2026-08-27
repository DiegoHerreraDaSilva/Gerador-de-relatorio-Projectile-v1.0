import { useState } from "react";
import { useReportStore } from "../store/useReportStore";
import { computeGrandTotalFor } from "../utils/calc";
import { fmtNum } from "../utils/fmt";
import { computeDefaultFileName, computeDefaultFileNameFor } from "../utils/fileName";

export function GenerateFooter() {
  const packages = useReportStore((s) => s.packages);
  const header = useReportStore((s) => s.header);
  const fileName = useReportStore((s) => s.fileName);
  const fileNameEdited = useReportStore((s) => s.fileNameEdited);
  const setFileName = useReportStore((s) => s.setFileName);
  const setHasGeneratedOnce = useReportStore((s) => s.setHasGeneratedOnce);
  const [status, setStatus] = useState("");

  if (packages.length === 0) return null;

  const grandTotalAll = packages.reduce((sum, p) => sum + computeGrandTotalFor(p.groups), 0);
  const singleTotal = packages[0] ? computeGrandTotalFor(packages[0].groups) : 0;

  const isSingle = packages.length === 1;
  const defaultName = computeDefaultFileName(header.monthLabel, packages.map((p) => ({ projectCode: p.projectCode, projectName: p.projectName })));
  const displayFileName = fileNameEdited ? fileName : defaultName;

  const handleGenerate = async () => {
    const payload = {
      packages: packages.map((pkg) => ({
        header: {
          project_code: pkg.projectCode,
          project_name: pkg.projectName,
          location_date: header.locationDate,
          month_label: header.monthLabel,
          signer1_name: header.signer1Name,
          signer1_company: header.signer1Company,
          signer2_name: header.signer2Name,
          signer2_company: header.signer2Company,
        },
        groups: pkg.groups.map((g) => ({
          name: g.name,
          performance: g.performance,
          activities: g.activities.map((a) => ({ description: a.description, hours: a.hours })),
        })),
        file_name: packages.length > 1 ? (pkg.fileNameEdited ? pkg.fileName : computeDefaultFileNameFor(pkg, header.monthLabel)) : undefined,
      })),
    };

    setStatus("Gerando...");
    try {
      const res = await fetch("/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const isZip = packages.length !== 1;
      let outName = (isSingle ? displayFileName : displayFileName) || defaultName;
      outName = outName.trim();
      const wantedExt = isZip ? ".zip" : ".xlsx";
      if (!outName.toLowerCase().endsWith(wantedExt)) outName += wantedExt;
      const a = document.createElement("a");
      a.href = url;
      a.download = outName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setStatus("");
      setHasGeneratedOnce(true);
    } catch (err: unknown) {
      setStatus("Erro ao gerar: " + (err instanceof Error ? err.message : String(err)));
    }
  };

  // Sync displayFileName to store if not edited, for controlled input
  const onFileNameChange = (v: string) => {
    setFileName(v, true);
  };

  // If not edited, we show default but store still holds old edited=false value
  // Ensure input reflects correct value: when not edited, we show default
  const inputValue = fileNameEdited ? fileName : defaultName;

  return (
    <div className="generate-footer visible" id="generateSection">
      <div className="generate-footer-inner">
        <div className="generate-total">
          {packages.length > 1 ? (
            <>
              Total geral: <strong>{fmtNum(grandTotalAll)} horas</strong> em {packages.length} relatórios
            </>
          ) : (
            <>
              Total: <strong>{fmtNum(singleTotal)} horas</strong>
            </>
          )}
        </div>
        <button className="primary" onClick={handleGenerate}>
          Gerar relatório final
        </button>
        <div className="filename-field">
          <label>{packages.length > 1 ? "Nome do arquivo (.zip)" : "Nome do arquivo"}</label>
          <input type="text" value={inputValue} onChange={(e) => onFileNameChange(e.target.value)} title={inputValue} />
        </div>
      </div>
      <p className="muted" style={{ textAlign: "center", minHeight: "1.45em", margin: "4px 0 0" }}>
        {status}
      </p>
    </div>
  );
}
