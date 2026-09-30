import { useEffect, useMemo, useRef, useState } from "react";
import { useModal } from "../hooks/useModal";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  CalendarClock,
  Layers,
  Plus,
  Trash2,
  UserRound,
  Users,
  X,
  Package as PackageIcon,
  FolderTree,
} from "lucide-react";
import { MultiSelectDropdown } from "./FilterDropdown";
import { RadioCardGroup } from "./RadioCard";
import { ReviewerPicker } from "./ReviewerPicker";
import {
  useAutoGenerationStore,
  type CustomPreview,
  type CustomSplit,
  type CustomUnit,
} from "../store/useAutoGenerationStore";
import { api } from "../utils/autoApi";
import { fmtNum } from "../utils/fmt";
import {
  blockProblem,
  buildCustomScope,
  describeBlock,
  emptyBlock,
  periodForCompetence,
  periodLabelOf,
  type BlockDraft,
  type PeriodDraft,
} from "../utils/customScope";

type ProjectOption = { id: string; name: string; code: string };
type EmployeeOption = { employee_id: string; name: string; cost_center: string | null };

const SPLIT_OPTIONS: Array<{ value: CustomSplit; icon: JSX.Element; title: string; description: string }> = [
  {
    value: "nenhum",
    icon: <Layers size={18} strokeWidth={1.8} />,
    title: "Tudo junto",
    description: "Um só item na lista, com tudo dentro.",
  },
  {
    value: "projeto",
    icon: <FolderTree size={18} strokeWidth={1.8} />,
    title: "Um item por projeto",
    description: "Separa a lista em um item para cada projeto.",
  },
  {
    value: "pacote",
    icon: <PackageIcon size={18} strokeWidth={1.8} />,
    title: "Um item por pacote de trabalho",
    description: "Separa a lista em um item para cada pacote de trabalho.",
  },
  {
    value: "colaborador",
    icon: <UserRound size={18} strokeWidth={1.8} />,
    title: "Um item por colaborador",
    description: "Separa a lista em um item para cada pessoa.",
  },
];

const UNIT_OPTIONS: Array<{ value: CustomUnit; icon: JSX.Element; title: string; description: string }> = [
  {
    value: "projeto",
    icon: <FolderTree size={18} strokeWidth={1.8} />,
    title: "Um relatório por projeto",
    description: "Cada projeto tem número e arquivo próprios. Os pacotes de trabalho viram grupos.",
  },
  {
    value: "pacote",
    icon: <PackageIcon size={18} strokeWidth={1.8} />,
    title: "Um relatório por pacote de trabalho",
    description: "Cada pacote de trabalho tem número e arquivo próprios. O começo da descrição vira o grupo.",
  },
];

// o que cada filtro faz (tooltip instantâneo no rótulo)
const HINTS = {
  client:
    "Pega os projetos deste cliente que têm horas no período. Dá pra marcar vários. Sem nada marcado, vale qualquer cliente.",
  project: "Só aparecem os projetos dos clientes marcados. Sem nada marcado, entram todos os projetos desses clientes.",
  package:
    "Limita a um pacote de trabalho do projeto. Só funciona com UM projeto marcado. Sem nada marcado, entram todos os pacotes.",
  employee: "Só as horas apontadas por estas pessoas. Sem nada marcado, entram as horas de todos os colaboradores.",
} as const;

/** O que a escolha de organização produz, em uma frase. */
export function howItWorks(splitBy: CustomSplit, unit: CustomUnit): string {
  const documents = {
    nenhum: "Vai criar 1 item na lista, com tudo o que os recortes pegaram",
    projeto: "Vai criar 1 item na lista para cada projeto",
    pacote: "Vai criar 1 item na lista para cada pacote de trabalho",
    colaborador: "Vai criar 1 item na lista para cada colaborador",
  }[splitBy];
  const inside =
    unit === "projeto"
      ? "Dentro de cada item, cada projeto é um relatório (com número e arquivo próprios) e os pacotes de trabalho viram grupos."
      : "Dentro de cada item, cada pacote de trabalho é um relatório (com número e arquivo próprios) e o começo da descrição, antes do “-”, vira o grupo.";
  return `${documents}. ${inside}`;
}

const projectLabel = (p: ProjectOption) => (p.code ? `${p.code} - ${p.name}` : p.name);

let blockCounter = 0;
const newBlock = () => emptyBlock(`bloco-${++blockCounter}`);

/** "Nova geração personalizada": recorte livre de colaborador, cliente,
 * projeto e pacote, num período qualquer. O gerente monta blocos (os filtros
 * de um bloco se cruzam, os blocos se somam), escolhe como as horas viram
 * relatórios e confere a prévia antes de gerar — os rascunhos entram na
 * mesma esteira da geração automática (revisão, aprovação, envio). */
export function AutoCustomModal({ onClose }: { onClose: () => void }) {
  const reviewers = useAutoGenerationStore((s) => s.reviewers);
  const previewCustom = useAutoGenerationStore((s) => s.previewCustom);
  const scheduleCustom = useAutoGenerationStore((s) => s.scheduleCustom);
  const currentCompetence = useAutoGenerationStore((s) => s.current);
  // a geração personalizada vale só pro MÊS ATUAL
  const period: PeriodDraft = useMemo(() => {
    const now = new Date();
    return periodForCompetence(
      currentCompetence ?? `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
    );
  }, [currentCompetence]);
  const [blocks, setBlocks] = useState<BlockDraft[]>(() => [newBlock()]);
  const [splitBy, setSplitBy] = useState<CustomSplit>("nenhum");
  const [unit, setUnit] = useState<CustomUnit>("projeto");
  const [title, setTitle] = useState("");
  const [reviewerLogin, setReviewerLogin] = useState("");
  const [clients, setClients] = useState<string[] | null>(null);
  const [employees, setEmployees] = useState<EmployeeOption[] | null>(null);
  const [projectsById, setProjectsById] = useState<Record<string, ProjectOption>>({});
  const [preview, setPreview] = useState<{ key: string; data: CustomPreview } | null>(null);
  const [busy, setBusy] = useState<"" | "preview" | "create">("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  const label = periodLabelOf(period);
  const problems = blocks.map(blockProblem);
  const valid = problems.every((p) => p === null);

  const scope = useMemo(
    () => buildCustomScope({ period, blocks, splitBy, unit, title, reviewerLogin }),
    [period, blocks, splitBy, unit, title, reviewerLogin],
  );
  const scopeKey = JSON.stringify(scope);
  // a prévia só vale pro recorte exato que a gerou
  const freshPreview = preview && preview.key === scopeKey ? preview.data : null;

  useEffect(() => {
    if (!useAutoGenerationStore.getState().reviewers) void useAutoGenerationStore.getState().loadReviewers();
    api<{ employees: EmployeeOption[] }>("/my-hours/employees")
      .then((r) => setEmployees(r.employees))
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  // clientes com horas NO PERÍODO (o mesmo endpoint da busca manual por cliente)
  useEffect(() => {
    let cancelled = false;
    setClients(null);
    api<{ clients: string[] }>(`/management/clients-with-hours?month_label=${encodeURIComponent(label)}`)
      .then((r) => {
        if (!cancelled) setClients(r.clients);
      })
      .catch((e) => {
        if (!cancelled) {
          setClients([]);
          setLoadError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [label]);

  const modalRef = useModal({ onClose, busy: Boolean(busy) });

  const employeeName = (id: string) => employees?.find((e) => e.employee_id === id)?.name ?? id;
  const projectName = (id: string) => (projectsById[id] ? projectLabel(projectsById[id]) : id);
  const updateBlock = (key: string, patch: Partial<BlockDraft>) =>
    setBlocks((all) => all.map((b) => (b.key === key ? { ...b, ...patch } : b)));
  const rememberProjects = (found: ProjectOption[]) =>
    setProjectsById((prev) => {
      const next = { ...prev };
      for (const p of found) next[p.id] = p;
      return next;
    });

  const runPreview = async () => {
    setBusy("preview");
    setError("");
    try {
      const data = await previewCustom(scope);
      setPreview({ key: scopeKey, data });
    } catch (e) {
      setPreview(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  };

  const create = async () => {
    setBusy("create");
    setError("");
    try {
      await scheduleCustom(scope);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy("");
    }
  };

  return createPortal(
    <div className="modal-backdrop" onClick={() => !busy && onClose()}>
      <div
        ref={modalRef}
        tabIndex={-1}
        className="modal-card auto-custom-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auto-custom-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="auto-custom-title">Nova geração personalizada</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar" disabled={Boolean(busy)}>
            <X size={18} strokeWidth={2} />
          </button>
        </div>
        <div className="modal-body auto-custom-body">
          <p className="muted">
            Monte o recorte com cliente, projeto, pacote e colaborador — dá pra misturar. Nada é criado agora: o pedido
            fica agendado e os relatórios nascem <strong>junto com os automáticos</strong>, quando o mês fecha. Aí
            seguem o mesmo caminho: revisão, aprovação e envio.
          </p>

          <section className="auto-custom-section" aria-labelledby="auto-custom-period">
            <h3 id="auto-custom-period">Período</h3>
            <p className="auto-custom-fixed-period">
              {label} <span className="auto-badge">mês atual</span>
            </p>
            <p className="auto-field-hint">
              A geração personalizada vale só para o mês atual. As horas que aparecem na prévia são as de agora; o
              relatório final usa as horas do mês fechado.
            </p>
          </section>

          <section className="auto-custom-section" aria-labelledby="auto-custom-blocks">
            <h3 id="auto-custom-blocks">Recortes</h3>
            <p className="auto-field-hint">
              Um recorte é um conjunto de filtros: só entram as horas que passam em <strong>todos</strong> os filtros
              preenchidos (“o Lucca nos projetos da Mercedes”). Filtro em branco não restringe. Para juntar coisas
              diferentes, adicione outro recorte — as horas dos recortes se somam, sem contar a mesma hora duas vezes.
            </p>
            {loadError && (
              <p className="error-text" role="alert">
                {loadError}
              </p>
            )}
            <div className="auto-custom-blocks">
              {blocks.map((block, index) => (
                <BlockEditor
                  key={block.key}
                  index={index}
                  block={block}
                  problem={problems[index]}
                  label={label}
                  clients={clients}
                  employees={employees}
                  removable={blocks.length > 1}
                  summary={describeBlock(block, employeeName, projectName)}
                  onChange={(patch) => updateBlock(block.key, patch)}
                  onRemove={() => setBlocks((all) => all.filter((b) => b.key !== block.key))}
                  onProjects={rememberProjects}
                />
              ))}
            </div>
            <button
              type="button"
              className="btn-secondary auto-custom-add"
              onClick={() => setBlocks((all) => [...all, newBlock()])}
            >
              <Plus size={14} strokeWidth={2} /> Adicionar recorte
            </button>
          </section>

          <section className="auto-custom-section" aria-labelledby="auto-custom-how">
            <h3 id="auto-custom-how">Como as horas viram relatórios</h3>
            <h4 className="auto-custom-subtitle">1. Como separar a lista</h4>
            <RadioCardGroup
              name="auto-custom-split"
              value={splitBy}
              onChange={(v) => setSplitBy(v as CustomSplit)}
              options={SPLIT_OPTIONS}
              ariaLabel="Como separar a lista"
              layout="horizontal"
              density="compact"
            />
            <h4 className="auto-custom-subtitle">2. O que é um relatório dentro de cada item</h4>
            <RadioCardGroup
              name="auto-custom-unit"
              value={unit}
              onChange={(v) => setUnit(v as CustomUnit)}
              options={UNIT_OPTIONS}
              ariaLabel="O que é um relatório dentro de cada item"
              layout="horizontal"
              density="compact"
            />
            <p className="auto-custom-result" role="status">
              {howItWorks(splitBy, unit)}
            </p>
            <div className="auto-custom-extra">
              <label className="auto-custom-field">
                Título (opcional)
                <input
                  type="text"
                  value={title}
                  maxLength={200}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Sem título, vale o que o recorte tem em comum"
                />
              </label>
              <div className="auto-custom-field">
                <span>Revisor (opcional)</span>
                <ReviewerPicker
                  value={reviewerLogin}
                  reviewers={reviewers}
                  emptyLabel="Sem revisor"
                  loadingLabel="Carregando..."
                  onChange={(login) => setReviewerLogin(login ?? "")}
                />
              </div>
            </div>
          </section>

          {freshPreview && <PreviewTable data={freshPreview} />}
          {preview && !freshPreview && (
            <p className="muted" role="status">
              Você mudou o recorte — calcule a prévia de novo se quiser conferir.
            </p>
          )}
          {error && (
            <p className="error-text" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={Boolean(busy)}>
            Cancelar
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void runPreview()}
            disabled={!valid || Boolean(busy)}
          >
            {busy === "preview" ? "Calculando..." : "Calcular prévia"}
          </button>
          <button
            type="button"
            className="primary"
            onClick={() => void create()}
            disabled={!valid || Boolean(busy)}
            title="Agenda o pedido: os relatórios são gerados junto com os automáticos"
          >
            <CalendarClock size={14} strokeWidth={2} /> {busy === "create" ? "Agendando..." : "Agendar geração"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Um recorte. A lista de projetos vem dos clientes marcados (endpoint da
 * busca manual, com horas no período); pacotes só aparecem com UM projeto. */
function BlockEditor({
  index,
  block,
  problem,
  label,
  clients,
  employees,
  removable,
  summary,
  onChange,
  onRemove,
  onProjects,
}: {
  index: number;
  block: BlockDraft;
  problem: string | null;
  label: string;
  clients: string[] | null;
  employees: EmployeeOption[] | null;
  removable: boolean;
  summary: string;
  onChange: (patch: Partial<BlockDraft>) => void;
  onRemove: () => void;
  onProjects: (projects: ProjectOption[]) => void;
}) {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [packages, setPackages] = useState<string[]>([]);
  const onProjectsRef = useRef(onProjects);
  onProjectsRef.current = onProjects;
  const clientsKey = block.clients.join("\u0000");
  const singleProject = block.projectIds.length === 1 ? block.projectIds[0] : null;

  useEffect(() => {
    if (!block.clients.length) {
      setProjects([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      block.clients.map((client) =>
        api<{ projects: ProjectOption[] }>(
          `/management/client-projects?client=${encodeURIComponent(client)}&month_label=${encodeURIComponent(label)}`,
        ).then((r) => r.projects),
      ),
    )
      .then((lists) => {
        if (cancelled) return;
        const merged = lists.flat();
        setProjects(merged);
        onProjectsRef.current(merged);
        // projeto marcado que não existe mais nessa lista (troca de cliente ou de período)
        const known = new Set(merged.map((p) => p.id));
        const kept = block.projectIds.filter((id) => known.has(id));
        if (kept.length !== block.projectIds.length) onChange({ projectIds: kept, packages: [] });
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientsKey, label]);

  useEffect(() => {
    if (!singleProject) {
      setPackages([]);
      return;
    }
    let cancelled = false;
    api<{ packages: string[] }>(`/management/projects/${encodeURIComponent(singleProject)}/all-packages`)
      .then((r) => {
        if (!cancelled) setPackages(r.packages);
      })
      .catch(() => {
        if (!cancelled) setPackages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [singleProject]);

  const employeeIds = (employees ?? []).map((e) => e.employee_id);
  const employeeLabel = (id: string) => employees?.find((e) => e.employee_id === id)?.name ?? id;
  const projectById = new Map(projects.map((p) => [p.id, p]));

  return (
    <div className={`auto-custom-block ${problem ? "auto-custom-block-invalid" : ""}`}>
      <div className="auto-custom-block-head">
        <strong>Recorte {index + 1}</strong>
        <span className="muted auto-custom-block-summary">
          {summary ? `Pega: ${summary}` : "Escolha pelo menos um filtro"}
        </span>
        {removable && (
          <button
            type="button"
            className="auto-link-button"
            onClick={onRemove}
            aria-label={`Remover recorte ${index + 1}`}
          >
            <Trash2 size={14} strokeWidth={2} /> Remover
          </button>
        )}
      </div>
      <div className="auto-custom-block-grid">
        <MultiSelectDropdown
          label="Cliente"
          options={clients ?? []}
          selected={block.clients}
          onChange={(v) => onChange({ clients: v })}
          searchPlaceholder="Buscar cliente"
          emptyLabel={clients ? "Qualquer cliente" : "Carregando..."}
          hint={HINTS.client}
        />
        <MultiSelectDropdown
          label="Projeto"
          options={projects.map((p) => p.id)}
          selected={block.projectIds}
          labelFor={(id) => (projectById.get(id) ? projectLabel(projectById.get(id)!) : id)}
          onChange={(v) => onChange({ projectIds: v, packages: v.length === 1 ? block.packages : [] })}
          searchPlaceholder="Buscar projeto"
          emptyLabel={block.clients.length ? "Todos do cliente" : "Escolha um cliente antes"}
          hint={HINTS.project}
        />
        <MultiSelectDropdown
          label="Pacote de trabalho"
          options={packages}
          selected={block.packages}
          onChange={(v) => onChange({ packages: v })}
          searchPlaceholder="Buscar pacote"
          emptyLabel={singleProject ? "Todos do projeto" : "Marque um só projeto"}
          hint={HINTS.package}
        />
        <MultiSelectDropdown
          label="Colaborador"
          options={employeeIds}
          selected={block.employeeIds}
          labelFor={employeeLabel}
          onChange={(v) => onChange({ employeeIds: v })}
          searchPlaceholder="Buscar colaborador"
          emptyLabel={employees ? "Todos os colaboradores" : "Carregando..."}
          hint={HINTS.employee}
        />
      </div>
      {problem && (
        <p className="auto-custom-problem" role="alert">
          <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" /> {problem}
        </p>
      )}
    </div>
  );
}

function PreviewTable({ data }: { data: CustomPreview }) {
  return (
    <section
      className="auto-custom-section auto-custom-preview"
      aria-labelledby="auto-custom-preview-title"
      aria-live="polite"
    >
      <h3 id="auto-custom-preview-title">
        Prévia com as horas de agora · {data.period_label} · {data.reports.length}{" "}
        {data.reports.length === 1 ? "item" : "itens"} · {fmtNum(data.total_hours)} h
      </h3>
      {data.summary && (
        <p className="muted">
          <Users size={13} strokeWidth={2} aria-hidden="true" /> {data.summary}
        </p>
      )}
      <div className="auto-custom-preview-scroll">
        <table className="auto-custom-table">
          <thead>
            <tr>
              <th>Item da lista</th>
              <th>Cliente</th>
              <th className="num">Horas</th>
              <th className="num">Relatórios</th>
            </tr>
          </thead>
          <tbody>
            {data.reports.map((r) => (
              <tr key={r.key}>
                <td>
                  {r.title}
                  {r.partial && (
                    <span
                      className="auto-badge auto-badge-warn"
                      title="Não cobre o projeto (ou pacote) inteiro — no Diagnóstico aparece como envio parcial"
                    >
                      recorte parcial
                    </span>
                  )}
                  {r.issues > 0 && (
                    <span
                      className="auto-badge auto-badge-warn"
                      title="Horas sem descrição no Projectile — aparecem como aviso no editor"
                    >
                      {r.issues} sem descrição
                    </span>
                  )}
                </td>
                <td>{r.client}</td>
                <td className="num">{fmtNum(r.hours)}</td>
                <td className="num">{r.packages}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.warnings.length > 0 && (
        <ul className="auto-custom-warnings">
          {data.warnings.map((w) => (
            <li key={w}>
              <AlertTriangle size={13} strokeWidth={2} aria-hidden="true" /> {w}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
