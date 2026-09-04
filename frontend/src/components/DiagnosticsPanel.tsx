import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Trash2, Pencil, Check, X, ChevronDown, RefreshCw } from "lucide-react";
import { ExtraHoursInput } from "./ExtraHoursInput";
import { ManagementFilters } from "./ManagementFilters";
import { useManagementStore } from "../store/useManagementStore";
import { useDiagnosticsStore, type Sample, type Project } from "../store/useDiagnosticsStore";
import { useClickOutside } from "../hooks/useClickOutside";
import { fmtNum } from "../utils/fmt";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
  return res.json();
}

function lastMonths(count: number): string[] {
  const out: string[] = [];
  const now = new Date();
  for (let i = 0; i < count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

const MONTH_OPTIONS = lastMonths(12);

// dropdown customizado genérico (reaproveita o mesmo visual dos filtros do
// Painel de Gerência, classes `.month-dropdown*`) — usado tanto pro seletor
// de projeto quanto pro de competência do formulário "Adicionar manualmente".
function SimpleDropdown({
  options,
  value,
  onChange,
  placeholder = "Selecione...",
  emptyLabel = "Nenhuma opção",
  className,
  searchable = false,
  listMinWidth,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyLabel?: string;
  className?: string;
  searchable?: boolean;
  listMinWidth?: number;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  // lista abre num portal (document.body) em vez de dentro do card — senão,
  // dentro de um container com scroll (.diagnostics-table-wrap), ela empurra
  // a altura do bloco de Amostras em vez de flutuar por cima dele.
  useClickOutside([wrapRef, listRef], () => setOpen(false), open);

  const toggleOpen = () => {
    if (!open && triggerRef.current) {
      const r = triggerRef.current.getBoundingClientRect();
      setRect({ top: r.bottom + 6, left: r.left, width: Math.max(r.width, listMinWidth ?? 0) });
    }
    setOpen((v) => !v);
  };

  useEffect(() => {
    if (open && searchable) {
      setSearch("");
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [open, searchable]);

  const selected = options.find((o) => o.value === value);
  const summary = selected ? selected.label : placeholder;
  const filtered = searchable && search ? options.filter((o) => o.label.toLowerCase().includes(search.toLowerCase())) : options;

  return (
    <div className={`month-dropdown ${className ?? ""}`} ref={wrapRef}>
      <button ref={triggerRef} type="button" className="month-dropdown-trigger" onClick={toggleOpen}>
        <span className="mgmt-filter-summary" title={summary}>{summary}</span>
        <ChevronDown size={15} strokeWidth={2} className={`month-dropdown-chevron ${open ? "open" : ""}`} />
      </button>
      {open &&
        rect &&
        createPortal(
          <div
            ref={listRef}
            className={`month-dropdown-list month-dropdown-list-portal ${searchable ? "month-dropdown-list-searchable" : ""}`}
            style={{ position: "fixed", top: rect.top, left: rect.left, width: rect.width }}
          >
            {searchable && (
              <input
                ref={searchRef}
                type="text"
                className="month-dropdown-search"
                placeholder="Buscar..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            )}
            <ul role="listbox">
              {filtered.length === 0 && (
                <li className="mgmt-filter-empty">{options.length === 0 ? emptyLabel : "Nenhum resultado"}</li>
              )}
              {filtered.map((o) => (
                <li key={o.value}>
                  <button
                    type="button"
                    className={`month-dropdown-option ${o.value === value ? "active" : ""}`}
                    onClick={() => {
                      onChange(o.value);
                      setOpen(false);
                    }}
                  >
                    {o.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>,
          document.body
        )}
    </div>
  );
}

function ProjectSelect({
  projects,
  value,
  onChange,
}: {
  projects: Project[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <SimpleDropdown
      className="diagnostics-project-dropdown"
      options={projects.map((p) => ({ value: p.id, label: `${p.client} — ${p.name}` }))}
      value={value}
      onChange={onChange}
      placeholder="Selecione o projeto..."
      emptyLabel="Nenhum projeto pros filtros atuais"
      searchable
      listMinWidth={340}
    />
  );
}

function MonthSelect({ value, onChange }: { value: string; onChange: (month: string) => void }) {
  return (
    <SimpleDropdown
      className="diagnostics-month-dropdown"
      options={MONTH_OPTIONS.map((m) => ({ value: m, label: m }))}
      value={value}
      onChange={onChange}
    />
  );
}

export function DiagnosticsPanel() {
  // reaproveita os mesmos filtros do Painel de Gerência (Período/Competência/
  // Cliente/Projeto) — busca TODAS as amostras uma vez e filtra no frontend,
  // já que essa tela precisa cruzar amostra com nome de projeto/cliente,
  // diferente do endpoint (que só filtra por mês).
  const rows = useManagementStore((s) => s.rows);
  const selectedMonths = useManagementStore((s) => s.selectedMonths);
  const filterClients = useManagementStore((s) => s.clients);
  const filterProjects = useManagementStore((s) => s.projects);
  const projectSendStatus = useManagementStore((s) => s.projectSendStatus);
  const loadManagementStore = useManagementStore((s) => s.load);

  const samples = useDiagnosticsStore((s) => s.samples);
  const skipped = useDiagnosticsStore((s) => s.skipped);
  const projects = useDiagnosticsStore((s) => s.projects);
  const refreshing = useDiagnosticsStore((s) => s.refreshing);
  const error = useDiagnosticsStore((s) => s.error);
  const load = useDiagnosticsStore((s) => s.load);
  const loadProjects = useDiagnosticsStore((s) => s.loadProjects);
  const setError = useDiagnosticsStore((s) => s.setError);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editProjectId, setEditProjectId] = useState("");
  const [editBilled, setEditBilled] = useState<number | null>(null);
  const [editDays, setEditDays] = useState<number | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createProjectId, setCreateProjectId] = useState("");
  const [createMonth, setCreateMonth] = useState(MONTH_OPTIONS[0]);
  const [createBilled, setCreateBilled] = useState<number | null>(null);
  const [createDays, setCreateDays] = useState<number | null>(null);

  useEffect(() => {
    load();
    loadProjects();
    loadManagementStore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clientFor = (projectId: string) => projects.find((p) => p.id === projectId)?.client ?? "—";

  // meses dentro do Período/Competência selecionados (mesmo cálculo que
  // ManagementPanel.tsx usa pra "displayRows"/"displayMonths").
  const displayMonths = useMemo(() => {
    const inPeriod = rows ?? [];
    const scoped = selectedMonths.length ? inPeriod.filter((r) => selectedMonths.includes(r.month)) : inPeriod;
    return new Set(scoped.map((r) => r.month));
  }, [rows, selectedMonths]);

  const displaySamples = samples.filter((s) => {
    if (!displayMonths.has(s.month)) return false;
    if (filterClients.length && !filterClients.includes(clientFor(s.project_id))) return false;
    if (filterProjects.length && !filterProjects.includes(s.project_name)) return false;
    return true;
  });
  const displaySkipped = skipped.filter((s) => displayMonths.has(String(s.received_at || "").slice(0, 7)));

  // projetos com horas dentro do Período/Competência selecionados — mesma
  // fonte que alimenta a tabela "Relatórios enviados" do Painel de Gerência.
  const projectIdsInPeriod = useMemo(() => {
    const ids = new Set<string>();
    for (const r of projectSendStatus) {
      if (displayMonths.has(r.month)) ids.add(r.project_id);
    }
    return ids;
  }, [projectSendStatus, displayMonths]);

  // mesmo recorte de Período/Competência/Cliente/Projeto do ManagementFilters,
  // aplicado à lista de projetos do seletor "Adicionar manualmente"/editar —
  // sem isso dava pra cadastrar/mudar uma amostra pra um projeto fora do
  // filtro ativo, ou de um mês sem nenhum apontamento no período em vista.
  const filteredProjects = projects.filter((p) => {
    if (!projectIdsInPeriod.has(p.id)) return false;
    if (filterClients.length && !filterClients.includes(p.client)) return false;
    if (filterProjects.length && !filterProjects.includes(p.name)) return false;
    return true;
  });

  // outras telas (Painel de Gerência) leem o mesmo JSON — sem isso, uma
  // correção feita aqui só apareceria lá depois de um F5.
  const refreshManagementPanel = () => {
    useManagementStore.getState().load(true, true);
  };

  const startEdit = (s: Sample) => {
    setEditingId(s.sample_id);
    setEditProjectId(s.project_id);
    setEditBilled(s.billed_hours);
    setEditDays(s.business_days);
  };
  const cancelEdit = () => setEditingId(null);

  const saveEdit = async (s: Sample) => {
    const project = projects.find((p) => p.id === editProjectId);
    const patch: Record<string, unknown> = {
      billed_hours: editBilled ?? 0,
      business_days: editDays ?? 0,
    };
    if (project && project.id !== s.project_id) {
      patch.project_id = project.id;
      patch.project_name = project.name;
    }
    try {
      await fetchJson(`/management/kpis/samples/${s.sample_id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      setEditingId(null);
      await load(true);
      refreshManagementPanel();
    } catch {
      setError("Não consegui salvar essa correção. Tenta de novo.");
    }
  };

  const deleteSample = async (s: Sample) => {
    if (!window.confirm(`Apagar a amostra de "${s.project_name}" (${s.month})? Isso não pode ser desfeito.`)) return;
    try {
      await fetchJson(`/management/kpis/samples/${s.sample_id}`, { method: "DELETE" });
      await load(true);
      refreshManagementPanel();
    } catch {
      setError("Não consegui apagar essa amostra. Tenta de novo.");
    }
  };

  const createManual = async () => {
    if (!createProjectId || createBilled === null || createDays === null) {
      setError("Preencha projeto, horas e dias antes de cadastrar.");
      return;
    }
    try {
      await fetchJson("/management/kpis/samples", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: createProjectId,
          month: createMonth,
          billed_hours: createBilled,
          business_days: createDays,
        }),
      });
      setShowCreate(false);
      setCreateProjectId("");
      setCreateBilled(null);
      setCreateDays(null);
      await load(true);
      refreshManagementPanel();
    } catch {
      setError("Não consegui cadastrar essa amostra. Tenta de novo.");
    }
  };

  const cancelCreate = () => {
    setShowCreate(false);
    setCreateProjectId("");
    setCreateMonth(MONTH_OPTIONS[0]);
    setCreateBilled(null);
    setCreateDays(null);
  };

  return (
    <div className="diagnostics-panel">
      <ManagementFilters showCostCenter={false} showPackage={false} />

      {error && <div className="card"><p className="muted">{error}</p></div>}

      <div className="card diagnostics-table-card diagnostics-samples-card">
        <div className="diagnostics-card-head">
          <h3>Amostras</h3>
          <div className="diagnostics-card-head-actions">
            <button type="button" className="btn-secondary" onClick={() => load(true)} disabled={refreshing}>
              <RefreshCw size={14} strokeWidth={2} className={refreshing ? "spin" : ""} />
              {refreshing ? "Atualizando..." : "Atualizar"}
            </button>
            <button type="button" className="primary" onClick={() => setShowCreate((v) => !v)}>
              Adicionar manualmente
            </button>
          </div>
        </div>

        {showCreate && (
          <div className="diagnostics-create-fields">
            <ProjectSelect projects={filteredProjects} value={createProjectId} onChange={setCreateProjectId} />
            <MonthSelect value={createMonth} onChange={setCreateMonth} />
            <ExtraHoursInput className="kpi-input" placeholder="Horas" value={createBilled} onCommit={setCreateBilled} />
            <ExtraHoursInput className="kpi-input kpi-input-days" placeholder="Dias" value={createDays} onCommit={setCreateDays} />
            <button type="button" className="primary" onClick={createManual}>Cadastrar</button>
            <button type="button" className="btn-secondary diagnostics-btn-danger" onClick={cancelCreate}>Cancelar</button>
          </div>
        )}

        {refreshing && <p className="muted">Carregando...</p>}
        {!refreshing && (
          <div className="kpi-table-wrap diagnostics-table-wrap">
            <table className="kpi-table">
              <thead>
                <tr>
                  <th>Cliente</th><th>Projeto</th><th>Pacote</th><th>Competência</th><th>Horas</th><th>Dias</th><th>Origem</th><th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {displaySamples.length === 0 && (
                  <tr><td colSpan={8} className="muted">Nenhuma amostra nesse período.</td></tr>
                )}
                {displaySamples.map((s) => (
                  <tr key={s.sample_id}>
                    {editingId === s.sample_id ? (
                      <>
                        <td colSpan={2}>
                          <ProjectSelect
                            projects={
                              filteredProjects.some((p) => p.id === editProjectId)
                                ? filteredProjects
                                : [...filteredProjects, ...projects.filter((p) => p.id === editProjectId)]
                            }
                            value={editProjectId}
                            onChange={setEditProjectId}
                          />
                        </td>
                        <td className="muted diagnostics-pacote-cell" title={s.pacote_scope || undefined}>{s.pacote_scope || "Projeto inteiro"}</td>
                        <td>{s.month}</td>
                        <td><ExtraHoursInput className="kpi-input" value={editBilled} onCommit={setEditBilled} /></td>
                        <td><ExtraHoursInput className="kpi-input kpi-input-days" value={editDays} onCommit={setEditDays} /></td>
                        <td>—</td>
                        <td className="diagnostics-actions-cell">
                          <div className="diagnostics-actions">
                            <button type="button" onClick={() => saveEdit(s)} title="Salvar"><Check size={15} /></button>
                            <button type="button" onClick={cancelEdit} title="Cancelar"><X size={15} /></button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td>{clientFor(s.project_id)}</td>
                        <td>{s.project_name}</td>
                        <td className="muted diagnostics-pacote-cell" title={s.pacote_scope || undefined}>{s.pacote_scope || "Projeto inteiro"}</td>
                        <td>{s.month}</td>
                        <td>{fmtNum(s.billed_hours)}</td>
                        <td>{fmtNum(s.business_days)}</td>
                        <td>
                          <span className={`diagnostics-source-badge ${s.source}`}>{s.source === "manual" ? "manual" : "e-mail"}</span>
                          {s.edited && <span className="diagnostics-edited-badge" title="Corrigido manualmente">editado</span>}
                        </td>
                        <td className="diagnostics-actions-cell">
                          <div className="diagnostics-actions">
                            <button type="button" onClick={() => startEdit(s)} title="Editar"><Pencil size={15} /></button>
                            <button type="button" onClick={() => deleteSample(s)} title="Apagar"><Trash2 size={15} /></button>
                          </div>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card diagnostics-table-card">
        <h3>E-mails pulados</h3>
        <div className="kpi-table-wrap diagnostics-table-wrap">
          <table className="kpi-table">
            <thead><tr><th>Data</th><th>Motivo</th></tr></thead>
            <tbody>
              {displaySkipped.length === 0 && <tr><td colSpan={2} className="muted">Nenhum e-mail pulado nesse período.</td></tr>}
              {displaySkipped.map((s, i) => (
                <tr key={`${s.message_id}-${i}`}>
                  <td>{s.received_at ? s.received_at.slice(0, 10) : "—"}</td>
                  <td>{s.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
