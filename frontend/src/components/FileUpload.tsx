import { useRef, useState } from "react";
import { useReportStore } from "../store/useReportStore";
import type { ParseResponse } from "../api/types";

function genId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2, 9);
}

export function FileUpload() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState("");
  const [hasFile, setHasFile] = useState(false);
  const reportMode = useReportStore((s) => s.reportMode);
  const setPackages = useReportStore((s) => s.setPackages);
  const setIssues = useReportStore((s) => s.setIssues);
  const packages = useReportStore((s) => s.packages);

  // Show status when mode changes and we have packages (was reset)
  const handleModeChangeSideEffect = () => {
    // reportMode change already resets packages via store, but we need to clear file input
    if (fileInputRef.current) fileInputRef.current.value = "";
    setHasFile(false);
    if (packages.length > 0) setStatus("Modo alterado — selecione o arquivo novamente para reanalisar.");
  };

  // Detect mode change to clear file? Store already clears packages, we just clear input
  // Use effect would be better, but simpler: watch packages length
  // Instead, we clear input when reportMode changes via ModeSelect? ModeSelect already triggers store reset.
  // We'll add an effect to reset file input when packages cleared?

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setHasFile(e.target.files ? e.target.files.length > 0 : false);
  };

  const clearFile = () => {
    if (fileInputRef.current) fileInputRef.current.value = "";
    setHasFile(false);
    setStatus("");
    // resetParsedState will be called via store reset? We need to clear packages
    useReportStore.getState().resetParsedState();
    const step1 = document.getElementById("step1");
    if (step1) step1.style.display = "block";
  };

  const handleParse = async () => {
    const fileInput = fileInputRef.current;
    if (!fileInput?.files?.length) {
      setStatus("Selecione um arquivo .xlsx primeiro.");
      return;
    }
    setStatus("Analisando...");
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("mode", reportMode);
    try {
      const res = await fetch("/parse", { method: "POST", body: formData });
      if (!res.ok) throw new Error(await res.text());
      const data: ParseResponse = await res.json();

      if (data.packages.length === 0) {
        setStatus("Nenhum grupo de atividades encontrado nesta planilha. Confira o aviso de validação acima (se houver) ou o arquivo enviado.");
        // create empty packages? keep none
        setPackages([], null);
        setIssues(data.issues || []);
        return;
      }

      const pkgs = data.packages.map((p) => ({
        id: genId(),
        key: p.key,
        projectCode: "",
        projectName: p.project_name || p.key,
        groups: p.groups.map((g) => ({
          id: genId(),
          name: g.name,
          performance: 1,
          activities: g.activities.map((a) => ({ id: genId(), description: a.description, hours: a.hours })),
        })),
        collapsedGroupIds: new Set<string>(p.groups.map((_, i) => String(i))), // temporary, will migrate to ids
        fileName: "",
        fileNameEdited: false,
      }));
      // fix collapsed ids to real ids
      pkgs.forEach((pkg) => {
        pkg.collapsedGroupIds = new Set(pkg.groups.map((g) => g.id));
      });

      setPackages(pkgs, pkgs[0]?.id ?? null);
      setIssues(data.issues || []);
      const totalGroups = pkgs.reduce((sum, p) => sum + p.groups.length, 0);
      setStatus(
        pkgs.length > 1
          ? `Encontrados ${pkgs.length} pacotes de trabalho (${totalGroups} grupo(s) no total).`
          : `Encontrados ${totalGroups} grupo(s).`
      );
      const step1 = document.getElementById("step1");
      if (step1) step1.style.display = "none";
      // fileName will be updated via effect in GenerateFooter / store?
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("Erro ao analisar: " + msg);
    }
  };

  const changeFile = () => {
    const step1 = document.getElementById("step1");
    if (step1) step1.style.display = "block";
  };

  // Sync hasFile vs mode reset: if packages cleared externally, clear file input
  // Simple effect: when packages length is 0, ensure file input cleared? Not needed.

  return (
    <>
      <div className="card" id="step1">
        <h2>1. Importar relatório do Projectile</h2>
        <div className="mode-select">
          <button
            type="button"
            className={`mode-option ${reportMode === "single" ? "active" : ""}`}
            onClick={() => {
              if (reportMode !== "single") {
                useReportStore.getState().setReportMode("single");
                if (fileInputRef.current) fileInputRef.current.value = "";
                setHasFile(false);
                setStatus("Modo alterado — selecione o arquivo novamente para reanalisar.");
              }
            }}
          >
            <span className="mode-title">Relatório único</span>
            <span className="mode-desc">Todas as linhas viram um único relatório final.</span>
          </button>
          <button
            type="button"
            className={`mode-option ${reportMode === "multi" ? "active" : ""}`}
            onClick={() => {
              if (reportMode !== "multi") {
                useReportStore.getState().setReportMode("multi");
                if (fileInputRef.current) fileInputRef.current.value = "";
                setHasFile(false);
                setStatus("Modo alterado — selecione o arquivo novamente para reanalisar.");
              }
            }}
          >
            <span className="mode-title">Múltiplos relatórios</span>
            <span className="mode-desc">Um relatório separado por Pacote de Trabalho.</span>
          </button>
        </div>
        <div className="file-input-row">
          <input ref={fileInputRef} type="file" accept=".xlsx" title="Selecione o .xlsx exportado do Projectile para o mês/projeto." onChange={onFileChange} />
          <button type="button" className="btn-remove-file" title="Remover arquivo selecionado" style={{ display: hasFile ? "flex" : "none" }} onClick={clearFile}>
            <span>×</span> Remover
          </button>
        </div>
        <button className="primary" onClick={handleParse}>Analisar planilha</button>
        <p className="muted">{status}</p>
      </div>
      {/* hidden change file button lives in SummaryBar, but we expose helper via window? We'll render SummaryBar separately */}
      <button type="button" id="btnChangeFileHidden" style={{ display: "none" }} onClick={changeFile} />
    </>
  );
}
