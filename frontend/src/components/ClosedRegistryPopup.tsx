import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronRight, X, Lock } from "lucide-react";
import { useManagementStore } from "../store/useManagementStore";

async function fetchAllPackages(projectId: string): Promise<string[]> {
  const res = await fetch(`/management/projects/${encodeURIComponent(projectId)}/all-packages`);
  if (!res.ok) throw new Error(await res.text().catch(() => `Erro ${res.status}`));
  const data: { packages: string[] } = await res.json();
  return data.packages;
}

/** Popup "Fechados" — marca clientes/projetos inteiros que nunca enviam
 * relatório por e-mail pro cliente (permanente, não por competência, ver
 * `compute_monthly_kpis`/`get_closed_registry` no backend). Pacotes de
 * trabalho nunca são fecháveis individualmente — a lista de pacotes ao
 * expandir um projeto é só leitura, pra referência antes de decidir fechar
 * o projeto inteiro. */
export function ClosedRegistryPopup({ onClose }: { onClose: () => void }) {
  const closedRegistryProjects = useManagementStore((s) => s.closedRegistryProjects);
  const closedRegistryLoading = useManagementStore((s) => s.closedRegistryLoading);
  const closedClients = useManagementStore((s) => s.closedClients);
  const closedProjects = useManagementStore((s) => s.closedProjects);
  // mesma lista de nomes de projeto já calculada pro resto do painel,
  // recortada por Cliente/Projeto/Período/Competência (compute_monthly_kpis,
  // "available_projects") — reaproveitada aqui pra o popup mostrar só o que
  // já está filtrado no dashboard, em vez de TODO o Projectile sempre.
  const availableProjects = useManagementStore((s) => s.availableProjects);
  const loadClosedRegistry = useManagementStore((s) => s.loadClosedRegistry);
  const toggleClosedClient = useManagementStore((s) => s.toggleClosedClient);
  const toggleClosedProject = useManagementStore((s) => s.toggleClosedProject);

  const [search, setSearch] = useState("");
  const [expandedClients, setExpandedClients] = useState<Set<string>>(new Set());
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());
  const [pacotesByProject, setPacotesByProject] = useState<Record<string, string[]>>({});
  const [loadingPacotesFor, setLoadingPacotesFor] = useState<string | null>(null);

  useEffect(() => {
    loadClosedRegistry();
  }, [loadClosedRegistry]);

  // Esc fecha o popup — mesma convenção de SendReportModal.tsx.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const searchNormalized = search.trim().toLowerCase();
  const clientGroups = useMemo(() => {
    const availableSet = new Set(availableProjects);
    const filteredByDashboard = closedRegistryProjects.filter((p) => availableSet.has(p.name));
    const byClient = new Map<string, typeof closedRegistryProjects>();
    for (const p of filteredByDashboard) {
      const list = byClient.get(p.client) ?? [];
      list.push(p);
      byClient.set(p.client, list);
    }
    for (const list of byClient.values()) list.sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
    return Array.from(byClient.entries())
      .filter(([client, projects]) =>
        !searchNormalized ||
        client.toLowerCase().includes(searchNormalized) ||
        projects.some((p) => p.name.toLowerCase().includes(searchNormalized))
      )
      .sort(([a], [b]) => a.localeCompare(b, "pt-BR"));
  }, [closedRegistryProjects, availableProjects, searchNormalized]);

  const toggleClientExpanded = (client: string) => {
    setExpandedClients((prev) => {
      const next = new Set(prev);
      if (next.has(client)) next.delete(client);
      else next.add(client);
      return next;
    });
  };

  const toggleProjectExpanded = (projectId: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
        if (!(projectId in pacotesByProject)) {
          setLoadingPacotesFor(projectId);
          fetchAllPackages(projectId)
            .then((pacotes) => setPacotesByProject((prevPacotes) => ({ ...prevPacotes, [projectId]: pacotes })))
            .catch(() => setPacotesByProject((prevPacotes) => ({ ...prevPacotes, [projectId]: [] })))
            .finally(() => setLoadingPacotesFor((cur) => (cur === projectId ? null : cur)));
        }
      }
      return next;
    });
  };

  return createPortal(
    <div className="modal-backdrop closed-registry-backdrop" onClick={onClose}>
      <div className="modal-card closed-registry-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>
            <Lock size={16} strokeWidth={2} /> Clientes/Projetos fechados
          </h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar">
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <div className="modal-body">
          <p className="muted">
            Marque um cliente ou projeto inteiro que nunca envia relatório de horas por e-mail — fica de fora de
            "Não enviados" pra sempre, em todo mês passado e futuro, até você desmarcar aqui. A lista abaixo segue os
            filtros de Cliente/Projeto/Período/Competência do painel — ajuste-os pra ver outros clientes/projetos.
          </p>
          <input
            type="text"
            className="closed-registry-search"
            placeholder="Buscar cliente ou projeto..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          {closedRegistryLoading && closedRegistryProjects.length === 0 && <p className="muted">Carregando...</p>}
          {!closedRegistryLoading && clientGroups.length === 0 && (
            <p className="muted">
              {searchNormalized
                ? "Nenhum resultado pra essa busca."
                : "Nenhum projeto no recorte atual do painel — ajuste Cliente/Projeto/Período/Competência lá em cima."}
            </p>
          )}

          <div className="closed-registry-tree">
            {clientGroups.map(([client, projects]) => {
              const clientClosed = closedClients.includes(client);
              const clientExpanded = expandedClients.has(client);
              return (
                <div key={client} className="closed-registry-client-row">
                  <div className="closed-registry-checkbox">
                    <button
                      type="button"
                      className="closed-registry-expand"
                      onClick={() => toggleClientExpanded(client)}
                      aria-label={clientExpanded ? "Recolher cliente" : "Expandir cliente"}
                    >
                      {clientExpanded ? <ChevronDown size={15} strokeWidth={2} /> : <ChevronRight size={15} strokeWidth={2} />}
                    </button>
                    <label>
                      <input
                        type="checkbox"
                        checked={clientClosed}
                        onChange={(e) => toggleClosedClient(client, e.target.checked)}
                      />
                      <strong>{client}</strong>
                    </label>
                  </div>

                  {clientExpanded && (
                    <div className="closed-registry-projects">
                      {projects.map((project) => {
                        const projectExpanded = expandedProjects.has(project.id);
                        const projectClosed = clientClosed || closedProjects.includes(project.id);
                        const pacotes = pacotesByProject[project.id];
                        return (
                          <div key={project.id} className="closed-registry-project-row">
                            <div className="closed-registry-checkbox">
                              <button
                                type="button"
                                className="closed-registry-expand"
                                onClick={() => toggleProjectExpanded(project.id)}
                                aria-label={projectExpanded ? "Recolher projeto" : "Expandir projeto (ver pacotes)"}
                              >
                                {projectExpanded ? <ChevronDown size={14} strokeWidth={2} /> : <ChevronRight size={14} strokeWidth={2} />}
                              </button>
                              <label title={clientClosed ? "Fechado porque o cliente inteiro está fechado" : undefined}>
                                <input
                                  type="checkbox"
                                  checked={projectClosed}
                                  disabled={clientClosed}
                                  onChange={(e) => toggleClosedProject(project.id, e.target.checked)}
                                />
                                {project.name}
                              </label>
                            </div>

                            {projectExpanded && (
                              <ul className="closed-registry-pacotes">
                                {loadingPacotesFor === project.id && <li className="muted">Carregando pacotes...</li>}
                                {loadingPacotesFor !== project.id && (pacotes ?? []).length === 0 && (
                                  <li className="muted">Nenhum pacote encontrado.</li>
                                )}
                                {loadingPacotesFor !== project.id && (pacotes ?? []).map((pacote) => <li key={pacote}>{pacote}</li>)}
                              </ul>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>Fechar</button>
        </div>
      </div>
    </div>,
    document.body
  );
}
