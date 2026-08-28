import { useRef, useState } from "react";
import { FileSpreadsheet } from "lucide-react";
import { useReportStore } from "../store/useReportStore";
import type { ParseResponse } from "../api/types";

function genId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2, 9);
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

export function FileUpload() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const reportMode = useReportStore((s) => s.reportMode);
  const setPackages = useReportStore((s) => s.setPackages);
  const setIssues = useReportStore((s) => s.setIssues);

  const applyFile = (file: File | null) => {
    setSelectedFile(file);
    setStatus("");
  };

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    applyFile(e.target.files?.[0] ?? null);
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      setStatus("Esse arquivo não é um .xlsx. Exporte a planilha do Projectile nesse formato.");
      return;
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
    applyFile(file);
  };

  const clearFile = () => {
    if (fileInputRef.current) fileInputRef.current.value = "";
    applyFile(null);
    useReportStore.getState().resetParsedState();
    const step1 = document.getElementById("step1");
    if (step1) step1.style.display = "block";
  };

  const setMode = (mode: "single" | "multi") => {
    if (reportMode === mode) return;
    useReportStore.getState().setReportMode(mode);
  };

  const handleParse = async () => {
    if (!selectedFile) {
      setStatus("Escolha um arquivo .xlsx primeiro.");
      return;
    }
    setStatus("Analisando...");
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("mode", reportMode);
    try {
      const res = await fetch("/parse", { method: "POST", body: formData });
      if (!res.ok) throw new Error(await res.text());
      const data: ParseResponse = await res.json();

      if (data.packages.length === 0) {
        setStatus("Não encontrei grupos de atividades nessa planilha. Confira o aviso acima (se houver) ou o arquivo enviado.");
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
        collapsedGroupIds: new Set<string>(),
        fileName: "",
        fileNameEdited: false,
      }));
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
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("Erro ao analisar: " + msg);
    }
  };

  const changeFile = () => {
    const step1 = document.getElementById("step1");
    if (step1) step1.style.display = "block";
  };

  return (
    <>
      <div className="card upload-card" id="step1">
        <p className="upload-eyebrow">Projectile → Relatório</p>
        <h2>Importe a planilha de horas</h2>

        <div className="format-grid">
          <button
            type="button"
            className={`format-card ${reportMode === "single" ? "active" : ""}`}
            onClick={() => setMode("single")}
          >
            <span className="format-tag">1 DOC</span>
            <span className="format-title">Relatório único</span>
            <span className="format-desc">Todas as linhas viram um único relatório.</span>
          </button>
          <button
            type="button"
            className={`format-card ${reportMode === "multi" ? "active" : ""}`}
            onClick={() => setMode("multi")}
          >
            <span className="format-tag">N DOCS</span>
            <span className="format-title">Múltiplos relatórios</span>
            <span className="format-desc">Um relatório por Pacote de Trabalho.</span>
          </button>
        </div>

        <div
          className={`dropzone ${dragging ? "dragging" : ""} ${selectedFile ? "has-file" : ""}`.trim()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          {selectedFile ? (
            <>
              <div className="file-chip">
                <span className="file-chip-icon" aria-hidden="true">
                  <FileSpreadsheet size={16} strokeWidth={1.8} />
                </span>
                <span className="file-chip-meta">
                  <span className="file-chip-name" title={selectedFile.name}>{selectedFile.name}</span>
                  <span className="file-chip-size">{formatFileSize(selectedFile.size)}</span>
                </span>
              </div>
              <button type="button" className="btn-remove-file" title="Remover arquivo selecionado" onClick={clearFile}>
                <span>×</span> Remover
              </button>
            </>
          ) : (
            <>
              <span className="dropzone-hint">Solte o .xlsx aqui</span>
              <span className="dropzone-subhint">ou clique pra escolher o arquivo exportado do Projectile</span>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            title="Selecione o .xlsx exportado do Projectile para o mês/projeto."
            onChange={onFileInputChange}
            style={{ display: selectedFile ? "none" : "block" }}
          />
        </div>

        <button className="primary" onClick={handleParse}>Analisar planilha</button>
        <p className="muted">{status}</p>
      </div>
      <button type="button" id="btnChangeFileHidden" style={{ display: "none" }} onClick={changeFile} />
    </>
  );
}
