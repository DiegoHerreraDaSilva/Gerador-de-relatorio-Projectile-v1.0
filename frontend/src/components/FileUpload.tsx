import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Database, FileSpreadsheet, Upload } from "lucide-react";
import { useReportStore, MESES_PT, genId } from "../store/useReportStore";
import { useAuthStore } from "../store/useAuthStore";
import { useClickOutside } from "../hooks/useClickOutside";
import type { ParseResponse } from "../api/types";

function ClientDropdown({
  value,
  onChange,
  monthLabel,
}: {
  value: string;
  onChange: (c: string) => void;
  monthLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const [clients, setClients] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useClickOutside(wrapRef, () => setOpen(false), open);

  useEffect(() => {
    setLoading(true);
    fetch(`/management/clients-with-hours?month_label=${encodeURIComponent(monthLabel)}`)
      .then((res) => (res.ok ? res.json() : { clients: [] }))
      .then((data: { clients: string[] }) => setClients(data.clients || []))
      .catch(() => setClients([]))
      .finally(() => setLoading(false));
  }, [monthLabel]);

  useEffect(() => {
    if (open) {
      setSearch("");
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [open]);

  const filtered = clients.filter((c) => c.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="month-dropdown client-dropdown" ref={wrapRef}>
      <button type="button" className="month-dropdown-trigger" onClick={() => setOpen((v) => !v)}>
        <span className="client-dropdown-trigger-label" title={value}>{value || "Selecione um cliente"}</span>
        <ChevronDown size={16} strokeWidth={2} className={`month-dropdown-chevron ${open ? "open" : ""}`} />
      </button>
      {open && (
        <div className="month-dropdown-list client-dropdown-list">
          <input
            ref={searchRef}
            type="text"
            className="client-dropdown-search"
            placeholder="Buscar cliente..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <ul role="listbox">
            {loading && <li className="month-dropdown-empty">Carregando clientes...</li>}
            {!loading && filtered.length === 0 && (
              <li className="month-dropdown-empty">
                {clients.length === 0 ? "Nenhum cliente com horas nesse mês." : "Nenhum cliente encontrado."}
              </li>
            )}
            {filtered.map((c) => (
              <li key={c}>
                <button
                  type="button"
                  className={`month-dropdown-option ${c === value ? "active" : ""}`}
                  onClick={() => {
                    onChange(c);
                    setOpen(false);
                  }}
                >
                  {c}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

type ClientProject = { id: string; name: string; code?: string };

function displayProjectName(p: ClientProject): string {
  return p.code ? `${p.code} - ${p.name}` : p.name;
}

function ProjectMultiSelect({
  client,
  monthLabel,
  selected,
  onChange,
}: {
  client: string;
  monthLabel: string;
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const [projects, setProjects] = useState<ClientProject[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!client) {
      setProjects([]);
      return;
    }
    setLoading(true);
    fetch(`/management/client-projects?client=${encodeURIComponent(client)}&month_label=${encodeURIComponent(monthLabel)}`)
      .then((res) => (res.ok ? res.json() : { projects: [] }))
      .then((data: { projects: ClientProject[] }) => {
        const list = data.projects || [];
        setProjects(list);
        onChange(new Set(list.map((p) => p.id)));
      })
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, monthLabel]);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  if (!client) return null;
  if (loading) return <p className="db-search-hint">Carregando projetos...</p>;
  if (projects.length === 0) return <p className="db-search-hint">Esse cliente não tem projetos com horas nesse mês.</p>;

  return (
    <div className="client-projects-select">
      <div className="client-projects-select-head">
        <span className="mgmt-filter-label">Projetos ({selected.size}/{projects.length})</span>
        <span className="client-projects-select-actions">
          <button type="button" className="client-projects-select-all" onClick={() => onChange(new Set(projects.map((p) => p.id)))}>
            Selecionar todos
          </button>
          <button type="button" className="client-projects-select-all" onClick={() => onChange(new Set())}>
            Desmarcar todos
          </button>
        </span>
      </div>
      {projects.map((p) => (
        <label key={p.id} className="send-report-package-option">
          <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
          <span>{displayProjectName(p)}</span>
        </label>
      ))}
    </div>
  );
}

function MonthDropdown({ value, onChange }: { value: string; onChange: (m: string) => void }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useClickOutside(wrapRef, () => setOpen(false), open);

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

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

export function FileUpload() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatusText] = useState("");
  const [statusIsError, setStatusIsError] = useState(false);
  // wrapper em vez de trocar toda chamada existente — `isError` default
  // false cobre a maioria (mensagens neutras tipo "Analisando...",
  // "Encontrados N grupos."); só as chamadas que hoje representam falha
  // (arquivo inválido, "não encontrei", "Erro ao ...") passam `true`, pra
  // não ficarem com o mesmo cinza neutro de "Carregando"/status normal.
  const setStatus = (text: string, isError = false) => {
    setStatusText(text);
    setStatusIsError(isError);
  };
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [source, setSource] = useState<"file" | "db">("file");
  const [searching, setSearching] = useState(false);
  const [byClient, setByClient] = useState(false);
  const [selectedClient, setSelectedClient] = useState("");
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(new Set());
  const [clientReportMode, setClientReportMode] = useState<"pacote" | "projeto">("pacote");
  const isManager = useAuthStore((s) => s.user?.isManager);
  const reportMode = useReportStore((s) => s.reportMode);
  const showImportCard = useReportStore((s) => s.showImportCard);
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
      setStatus("Esse arquivo não é um .xlsx. Exporte a planilha do Projectile nesse formato.", true);
      return;
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
    applyFile(file);
  };

  const clearFile = () => {
    if (fileInputRef.current) fileInputRef.current.value = "";
    applyFile(null);
    useReportStore.getState().resetParsedState();
  };

  const setMode = (mode: "single" | "multi") => {
    if (reportMode === mode) return;
    useReportStore.getState().setReportMode(mode);
  };

  // `isPacoteMode` diz se cada pacote resultante representa só 1 pacote de
  // trabalho (true, "Múltiplos relatórios"/"Por pacote de trabalho") ou o
  // projeto/coleção inteira (false, "Relatório único"/"Por projeto") — vira
  // a marca oculta (`pacoteScope`) que impede o Painel de Gerência de marcar
  // o projeto inteiro como "Enviado" a partir de um relatório de 1 pacote só.
  const applyParseResponse = (data: ParseResponse, isPacoteMode: boolean) => {
    if (data.packages.length === 0) {
      setStatus("Não encontrei grupos de atividades. Confira o aviso acima (se houver).", true);
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
      pacoteScope: isPacoteMode ? p.key : null,
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
      applyParseResponse(data, reportMode === "multi");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("Erro ao analisar: " + msg, true);
    }
  };

  const handleSearchByClient = async () => {
    if (!selectedClient) {
      setStatus("Escolha um cliente primeiro.");
      return;
    }
    if (selectedProjectIds.size === 0) {
      setStatus("Escolha ao menos um projeto.");
      return;
    }
    setSearching(true);
    setStatus("Buscando no Projectile...");
    try {
      const res = await fetch("/parse-db-client", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_ids: Array.from(selectedProjectIds),
          month_label: monthLabel,
          mode: clientReportMode,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error((data && (data as any).detail) || (await res.text().catch(() => "")) || `Erro ${res.status}`);
      }
      const data: ParseResponse = await res.json();
      applyParseResponse(data, clientReportMode === "pacote");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("Erro ao buscar: " + msg, true);
    } finally {
      setSearching(false);
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
      applyParseResponse(data, reportMode === "multi");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("Erro ao buscar: " + msg, true);
    } finally {
      setSearching(false);
    }
  };

  return (
    <>
      <div className={`card upload-card ${showImportCard ? "visible" : ""}`} id="step1">
        <div className="upload-header">
          <span className="upload-doc-id">Projectile → Relatório</span>
          <span className="upload-header-rule" aria-hidden="true" />
        </div>
        <h2 className="upload-title">Importe a planilha de horas</h2>

        {!(source === "db" && byClient) && (
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
        )}

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
            {isManager && (
              <div className="source-switch source-switch-small">
                <div className={`source-switch-indicator ${byClient ? "right" : ""}`} aria-hidden="true" />
                <button type="button" className={`source-switch-option ${!byClient ? "active" : ""}`} onClick={() => setByClient(false)}>
                  Meu usuário
                </button>
                <button type="button" className={`source-switch-option ${byClient ? "active" : ""}`} onClick={() => setByClient(true)}>
                  Por cliente
                </button>
              </div>
            )}

            {byClient ? (
              <div className="db-search-date-block">
                <label className="db-search-label">Mês de referência</label>
                <div className="db-search-month-row">
                  <MonthDropdown value={searchMonth} onChange={setSearchMonth} />
                  <YearStepper value={searchYear} onChange={setSearchYear} />
                </div>

                <label className="db-search-label" style={{ marginTop: 10 }}>Cliente</label>
                <ClientDropdown
                  value={selectedClient}
                  monthLabel={monthLabel}
                  onChange={(c) => {
                    setSelectedClient(c);
                    setSelectedProjectIds(new Set());
                  }}
                />

                <ProjectMultiSelect
                  client={selectedClient}
                  monthLabel={monthLabel}
                  selected={selectedProjectIds}
                  onChange={setSelectedProjectIds}
                />

                {selectedClient && (
                  <div className="format-grid client-report-mode-grid">
                    <button
                      type="button"
                      className={`format-card ${clientReportMode === "pacote" ? "active" : ""}`}
                      onClick={() => setClientReportMode("pacote")}
                    >
                      <span className="format-tag">N DOCS</span>
                      <span className="format-title">Por pacote de trabalho</span>
                      <span className="format-desc">Um relatório por Pacote de Trabalho.</span>
                    </button>
                    <button
                      type="button"
                      className={`format-card ${clientReportMode === "projeto" ? "active" : ""}`}
                      onClick={() => setClientReportMode("projeto")}
                    >
                      <span className="format-tag">N DOCS</span>
                      <span className="format-title">Por projeto</span>
                      <span className="format-desc">Um relatório por projeto, com os grupos divididos por Pacote de Trabalho.</span>
                    </button>
                  </div>
                )}

                <p className="db-search-hint">
                  Busca as horas dos projetos escolhidos nesse mês, zipando um relatório por{" "}
                  {clientReportMode === "pacote" ? "pacote de trabalho" : "projeto"}.
                </p>
              </div>
            ) : (
              <div className="db-search-date-block">
                <label className="db-search-label">Mês de referência</label>
                <div className="db-search-month-row">
                  <MonthDropdown value={searchMonth} onChange={setSearchMonth} />
                  <YearStepper value={searchYear} onChange={setSearchYear} />
                </div>
                <p className="db-search-hint">Busca as horas apontadas pelo seu usuário do Projectile nesse mês.</p>
              </div>
            )}

            <button className="primary" onClick={byClient ? handleSearchByClient : handleSearchDb} disabled={searching}>
              {searching ? "Buscando..." : "Buscar horas"}
            </button>
          </>
        )}

        <p className={statusIsError ? "error-text" : "muted"}>{status}</p>
      </div>
    </>
  );
}
