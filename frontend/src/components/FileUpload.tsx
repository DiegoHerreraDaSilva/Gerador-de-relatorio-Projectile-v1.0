import { useEffect, useRef, useState } from "react";
import {
  Archive,
  Calendar,
  CalendarRange,
  ChevronDown,
  Database,
  FileSpreadsheet,
  FileText,
  GitBranch,
  Plus,
  Search,
  ShieldCheck,
  Upload,
  User,
} from "lucide-react";
import { useReportStore, MESES_PT, genId } from "../store/useReportStore";
import { useReportTabsStore } from "../store/useReportTabsStore";
import { useAuthStore } from "../store/useAuthStore";
import { useClickOutside } from "../hooks/useClickOutside";
import { buildPeriodLabel, getReportYearOptions, parsePeriodLabelForControls } from "../utils/period";
import { getReportImportActionState } from "../utils/reportImport";
import { StepCard } from "./StepCard";
import { RadioCardGroup } from "./RadioCard";
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
      <button
        type="button"
        className="month-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
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
                  role="option"
                  aria-selected={c === value}
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
    onChange(new Set());
    setLoading(true);
    fetch(`/management/client-projects?client=${encodeURIComponent(client)}&month_label=${encodeURIComponent(monthLabel)}`)
      .then((res) => (res.ok ? res.json() : { projects: [] }))
      .then((data: { projects: ClientProject[] }) => setProjects(data.projects || []))
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
    <div className="client-projects-select" role="group" aria-label="Projetos do cliente">
      {projects.map((p) => (
        <label key={p.id} className={`client-project-option ${selected.has(p.id) ? "active" : ""}`}>
          <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
          <span>{displayProjectName(p)}</span>
        </label>
      ))}
    </div>
  );
}

function PeriodSelect({
  value,
  label,
  options,
  onChange,
}: {
  value: string;
  label: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      className="period-select"
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {options.map((option) => <option key={option} value={option}>{option}</option>)}
    </select>
  );
}

/** Seletor de "Mês único"/"Período" da busca "Buscar do Projectile" —
 * compartilhado pelos dois submodos ("Meu usuário"/"Por cliente"), que hoje
 * têm o mesmo bloco de mês único duplicado. Lê/escreve direto na store (não
 * recebe props) — o mês INICIAL sempre é `header.monthLabel` (igual antes
 * desta feature); o mês final (só usado em modo "Período") é
 * `importEndMonthLabel`, novo campo por guia (mesmo motivo dos outros
 * campos de import já viverem na store, ver comentário acima deles).
 * Não renderiza nenhum wrapper em volta — quem chama decide o card/bloco
 * que envolve (StepCard "Selecionar período" no fluxo de reforma da UI). */
function PeriodPicker() {
  const monthLabel = useReportStore((s) => s.header.monthLabel);
  const setHeaderField = useReportStore((s) => s.setHeaderField);
  const periodMode = useReportStore((s) => s.importPeriodMode);
  const setPeriodMode = useReportStore((s) => s.setImportPeriodMode);
  const endMonthLabel = useReportStore((s) => s.importEndMonthLabel);
  const setEndMonthLabel = useReportStore((s) => s.setImportEndMonthLabel);

  const { startMonth, startYear, endMonth } = parsePeriodLabelForControls(monthLabel, endMonthLabel);
  const yearOptions = getReportYearOptions();

  const applyRange = (sMonth: string, year: string, eMonth: string) => {
    setHeaderField("monthLabel", buildPeriodLabel(sMonth, year, eMonth, year));
    setEndMonthLabel(`${eMonth}/${year}`);
  };

  return (
    <>
      <RadioCardGroup
        name="import-period-mode"
        ariaLabel="Quantidade de meses"
        value={periodMode}
        onChange={(value) => setPeriodMode(value as "single" | "range")}
        layout="horizontal"
        density="compact"
        options={[
          { value: "single", icon: <Calendar size={18} strokeWidth={1.8} />, title: "Mês único" },
          { value: "range", icon: <CalendarRange size={18} strokeWidth={1.8} />, title: "Múltiplos meses" },
        ]}
      />

      {periodMode === "single" ? (
        <div className="period-fields period-fields-single">
          <div className="period-field">
            <label className="db-search-label">Mês</label>
            <PeriodSelect value={startMonth} label="Mês" options={MESES_PT} onChange={(m) => setHeaderField("monthLabel", `${m}/${startYear}`)} />
          </div>
          <div className="period-field">
            <label className="db-search-label">Ano</label>
            <PeriodSelect value={startYear} label="Ano" options={yearOptions} onChange={(y) => setHeaderField("monthLabel", `${startMonth}/${y}`)} />
          </div>
        </div>
      ) : (
        <div className="period-fields period-fields-range">
          <div className="period-field">
            <label className="db-search-label">Mês inicial</label>
            <PeriodSelect value={startMonth} label="Mês inicial" options={MESES_PT} onChange={(m) => applyRange(m, startYear, endMonth)} />
          </div>
          <div className="period-field">
            <label className="db-search-label">Mês final</label>
            <PeriodSelect value={endMonth} label="Mês final" options={MESES_PT} onChange={(m) => applyRange(startMonth, startYear, m)} />
          </div>
          <div className="period-field period-field-year">
            <label className="db-search-label">Ano</label>
            <PeriodSelect value={startYear} label="Ano" options={yearOptions} onChange={(y) => applyRange(startMonth, y, endMonth)} />
          </div>
        </div>
      )}
    </>
  );
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
  const [parsing, setParsing] = useState(false);
  const [searching, setSearching] = useState(false);
  const isManager = useAuthStore((s) => s.user?.isManager);
  const reportMode = useReportStore((s) => s.reportMode);
  const showImportCard = useReportStore((s) => s.showImportCard);
  const monthLabel = useReportStore((s) => s.header.monthLabel);
  const setHeaderField = useReportStore((s) => s.setHeaderField);
  const setPackages = useReportStore((s) => s.setPackages);
  const setIssues = useReportStore((s) => s.setIssues);
  // seleção deste card (fonte/cliente/projetos/modo) vive na store, não em
  // useState local — cada guia (ver useReportTabsStore) precisa manter a
  // própria busca configurada ao voltar pra ela.
  const source = useReportStore((s) => s.importSource);
  const setSource = useReportStore((s) => s.setImportSource);
  const byClient = useReportStore((s) => s.importByClient);
  const setByClient = useReportStore((s) => s.setImportByClient);
  const selectedClient = useReportStore((s) => s.importSelectedClient);
  const setSelectedClient = useReportStore((s) => s.setImportSelectedClient);
  const selectedProjectIds = useReportStore((s) => s.importSelectedProjectIds);
  const setSelectedProjectIds = useReportStore((s) => s.setImportSelectedProjectIds);
  const clientReportMode = useReportStore((s) => s.importClientReportMode);
  const setClientReportMode = useReportStore((s) => s.setImportClientReportMode);
  const activeTabId = useReportTabsStore((s) => s.activeTabId);

  // reseta o que é puramente transitório desta tela (arquivo ainda não
  // enviado, resultado da última busca) ao trocar de guia — um arquivo
  // escolhido mas não analisado, ou a mensagem de status da guia anterior,
  // não fazem sentido continuar aparecendo numa guia diferente. Feito via
  // efeito (não via `key={activeTabId}` em App.tsx) porque forçar
  // desmontagem/remontagem do componente inteiro depende do React
  // reconciliar de forma consistente duas stores Zustand independentes
  // mudando no mesmo clique (useReportTabsStore.activeTabId e
  // useReportStore) — visto ao vivo causando tanto o componente antigo
  // nunca desmontar quanto instâncias "fantasmas" acumulando na tela.
  useEffect(() => {
    setSelectedFile(null);
    setDragging(false);
    setParsing(false);
    setSearching(false);
    setStatus("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTabId]);

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
      language: "pt" as const,
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
    setParsing(true);
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
    } finally {
      setParsing(false);
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

  // Etapa 03 ("Como organizar") sempre existe; Etapa 02 ("Quais dados
  // deseja buscar") só existe no fluxo Projectile E pra quem é gerente —
  // os números dos cards seguintes precisam se ajustar conforme ela existe
  // ou não (3 cards no total pra quem não é gerente, mesmo em Projectile).
  const showSourceStep2 = source === "db" && isManager;
  const organizeStepNumber = showSourceStep2 ? 3 : 2;
  const periodStepNumber = showSourceStep2 ? 4 : 3;
  const flowDescription =
    source === "file"
      ? "Fluxo de arquivo local selecionado — 3 etapas."
      : `Fluxo Buscar no Projectile selecionado — ${showSourceStep2 ? "4" : "3"} etapas.`;
  const actionState = getReportImportActionState({
    source,
    hasFile: Boolean(selectedFile),
    busy: source === "file" ? parsing : searching,
    byClient,
    hasClient: Boolean(selectedClient),
    selectedProjectCount: selectedProjectIds.size,
  });

  return (
    <>
      <div className={`steps-wrap ${showImportCard ? "visible" : ""}`} id="step1">
        <p className="sr-only" aria-live="polite">{flowDescription}</p>

        <div className="step-cards-row">
          <StepCard
            number={1}
            title="De onde vêm os dados?"
            description="Escolha um arquivo local ou conecte-se diretamente ao Projectile."
          >
            <RadioCardGroup
              name="import-source"
              ariaLabel="De onde vêm os dados?"
              value={source}
              onChange={(v) => setSource(v as "file" | "db")}
              options={[
                {
                  value: "db",
                  icon: <Database size={18} strokeWidth={1.8} />,
                  title: "Buscar no Projectile",
                  description: "Importe os dados diretamente do sistema.",
                },
                {
                  value: "file",
                  icon: <Upload size={18} strokeWidth={1.8} />,
                  title: "Arquivo do computador",
                  description: "Envie a planilha exportada em formato XLSX.",
                },
              ]}
            />
          </StepCard>

          {source === "file" ? (
            <>
              <StepCard
                number={2}
                title="Selecione a planilha"
                description="Arraste o arquivo .xlsx aqui ou selecione no computador, até 25 MB."
              >
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
                      <span className="dropzone-hint">Arraste o arquivo para cá ou selecione no computador</span>
                      <span className="dropzone-subhint">.xlsx exportado do Projectile, até 25 MB</span>
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
              </StepCard>

              <StepCard
                number={3}
                title="Como deseja organizar o relatório?"
                description="Você poderá revisar o agrupamento antes de gerar o documento."
              >
                <RadioCardGroup
                  name="file-report-organization"
                  ariaLabel="Organização do relatório"
                  value={reportMode}
                  onChange={(value) => setMode(value as "single" | "multi")}
                  options={[
                    { value: "single", icon: <FileText size={18} strokeWidth={1.8} />, title: "Relatório consolidado", description: "Todas as linhas em um único documento." },
                    { value: "multi", icon: <Archive size={18} strokeWidth={1.8} />, title: "Um relatório por pacote", description: "Cria um documento para cada pacote de trabalho." },
                  ]}
                />
              </StepCard>
            </>
          ) : (
            <>
              {showSourceStep2 && (
                <StepCard
                  number={2}
                  title="Quais dados deseja buscar?"
                  description="Use seus próprios registros ou localize um cliente."
                >
                  <RadioCardGroup
                    name="import-by-client"
                    ariaLabel="Quais dados deseja buscar?"
                    value={byClient ? "client" : "self"}
                    onChange={(v) => setByClient(v === "client")}
                    options={[
                      {
                        value: "self",
                        icon: <User size={18} strokeWidth={1.8} />,
                        title: "Meu usuário",
                        description: "Usar os registros vinculados ao seu perfil.",
                      },
                      {
                        value: "client",
                        icon: (
                          <span className="search-plus-icon">
                            <Search size={18} strokeWidth={1.8} />
                            <Plus className="search-plus-icon-mark" size={9} strokeWidth={2.4} />
                          </span>
                        ),
                        title: "Buscar cliente",
                        description: "Localizar um cliente ou projeto no Projectile.",
                      },
                    ]}
                  />
                </StepCard>
              )}

              <StepCard
                number={organizeStepNumber}
                title="Como deseja organizar o relatório?"
                description="Você poderá revisar o agrupamento antes de gerar o documento."
              >
                {byClient ? (
                  <RadioCardGroup
                    name="client-report-organization"
                    ariaLabel="Organização do relatório"
                    value={clientReportMode}
                    onChange={(value) => setClientReportMode(value as "pacote" | "projeto")}
                    options={[
                      { value: "pacote", icon: <Archive size={18} strokeWidth={1.8} />, title: "Um relatório por pacote", description: "Cria um documento para cada pacote de trabalho." },
                      { value: "projeto", icon: <FileText size={18} strokeWidth={1.8} />, title: "Um relatório por projeto", description: "Agrupa os pacotes de trabalho em um documento por projeto." },
                    ]}
                  />
                ) : (
                  <RadioCardGroup
                    name="projectile-report-organization"
                    ariaLabel="Organização do relatório"
                    value={reportMode}
                    onChange={(value) => setMode(value as "single" | "multi")}
                    options={[
                      { value: "single", icon: <FileText size={18} strokeWidth={1.8} />, title: "Relatório consolidado", description: "Todas as linhas em um único documento." },
                      { value: "multi", icon: <Archive size={18} strokeWidth={1.8} />, title: "Um relatório por pacote", description: "Cria um documento para cada pacote de trabalho." },
                    ]}
                  />
                )}
              </StepCard>

              <StepCard
                number={periodStepNumber}
                title="Selecionar período"
                description="Defina o mês e o ano dos dados do Projectile."
              >
                <PeriodPicker />
              </StepCard>
            </>
          )}
        </div>

        {source === "db" && byClient && (
          <div className="step-card client-projects-panel">
            <div className="step-card-head-plain client-projects-panel-head">
              <span className="step-card-badge" aria-hidden="true"><GitBranch size={15} strokeWidth={2} /></span>
              <div>
                <h2>Selecionar cliente e projetos</h2>
                <p>Escolha um cliente e marque um ou mais projetos associados.</p>
              </div>
            </div>
            <div className="client-projects-columns">
              <div className="client-projects-col">
                <label className="db-search-label">Selecionar cliente</label>
                <ClientDropdown
                  value={selectedClient}
                  monthLabel={monthLabel}
                  onChange={(c) => {
                    setSelectedClient(c);
                    setSelectedProjectIds(new Set());
                  }}
                />
              </div>
              <div className="client-projects-col">
                <label className="db-search-label">Selecionar projeto</label>
                {selectedClient ? (
                  <ProjectMultiSelect
                    client={selectedClient}
                    monthLabel={monthLabel}
                    selected={selectedProjectIds}
                    onChange={setSelectedProjectIds}
                  />
                ) : (
                  <p className="db-search-hint">Escolha um cliente pra ver os projetos disponíveis.</p>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="action-bar">
          <span className="action-bar-info">
            <ShieldCheck size={16} strokeWidth={1.8} aria-hidden="true" />
            Seus dados são processados com segurança.
          </span>
          <button
            type="button"
            className="primary"
            onClick={source === "file" ? handleParse : (byClient ? handleSearchByClient : handleSearchDb)}
            disabled={actionState.disabled}
          >
            {actionState.label}
          </button>
        </div>

        <p
          className={`import-status ${statusIsError ? "error-text" : "muted"}`}
          role={statusIsError ? "alert" : "status"}
          aria-live="polite"
        >
          {status}
        </p>
      </div>
    </>
  );
}
