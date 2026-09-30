import { useState } from "react";
import { Send } from "lucide-react";
import { useReportStore } from "../store/useReportStore";
import { computeGrandTotalFor, findEmptyActivityDescriptionMessage } from "../utils/calc";
import { fmtNum } from "../utils/fmt";
import { computeDefaultFileName } from "../utils/fileName";
import { buildGeneratePayload } from "../utils/generatePayload";
import { SendReportModal } from "./SendReportModal";
import { FormatCheckboxes, type ReportFormat } from "./FormatCheckboxes";
import { toast } from "../store/useToastStore";

export function GenerateFooter() {
  const packages = useReportStore((s) => s.packages);
  const header = useReportStore((s) => s.header);
  const fileName = useReportStore((s) => s.fileName);
  const fileNameEdited = useReportStore((s) => s.fileNameEdited);
  const setFileName = useReportStore((s) => s.setFileName);
  const setHasGeneratedOnce = useReportStore((s) => s.setHasGeneratedOnce);
  const [generating, setGenerating] = useState(false);
  const [showSendModal, setShowSendModal] = useState(false);
  const [formats, setFormats] = useState<Set<ReportFormat>>(() => new Set(["xlsx"]));

  if (packages.length === 0) return null;

  const grandTotalAll = packages.reduce((sum, p) => sum + computeGrandTotalFor(p.groups), 0);
  const singleTotal = packages[0] ? computeGrandTotalFor(packages[0].groups) : 0;

  const defaultName = computeDefaultFileName(
    header.monthLabel,
    packages.map((p) => ({ projectCode: p.projectCode, projectName: p.projectName })),
  );
  const displayFileName = fileNameEdited ? fileName : defaultName;

  const handleGenerate = async () => {
    const missingCode = packages.find((pkg) => !pkg.projectCode.trim());
    if (missingCode) {
      toast.error(`Preencha o número do relatório (SE.XX.XXX) de "${missingCode.projectName}" antes de gerar.`);
      return;
    }
    if (!header.signer1Name.trim() || !header.signer2Name.trim()) {
      toast.error("Preencha o nome de quem assina (Schwaben e cliente) antes de gerar.");
      return;
    }
    const emptyDescMessage = findEmptyActivityDescriptionMessage(packages, "gerar");
    if (emptyDescMessage) {
      toast.error(emptyDescMessage);
      return;
    }

    const payload = buildGeneratePayload(packages, header, Array.from(formats));

    setGenerating(true);
    try {
      const res = await fetch("/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const isZip = packages.length !== 1 || formats.size !== 1;
      let outName = (displayFileName || defaultName).trim();
      outName = outName.replace(/\.(xlsx|pdf|zip)$/i, "");
      const wantedExt = isZip ? ".zip" : `.${Array.from(formats)[0]}`;
      outName += wantedExt;
      const a = document.createElement("a");
      a.href = url;
      a.download = outName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setHasGeneratedOnce(true);
      toast.success(
        isZip ? "Relatórios gerados — o download do .zip começou." : "Relatório gerado — o download começou.",
      );
    } catch (err: unknown) {
      toast.error("Erro ao gerar: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setGenerating(false);
    }
  };

  // Sync displayFileName to store if not edited, for controlled input
  const onFileNameChange = (v: string) => {
    setFileName(v, true);
  };

  // If not edited, we show default but store still holds old edited=false value
  // Ensure input reflects correct value: when not edited, we show default
  const inputValue = fileNameEdited ? fileName : defaultName;
  const isZipOutput = packages.length > 1 || formats.size > 1;

  return (
    <div className="generate-footer visible" id="generateSection">
      <div className="generate-footer-inner">
        <div className="generate-footer-main">
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
          <FormatCheckboxes value={formats} onChange={setFormats} />
          <button className="primary" onClick={handleGenerate} disabled={generating}>
            {generating ? "Gerando..." : "Gerar relatório final"}
          </button>
          <div className="filename-with-performance">
            <div className="filename-field">
              <label>{isZipOutput ? "Nome do arquivo (.zip)" : "Nome do arquivo"}</label>
              <input
                type="text"
                autoComplete="off"
                value={inputValue}
                onChange={(e) => onFileNameChange(e.target.value)}
                title={inputValue}
              />
            </div>
          </div>
        </div>
        <button type="button" className="primary generate-footer-send" onClick={() => setShowSendModal(true)}>
          <Send size={14} strokeWidth={2} />
          Enviar Relatório
        </button>
      </div>
      {showSendModal && <SendReportModal onClose={() => setShowSendModal(false)} />}
    </div>
  );
}
