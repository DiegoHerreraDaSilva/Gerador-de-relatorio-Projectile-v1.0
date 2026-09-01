import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Database, FileSpreadsheet, Upload } from "lucide-react";
import { useReportStore, MESES_PT } from "../store/useReportStore";
import type { ParseResponse } from "../api/types";

function MonthDropdown({ value, onChange }: { value: string; onChange: (m: string) => void }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onOutside = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [open]);

  return (
    <div className="month-dropdown" ref={wrapRef}>
      <button type="button" className="month-dropdown-trigger" onClick={() => setOpen((v) => !v)}>
        {value}
        <ChevronDown size={16} strokeWidth={2} className={`month-dropdown-chevron ${open ? "open" : ""}`} />
      </button>
      {open && (
        <ul className="month-dropdown-list" role="listbox">
          {MESES_PT.map((m) => (
            <li key={m}>
              <button
                type="button"
                className={`month-dropdown-option ${m === value ? "active" : ""}`}
                onClick={() => {
                  onChange(m);
                  setOpen(false);
                }}
              >
                {m}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function YearStepper({ value, onChange }: { value: string; onChange: (y: string) => void }) {
  const num = parseInt(value, 10) || new Date().getFullYear();
  return (
    <div className="year-stepper">
      <input
        type="text"
        inputMode="numeric"
        className="year-stepper-input"
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 4))}
      />
      <div className="year-stepper-buttons">
        <button type="button" aria-label="Ano seguinte" onClick={() => onChange(String(num + 1))}>
          <ChevronUp size={12} strokeWidth={2.5} />
        </button>
        <button type="button" aria-label="Ano anterior" onClick={() => onChange(String(num - 1))}>
          <ChevronDown size={12} strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
}

function parseMonthLabel(label: string): { month: string; year: string } {
  const match = /^([^/]+)\/(\d{4})$/.exec(label || "");
  if (!match) return { month: MESES_PT[0], year: String(new Date().getFullYear()) };
  const found = MESES_PT.find((m) => m.toLowerCase() === match[1].trim().toLowerCase());
  return { month: found || MESES_PT[0], year: match[2] };
}

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
  const [source, setSource] = useState<"file" | "db">("file");
  const [searching, setSearching] = useState(false);
  const reportMode = useReportStore((s) => s.reportMode);
  const monthLabel = useReportStore((s) => s.header.monthLabel);
  const setHeaderField = useReportStore((s) => s.setHeaderField);
  const setPackages = useReportStore((s) => s.setPackages);
  const setIssues = useReportStore((s) => s.setIssues);

  const { month: searchMonth, year: searchYear } = parseMonthLabel(monthLabel);
  const setSearchMonth = (month: string) => setHeaderField("monthLabel", `${month}/${searchYear}`);
  const setSearchYear = (year: string) => setHeaderField("monthLabel", `${searchMonth}/${year}`);

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

  const applyParseResponse = (data: ParseResponse) => {
    if (data.packages.length === 0) {
      setStatus("Não encontrei grupos de atividades. Confira o aviso acima (se houver).");
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
        activities: g.activities.map((a) => ({ id: genId(), description: a.description, hours: a.hours, extra: false })),
      })),
      collapsedGroupIds: new Set<string>(),
      fileName: "",
      fileNameEdited: false,
      chartBar: false,
      chartPie: false,
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
      applyParseResponse(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("Erro ao analisar: " + msg);
    }
  };

  const handleSearchDb = async () => {
    setSearching(true);
    setStatus("Buscando no Projectile...");
    try {
      const res = await fetch("/parse-db", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ month_label: monthLabel, mode: reportMode }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error((data && (data as any).detail) || (await res.text().catch(() => "")) || `Erro ${res.status}`);
      }
      const data: ParseResponse = await res.json();
      applyParseResponse(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("Erro ao buscar: " + msg);
    } finally {
      setSearching(false);
    }
  };

  const changeFile = () => {
    const step1 = document.getElementById("step1");
    if (step1) step1.style.display = "block";
  };

  return (
    <>
      <div className="card upload-card" id="step1">
        <div className="upload-header">
          <span className="upload-doc-id">Projectile → Relatório</span>
          <span className="upload-header-rule" aria-hidden="true" />
        </div>
        <h2 className="upload-title">Importe a planilha de horas</h2>

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

        <p className="source-switch-eyebrow">Fonte dos dados</p>
        <div className="source-switch">
          <div className={`source-switch-indicator ${source === "db" ? "right" : ""}`} aria-hidden="true" />
          <button type="button" className={`source-switch-option ${source === "file" ? "active" : ""}`} onClick={() => setSource("file")}>
            <Upload size={17} strokeWidth={2} />
            Enviar arquivo
          </button>
          <button type="button" className={`source-switch-option ${source === "db" ? "active" : ""}`} onClick={() => setSource("db")}>
            <Database size={17} strokeWidth={2} />
            Buscar do Projectile
          </button>
        </div>

        {source === "file" ? (
          <>
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
          </>
        ) : (
          <>
            <div className="db-search-date-block">
              <label className="db-search-label">Mês de referência</label>
              <div className="db-search-month-row">
                <MonthDropdown value={searchMonth} onChange={setSearchMonth} />
                <YearStepper value={searchYear} onChange={setSearchYear} />
              </div>
              <p className="db-search-hint">Busca as horas apontadas pelo seu usuário do Projectile nesse mês.</p>
            </div>
            <button className="primary" onClick={handleSearchDb} disabled={searching}>
              {searching ? "Buscando..." : "Buscar horas"}
            </button>
          </>
        )}

        <p className="muted">{status}</p>
      </div>
      <button type="button" id="btnChangeFileHidden" style={{ display: "none" }} onClick={changeFile} />
    </>
  );
}
