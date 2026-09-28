import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  CalendarClock, ChevronDown, Download, FilePen, Play, RefreshCw, RotateCcw, Search, Settings, SkipForward, SlidersHorizontal,
  Send, Undo2, UserRound, X,
} from "lucide-react";
import { PageHeader } from "./PageHeader";
import { FormatCheckboxes, type ReportFormat } from "./FormatCheckboxes";
import type { AppView } from "../appView";
import { useReportTabsStore } from "../store/useReportTabsStore";
import {
  EDITABLE_STATUSES,
  useAutoGenerationStore,
  type AutoItem,
  type AutoStatus,
  type EffectiveConfig,
  type PreviewProject,
  type ProjectRule,
} from "../store/useAutoGenerationStore";
import { fmtNum } from "../utils/fmt";
import { matchesNumberPattern, numberPatternLabel } from "../utils/autoDraft";
import { ReviewNote } from "./MyReviewsPanel";
import { AutoSendModal, BulkSendModal } from "./AutoSendModal";
import { ReviewerPicker } from "./ReviewerPicker";

const MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];

export function competenceLabel(competence: string | null | undefined): string {
  if (!competence) return "";
  const [year, month] = competence.split("-");
  return `${MONTHS[Number(month) - 1] ?? month}/${year}`;
}

export const STATUS_LABELS: Record<AutoStatus, string> = {
  gerando: "Gerando",
  erro: "Erro",
  em_revisao: "Em revisão",
  revisado: "Aguardando aprovação",
  devolvido: "Devolvido",
  aprovado: "Aprovado",
  enviado: "Enviado",
  pulado: "Pulado",
};

// ordem das etapas na faixa de filtros (o caminho feliz primeiro)
const STAGES: AutoStatus[] = ["em_revisao", "revisado", "devolvido", "aprovado", "enviado", "erro", "pulado"];

export function StatusPill({ status }: { status: AutoStatus }) {
  return <span className={`auto-status-pill auto-status-${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}

// aprovados (e já enviados) entram na seleção em massa
const SELECTABLE: AutoStatus[] = ["aprovado", "enviado"];

const MODE_LABELS = { projeto: "Um relatório pro projeto", pacote: "Um relatório por pacote" } as const;

/** Aba "Geração automática" (só gerente): um bloco por projeto da
 * competência, cada um com status, número, ações e a configuração
 * individual do projeto. A revisão/aprovação acontece no editor de sempre. */
export function AutoGenerationPanel({ onNavigate }: { onNavigate: (view: AppView) => void }) {
  const current = useAutoGenerationStore((s) => s.current);
  const previous = useAutoGenerationStore((s) => s.previous);
  const runs = useAutoGenerationStore((s) => s.runs);
  const selected = useAutoGenerationStore((s) => s.selected);
  const view = useAutoGenerationStore((s) => s.view);
  const preview = useAutoGenerationStore((s) => s.preview);
  const loading = useAutoGenerationStore((s) => s.loading);
  const error = useAutoGenerationStore((s) => s.error);
  const init = useAutoGenerationStore((s) => s.init);
  const select = useAutoGenerationStore((s) => s.select);
  const refresh = useAutoGenerationStore((s) => s.refresh);
  const run = useAutoGenerationStore((s) => s.run);
  const [stage, setStage] = useState<AutoStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [openError, setOpenError] = useState("");
  const [picked, setPicked] = useState<Set<string>>(() => new Set());
  const [bulkSend, setBulkSend] = useState<AutoItem[] | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  // outra competência: a seleção não vale mais
  useEffect(() => setPicked(new Set()), [view?.competence]);

  useEffect(() => {
    void init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const olderRuns = runs.filter((r) => r.competence !== current && r.competence !== previous);
  const running = view?.run?.status === "running";
  const term = search.trim().toLocaleLowerCase("pt-BR");
  const matches = (text: string) => !term || text.toLocaleLowerCase("pt-BR").includes(term);
  const items = useMemo(
    () => (view?.items ?? []).filter((i) => (stage === "all" || i.status === stage) && matches(`${i.project_name} ${i.client ?? ""}`)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [view, stage, term],
  );
  const previewProjects = (preview?.projects ?? []).filter((p) => matches(`${p.name} ${p.client}`));
  // só o que ainda está na lista e continua aprovado/enviado
  const pickedItems = (view?.items ?? []).filter((i) => picked.has(i.id) && SELECTABLE.includes(i.status));
  const selectableVisible = items.filter((i) => SELECTABLE.includes(i.status));
  const togglePick = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const bulkView = async () => {
    setOpenError("");
    setBulkBusy(true);
    try {
      for (const item of pickedItems) await useAutoGenerationStore.getState().openInEditor(item.id);
      onNavigate("report");
    } catch (e) {
      setOpenError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const bulkReopen = async () => {
    const reopenable = pickedItems.filter((i) => i.status === "aprovado");
    if (!reopenable.length) return;
    const skipped = pickedItems.length - reopenable.length;
    const note = skipped ? `\n\n${skipped} já enviado${skipped === 1 ? "" : "s"} não ${skipped === 1 ? "reabre" : "reabrem"}.` : "";
    if (!window.confirm(`Reabrir ${reopenable.length} relatório${reopenable.length === 1 ? "" : "s"} pra revisão? A aprovação é desfeita (o que foi pro histórico continua lá).${note}`)) return;
    setBulkBusy(true);
    for (const item of reopenable) await useAutoGenerationStore.getState().action(item, "reopen");
    setPicked(new Set());
    setBulkBusy(false);
  };

  const openInEditor = async (item: AutoItem) => {
    setOpenError("");
    try {
      await useAutoGenerationStore.getState().openInEditor(item.id);
      onNavigate("report");
    } catch (e) {
      setOpenError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="auto-panel page-container">
      <PageHeader
        title="Geração automática"
        description="Um rascunho por projeto com horas no mês, com o que foi ajustado no mês anterior já aplicado. Revise no editor, digite o número e aprove."
        icon={<CalendarClock size={20} strokeWidth={1.8} />}
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={() => setShowSettings(true)}>
              <Settings size={14} strokeWidth={2} /> Padrão geral
            </button>
            <button type="button" className="btn-secondary" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} /> Atualizar
            </button>
          </>
        }
      />

      <div className="auto-competences" role="tablist" aria-label="Competência">
        {previous && (
          <button type="button" role="tab" aria-selected={selected === previous}
            className={selected === previous ? "active" : ""} onClick={() => void select(previous)}>
            <span className="auto-competence-kind">Mês passado</span>
            {competenceLabel(previous)}
          </button>
        )}
        {current && (
          <button type="button" role="tab" aria-selected={selected === current}
            className={selected === current ? "active" : ""} onClick={() => void select(current)}>
            <span className="auto-competence-kind">Mês atual</span>
            {competenceLabel(current)}
          </button>
        )}
        {olderRuns.length > 0 && (
          <select
            aria-label="Competências anteriores"
            value={olderRuns.some((r) => r.competence === selected) ? selected ?? "" : ""}
            onChange={(e) => e.target.value && void select(e.target.value)}
          >
            <option value="">Anteriores…</option>
            {olderRuns.map((r) => (
              <option key={r.competence} value={r.competence}>{competenceLabel(r.competence)}</option>
            ))}
          </select>
        )}
      </div>

      {error && <div className="card"><p className="error-text">{error}</p></div>}
      {openError && <div className="card"><p className="error-text">{openError}</p></div>}
      {loading && !view && <div className="card"><p className="muted">Carregando...</p></div>}

      {view && !view.run && (
        <div className="card auto-run-card">
          <div>
            <h3>{view.competence === current ? `${view.month_label} ainda está em andamento` : `Nenhum rascunho de ${view.month_label} ainda`}</h3>
            <p className="muted">
              {view.competence === current
                ? "Abaixo, os projetos com horas até agora e o que vai acontecer com cada um. Nada é gravado até você gerar — mas já dá pra configurar cada projeto."
                : "Gere os rascunhos de todos os projetos com horas no mês. Projetos fechados no Diagnóstico e os desligados na configuração ficam de fora."}
            </p>
          </div>
          <button type="button" className="primary" onClick={() => void run()}>
            <Play size={14} strokeWidth={2} /> Gerar rascunhos de {view.month_label}
          </button>
        </div>
      )}

      {view?.run && (running || view.run.status === "failed") && (
        <div className="card auto-run-card" role="status" aria-live="polite">
          {running ? (
            <p><RefreshCw size={14} strokeWidth={2} className="spin" /> Gerando os rascunhos de {view.month_label}… a lista atualiza sozinha.</p>
          ) : (
            <p className="error-text">A última geração falhou: {view.run.error}. Os rascunhos já criados continuam aqui; gere de novo pra completar.</p>
          )}
        </div>
      )}

      {(view?.run || preview) && (
        <div className="auto-toolbar">
          <div className="send-status-search">
            <Search size={14} strokeWidth={2} />
            <input type="text" placeholder="Buscar por projeto ou cliente..." value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          {view?.run && (
            <div className="send-status-tabs auto-stages">
              {/* sem "Todos": nada marcado = lista inteira; clicar de novo na etapa marcada desfaz o filtro */}
              {STAGES.filter((s) => view.counts[s] || stage === s).map((s) => (
                <button key={s} type="button" className={stage === s ? "active" : ""} aria-pressed={stage === s}
                  title={stage === s ? "Clique de novo pra ver todos" : undefined}
                  onClick={() => setStage((current) => (current === s ? "all" : s))}>
                  {STATUS_LABELS[s]} <span className="send-status-tab-count">{view.counts[s] ?? 0}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {view?.run && (
        <div className="auto-cards">
          {items.map((item) => (
            <ProjectCard key={item.id} title={item.project_name} client={item.client ?? ""} familyKey={item.family_key}
              rule={item.rule} effective={item.effective} item={item} onOpen={() => void openInEditor(item)}
              selected={picked.has(item.id)} onToggleSelect={SELECTABLE.includes(item.status) ? () => togglePick(item.id) : undefined} />
          ))}
          {items.length === 0 && <div className="card"><p className="muted">Nenhum projeto nesse filtro.</p></div>}
        </div>
      )}

      {preview && !view?.run && (
        <div className="auto-cards">
          {previewProjects.map((p) => (
            <ProjectCard key={p.project_id} title={p.name} client={p.client} familyKey={p.family_key}
              rule={p.rule} effective={p.effective} preview={p} />
          ))}
          {previewProjects.length === 0 && <div className="card"><p className="muted">Nenhum projeto com horas ainda.</p></div>}
        </div>
      )}

      {view?.run && view.new_projects.length > 0 && !running && (
        <div className="card auto-new-projects">
          <div>
            <h3>{view.new_projects.length} projeto{view.new_projects.length === 1 ? "" : "s"} com horas depois da geração</h3>
            <p className="muted">{view.new_projects.map((p) => `${p.name} (${fmtNum(p.hours)} h)`).join(" · ")}</p>
          </div>
          <button type="button" className="btn-secondary" onClick={() => void run(view.new_projects.map((p) => p.project_id))}>
            <Play size={14} strokeWidth={2} /> Gerar rascunhos destes
          </button>
        </div>
      )}

      {pickedItems.length > 0 && (
        <div className="auto-bulk-bar card" role="region" aria-label="Ações nos selecionados">
          <span className="auto-bulk-count">
            {pickedItems.length} selecionado{pickedItems.length === 1 ? "" : "s"}
          </span>
          {pickedItems.length < selectableVisible.length && (
            <button type="button" className="auto-link-button" onClick={() => setPicked(new Set(selectableVisible.map((i) => i.id)))}>
              Selecionar todos os {selectableVisible.length}
            </button>
          )}
          <button type="button" className="auto-link-button" onClick={() => setPicked(new Set())}>Limpar</button>
          <div className="auto-bulk-actions">
            <button type="button" className="primary" onClick={() => setBulkSend(pickedItems)} disabled={bulkBusy}>
              <Send size={14} strokeWidth={2} /> Enviar ao cliente
            </button>
            <button type="button" className="btn-secondary" onClick={() => void bulkView()} disabled={bulkBusy}>
              <FilePen size={14} strokeWidth={2} /> Ver
            </button>
            <a className="btn-secondary" href={`/auto-generation/files?${pickedItems.map((i) => `ids=${encodeURIComponent(i.id)}`).join("&")}`}>
              <Download size={14} strokeWidth={2} /> Baixar
            </a>
            <button type="button" className="btn-secondary" onClick={() => void bulkReopen()}
              disabled={bulkBusy || !pickedItems.some((i) => i.status === "aprovado")}
              title={pickedItems.some((i) => i.status === "aprovado") ? undefined : "Relatório já enviado não reabre"}>
              <RotateCcw size={14} strokeWidth={2} /> Reabrir
            </button>
          </div>
        </div>
      )}
      {bulkSend && <BulkSendModal items={bulkSend} onClose={() => { setBulkSend(null); setPicked(new Set()); }} />}

      {showSettings && <AutoSettingsModal onClose={() => setShowSettings(false)} />}
    </div>
  );
}

function fmtDate(value: string): string {
  // o backend grava UTC sem fuso ("2026-09-28T14:05:00")
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

const PLANNED_LABELS = { sera_gerado: "Será gerado", fechado: "Fechado no Diagnóstico", desativado: "Desligado neste projeto" } as const;

/** Um projeto: o rascunho (quando já gerado) ou a prévia do mês em
 * andamento, e a configuração individual. */
function ProjectCard({ title, client, familyKey, rule, effective, item, preview, onOpen, selected = false, onToggleSelect }: {
  selected?: boolean;
  // presente = bloco entra na seleção em massa (aprovado/enviado)
  onToggleSelect?: () => void;
  title: string;
  client: string;
  familyKey: string;
  rule: ProjectRule;
  effective: EffectiveConfig;
  item?: AutoItem;
  preview?: PreviewProject;
  onOpen?: () => void;
}) {
  const busy = useAutoGenerationStore((s) => (item ? Boolean(s.busy[item.id]) : false));
  const action = useAutoGenerationStore((s) => s.action);
  const [showConfig, setShowConfig] = useState(false);
  const [showReturn, setShowReturn] = useState(false);
  const [showSend, setShowSend] = useState(false);
  const sent = item?.status === "enviado";
  const canReturn = Boolean(item && item.status === "revisado" && item.reviewer_login);
  const status = item?.status;
  const editable = status ? EDITABLE_STATUSES.includes(status) : false;
  const badges = item?.badges ?? {};
  const hasRule = Object.keys(rule ?? {}).length > 0;
  // o bloco mostra como o rascunho FOI gerado; a configuração pode ter mudado depois
  const draftMode = item ? badges.mode ?? effective.mode : effective.mode;
  const modeOutdated = Boolean(item && badges.mode && badges.mode !== effective.mode);

  const confirmRegenerate = () => {
    if (!item) return;
    if (editable && !window.confirm(`Gerar de novo "${title}" a partir do Projectile? As edições feitas no rascunho serão descartadas.`)) return;
    void action(item, "regenerate");
  };

  return (
    <article
      className={`card auto-card ${busy ? "auto-card-busy" : ""} ${status ? `auto-card-${status}` : ""} ${onToggleSelect ? "auto-card-selectable" : ""} ${selected ? "auto-card-selected" : ""}`}
      aria-label={title}
    >
      {/* bloco horizontal: identificação | dados | status e ações */}
      <div className="auto-card-row">
        <div className="auto-card-main">
          <div className="auto-card-title">
            <h3 title={title}>{title}</h3>
            <span className="muted">{client}</span>
          </div>
          <div className="auto-badges">
            {badges.memory_applied && <span className="auto-badge" title="Nomes de grupo, performance, descrições e assinantes do último relatório aprovado deste projeto">memória do mês anterior</span>}
            {badges.hours_changed && <span className="auto-badge auto-badge-warn" title="As horas do Projectile mudaram depois que o rascunho foi gerado">horas mudaram</span>}
            {(badges.missing_hours ?? 0) > 0 && (
              <span className="auto-badge auto-badge-warn" title="Lançamentos sem descrição no Projectile não entram no relatório — aparecem como aviso no editor, onde dá pra adicionar como atividade">
                {fmtNum(badges.missing_hours ?? 0)} h sem descrição
              </span>
            )}
            {badges.skip_reason && <span className="auto-badge">{badges.skip_reason}</span>}
            {hasRule && <span className="auto-badge" title="Este projeto tem configuração própria">configuração própria</span>}
          </div>
          {item?.status === "erro" && item.error && <p className="error-text auto-error">{item.error}</p>}
        </div>

        <div className="auto-card-data">
          <dl className="auto-card-facts">
            <div>
              <dt>Horas</dt>
              <dd>
                {item?.source_hours != null ? `${fmtNum(item.source_hours)} h` : preview ? `${fmtNum(preview.hours)} h até agora` : "—"}
                {badges.hours_changed && item?.hours_now != null && <span className="muted"> · {fmtNum(item.hours_now)} h agora</span>}
              </dd>
            </div>
            <div>
              <dt>Relatório</dt>
              <dd>{MODE_LABELS[draftMode] ?? draftMode}{(badges.packages ?? 0) > 1 ? ` · ${badges.packages} pacotes` : ""}</dd>
            </div>
          </dl>
          {modeOutdated && (
            <p className="auto-mode-hint">
              Gerado como “{MODE_LABELS[draftMode].toLowerCase()}”; a configuração agora é “{MODE_LABELS[effective.mode].toLowerCase()}”.
              {editable && <button type="button" className="auto-link-button" onClick={confirmRegenerate} disabled={busy}>Regenerar pra aplicar</button>}
            </p>
          )}
          {item && (badges.package_ids?.length ?? 0) > 0 && <NumbersField item={item} editable={editable} pattern={effective.number_pattern} model={effective.number_model} />}
          {item && status !== "erro" && status !== "pulado" && <ReviewerField item={item} editable={editable} />}
          {item?.last_comment?.comment && <ReviewNote comment={item.last_comment} />}
          {sent && item?.last_sent && (
            <p className="auto-sent-info">
              <Send size={14} strokeWidth={2} aria-hidden="true" />
              <span>
                Enviado {fmtDate(item.last_sent.created_at)}{item.last_sent.actor_name ? ` por ${item.last_sent.actor_name}` : ""} pra{" "}
                {[...item.last_sent.to, ...item.last_sent.cc].join(", ")}
              </span>
            </p>
          )}
          {preview && preview.planned === "sera_gerado" && (
            <PlannedReviewerField familyKey={familyKey} rule={rule} remembered={preview.remembered_reviewer} />
          )}
        </div>

        <div className="auto-card-side">
          {status ? <StatusPill status={status} /> : preview && (
            <span className={`auto-status-pill ${preview.planned === "sera_gerado" ? "auto-status-em_revisao" : ""}`}>{PLANNED_LABELS[preview.planned]}</span>
          )}
          <div className="auto-card-actions">
            {canReturn && (
              <button type="button" className="btn-secondary" aria-expanded={showReturn} onClick={() => setShowReturn((v) => !v)} disabled={busy}>
                <Undo2 size={14} strokeWidth={2} /> Devolver
              </button>
            )}
            {item && (item.status === "aprovado" || sent) && (
              <button type="button" className={sent ? "btn-secondary" : "primary"} onClick={() => setShowSend(true)} disabled={busy}>
                <Send size={14} strokeWidth={2} /> {sent ? "Enviar de novo" : "Enviar ao cliente"}
              </button>
            )}
            {item && (editable || item.status === "aprovado" || sent) && (
              <button type="button" className={editable ? "primary" : "btn-secondary"} onClick={onOpen} disabled={busy}>
                <FilePen size={14} strokeWidth={2} /> {editable ? "Abrir no editor" : "Ver"}
              </button>
            )}
            {item && (item.status === "aprovado" || sent) && (
              <>
                <a className="btn-secondary" href={`/auto-generation/reports/${item.id}/files`}>
                  <Download size={14} strokeWidth={2} /> Arquivos
                </a>
              </>
            )}
            {item?.status === "aprovado" && (
              <button type="button" className="btn-secondary" disabled={busy}
                onClick={() => window.confirm("Reabrir pra revisão? A aprovação é desfeita (o que foi pro histórico continua lá).") && void action(item, "reopen")}>
                <RotateCcw size={14} strokeWidth={2} /> Reabrir
              </button>
            )}
            {item && (editable || item.status === "erro" || item.status === "pulado") && (
              <button type="button" className="btn-secondary" onClick={confirmRegenerate} disabled={busy}
                title={item.status === "pulado" ? "Gerar o rascunho deste projeto" : "Gerar de novo a partir do Projectile, com a configuração atual"}>
                <RefreshCw size={14} strokeWidth={2} /> {item.status === "pulado" ? "Gerar" : "Regenerar"}
              </button>
            )}
            {item && (editable || item.status === "erro") && (
              <button type="button" className="btn-secondary" disabled={busy}
                onClick={() => window.confirm(`Pular "${title}" neste mês?`) && void action(item, "skip")}>
                <SkipForward size={14} strokeWidth={2} /> Pular
              </button>
            )}
            {!onToggleSelect && (
              <button type="button" className="btn-secondary auto-config-toggle" aria-expanded={showConfig} onClick={() => setShowConfig((v) => !v)}>
                <SlidersHorizontal size={14} strokeWidth={2} /> Configuração <ChevronDown size={14} className={showConfig ? "flipped" : ""} />
              </button>
            )}
          </div>
          {onToggleSelect && (
            <label className="auto-card-select" title="Selecionar pra ações em massa">
              <input type="checkbox" checked={selected} onChange={onToggleSelect} aria-label={`Selecionar ${title}`} />
            </label>
          )}
        </div>
      </div>

      {showReturn && canReturn && item && (
        <ReturnForm reviewerName={item.reviewer_name ?? ""} onCancel={() => setShowReturn(false)}
          onSubmit={async (comment) => {
            await useAutoGenerationStore.getState().returnToReviewer(item.id, comment);
            setShowReturn(false);
          }} />
      )}
      {showSend && item && <AutoSendModal item={item} onClose={() => setShowSend(false)} />}
      {showConfig && !onToggleSelect && <ProjectConfig familyKey={familyKey} rule={rule} effective={effective} item={item} onRegenerate={item && editable ? confirmRegenerate : undefined} />}
    </article>
  );
}

/** Quem revisa este relatório. A lista vem do Projectile (engenharia com
 * login); o backend confere o login e grava o nome de lá. */
function ReviewerField({ item, editable }: { item: AutoItem; editable: boolean }) {
  const reviewers = useAutoGenerationStore((s) => s.reviewers);
  const reviewersError = useAutoGenerationStore((s) => s.reviewersError);
  const busy = useAutoGenerationStore((s) => Boolean(s.busy[item.id]));
  const assign = useAutoGenerationStore((s) => s.assignReviewer);
  const current = item.reviewer_login ?? "";
  const hint =
    !current ? "Sem revisor: você revisa e aprova direto."
      : item.status === "em_revisao" ? `Com ${item.reviewer_name ?? current} pra revisar.`
        : item.status === "revisado" ? `${item.reviewer_name ?? current} mandou pra aprovação.`
          : item.status === "devolvido" ? `Devolvido pra ${item.reviewer_name ?? current}.`
            : null;

  if (!editable) {
    return current ? (
      <p className="auto-reviewer-readonly"><UserRound size={14} strokeWidth={2} aria-hidden="true" /> Revisado por {item.reviewer_name ?? current}</p>
    ) : null;
  }
  return (
    <div className="auto-reviewer">
      <div className="auto-reviewer-field">
        <span className="auto-numbers-label">Revisor</span>
        <ReviewerPicker
          value={current}
          valueName={item.reviewer_name}
          reviewers={reviewers}
          emptyLabel="Sem revisor"
          loadingLabel={reviewersError ? "Lista indisponível" : "Carregando…"}
          disabled={busy}
          onChange={(login) => void assign(item, login)}
          describedBy={`reviewer-hint-${item.id}`}
        />
      </div>
      {hint && <span id={`reviewer-hint-${item.id}`} className="muted auto-reviewer-hint">{hint}</span>}
    </div>
  );
}

/** Mês em andamento (ainda sem rascunho): o revisor vai pra configuração do
 * projeto e o rascunho já nasce atribuído a ele — neste mês e nos próximos. */
function PlannedReviewerField({ familyKey, rule, remembered }: {
  familyKey: string; rule: ProjectRule; remembered: { login: string; name: string } | null;
}) {
  const reviewers = useAutoGenerationStore((s) => s.reviewers);
  const reviewersError = useAutoGenerationStore((s) => s.reviewersError);
  const saveRule = useAutoGenerationStore((s) => s.saveRule);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const current = rule.reviewer_login ?? "";

  const change = async (login: string) => {
    setSaving(true);
    setError("");
    const next: ProjectRule = { ...rule };
    delete next.reviewer_name;
    if (login) next.reviewer_login = login;
    else delete next.reviewer_login;
    try {
      await saveRule(familyKey, next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const hint = current
    ? `O rascunho já nasce com ${rule.reviewer_name || current} — neste mês e nos próximos.`
    : remembered
      ? `Sem escolha, fica com ${remembered.name || remembered.login} (revisou o último aprovado).`
      : "Sem revisor: você revisa e aprova direto.";

  return (
    <div className="auto-reviewer">
      <div className="auto-reviewer-field">
        <span className="auto-numbers-label">Revisor</span>
        <ReviewerPicker
          value={current}
          valueName={rule.reviewer_name}
          reviewers={reviewers}
          emptyLabel={remembered ? `Padrão (${remembered.name || remembered.login})` : "Sem revisor"}
          loadingLabel={reviewersError ? "Lista indisponível" : "Carregando…"}
          disabled={saving}
          onChange={(login) => void change(login ?? "")}
        />
      </div>
      <span className="muted auto-reviewer-hint">{saving ? "Salvando…" : hint}</span>
      {error && <span className="error-text auto-reviewer-hint" role="alert">{error}</span>}
    </div>
  );
}

/** Devolver ao revisor: o comentário é obrigatório — é o que ele vai ver. */
function ReturnForm({ reviewerName, onSubmit, onCancel }: {
  reviewerName: string; onSubmit: (comment: string) => Promise<void>; onCancel: () => void;
}) {
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    if (!comment.trim()) {
      setError("Escreva o que precisa mudar.");
      return;
    }
    setSending(true);
    setError("");
    try {
      await onSubmit(comment.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSending(false);
    }
  };
  return (
    <div className="auto-return">
      <label className="auto-return-field">
        <span>O que {reviewerName || "o revisor"} precisa mudar?</span>
        <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} maxLength={2000}
          placeholder="Ex.: separe a reunião de alinhamento em outro grupo." autoFocus />
      </label>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="auto-config-actions">
        <button type="button" className="btn-secondary" onClick={onCancel} disabled={sending}>Cancelar</button>
        <button type="button" className="primary" onClick={() => void submit()} disabled={sending}>
          <Undo2 size={14} strokeWidth={2} /> {sending ? "Devolvendo…" : "Devolver ao revisor"}
        </button>
      </div>
    </div>
  );
}

function NumbersField({ item, editable, pattern, model }: {
  item: AutoItem; editable: boolean; pattern?: string; model?: string | null;
}) {
  const setNumber = useAutoGenerationStore((s) => s.setNumber);
  const busy = useAutoGenerationStore((s) => Boolean(s.busy[item.id]));
  const open = useReportTabsStore((s) => s.tabs.some((t) => t.auto?.reportId === item.id));
  const ids = item.badges.package_ids ?? [];
  const names = item.badges.package_names ?? [];
  const numbers = item.badges.numbers ?? [];
  const suggested = item.badges.suggested ?? [];
  const canType = editable && !open;
  return (
    <div className="auto-numbers">
      <span className="auto-numbers-label">{ids.length > 1 ? "Números dos relatórios" : "Número do relatório"}</span>
      {ids.map((id, i) => (
        <NumberInput key={id} label={ids.length > 1 ? names[i] : undefined} value={numbers[i] ?? ""} suggested={suggested[i] ?? ""}
          pattern={pattern} model={model} disabled={!canType || busy} onCommit={(code) => void setNumber(item, id, code)} />
      ))}
      {editable && open && <span className="muted auto-numbers-hint">Aberto no editor — digite o número lá.</span>}
    </div>
  );
}

function NumberInput({ label, value, suggested, pattern, model, disabled, onCommit }: {
  label?: string; value: string; suggested: string; pattern?: string; model?: string | null; disabled: boolean;
  onCommit: (code: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const invalid = draft.trim() !== "" && !matchesNumberPattern(draft.trim(), pattern);
  const commit = () => {
    if (draft.trim() !== value) onCommit(draft.trim());
  };
  return (
    <label className={`auto-number ${invalid ? "auto-number-invalid" : ""}`}>
      {label && <span className="auto-number-package" title={label}>{label}</span>}
      <span className="auto-number-field">
        <input
          className="auto-number-input"
          type="text"
          value={draft}
          placeholder={suggested ? `${suggested} (mês passado)` : "SE.XX.XXX"}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          disabled={disabled}
          aria-invalid={invalid}
          aria-label={label ? `Número do relatório de ${label}` : "Número do relatório"}
        />
        {invalid && <span className="auto-number-error">Formato esperado: {numberPatternLabel(model)}</span>}
      </span>
    </label>
  );
}


/** Configuração individual do projeto — só o que difere do padrão geral
 * (campo vazio = usa o padrão). Guardada pela família: vale também nos
 * próximos meses do mesmo trabalho ("… Estribo 08.2026" → "… 09.2026"). */
function ProjectConfig({ familyKey, rule, effective, item, onRegenerate }: {
  familyKey: string; rule: ProjectRule; effective: EffectiveConfig; item?: AutoItem; onRegenerate?: () => void;
}) {
  const saveRule = useAutoGenerationStore((s) => s.saveRule);
  const [form, setForm] = useState<ProjectRule>(rule ?? {});
  const [status, setStatus] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => setForm(rule ?? {}), [rule]);

  const set = <K extends keyof ProjectRule>(key: K, value: ProjectRule[K] | undefined) =>
    setForm((f) => {
      const next = { ...f };
      if (value === undefined || value === "") delete next[key];
      else next[key] = value;
      return next;
    });
  // o que vale sem a regra deste projeto (pra mostrar o "Padrão: …")
  const inherited = (key: keyof ProjectRule) => (rule && key in rule ? undefined : effective[key]);
  const placeholder = (key: "signer1_name" | "signer1_company" | "signer2_name" | "signer2_company") => {
    const value = inherited(key) as string | undefined;
    return value ? `Padrão: ${value}` : key.endsWith("name") ? "Padrão: último relatório aprovado" : "Padrão";
  };
  const formatsValue = form.formats ? form.formats.slice().sort().join("+") : "";

  const save = async () => {
    setStatus("Salvando...");
    try {
      await saveRule(familyKey, form);
      setStatus("Salvo. Vale pros próximos rascunhos deste projeto, inclusive nos próximos meses.");
      setSaved(true);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="auto-config">
      <div className="auto-config-grid">
        <label className="include-performance-checkbox auto-config-enabled">
          <input type="checkbox" checked={form.enabled !== false} onChange={(e) => set("enabled", e.target.checked ? undefined : false)} />
          <span>Gerar relatório deste projeto</span>
        </label>
        <label>Relatório
          <select value={form.mode ?? ""} onChange={(e) => set("mode", (e.target.value || undefined) as ProjectRule["mode"])}>
            <option value="">Padrão ({MODE_LABELS[(inherited("mode") as "projeto" | "pacote") ?? "projeto"] ?? "—"})</option>
            <option value="projeto">{MODE_LABELS.projeto}</option>
            <option value="pacote">{MODE_LABELS.pacote}</option>
          </select>
        </label>
        <label>Arquivos
          <select value={formatsValue}
            onChange={(e) => set("formats", e.target.value ? (e.target.value.split("+") as Array<"xlsx" | "pdf">) : undefined)}>
            <option value="">Padrão ({((inherited("formats") as string[] | undefined) ?? ["xlsx"]).map((f) => f.toUpperCase()).join(" + ")})</option>
            <option value="xlsx">XLSX</option>
            <option value="pdf">PDF</option>
            <option value="pdf+xlsx">XLSX + PDF</option>
          </select>
        </label>
        <label>Assinante Schwaben
          <input type="text" value={form.signer1_name ?? ""} placeholder={placeholder("signer1_name")} onChange={(e) => set("signer1_name", e.target.value)} />
        </label>
        <label>Empresa
          <input type="text" value={form.signer1_company ?? ""} placeholder={placeholder("signer1_company")} onChange={(e) => set("signer1_company", e.target.value)} />
        </label>
        <label>Assinante do cliente
          <input type="text" value={form.signer2_name ?? ""} placeholder={placeholder("signer2_name")} onChange={(e) => set("signer2_name", e.target.value)} />
        </label>
        <label>Empresa do cliente
          <input type="text" value={form.signer2_company ?? ""} placeholder={placeholder("signer2_company")} onChange={(e) => set("signer2_company", e.target.value)} />
        </label>
      </div>
      <div className="auto-config-actions">
        {status && <span className="muted" role="status">{status}</span>}
        {saved && onRegenerate && item && (
          <button type="button" className="btn-secondary" onClick={onRegenerate}>
            <RefreshCw size={14} strokeWidth={2} /> Regenerar este rascunho com a configuração nova
          </button>
        )}
        <button type="button" className="btn-secondary" onClick={() => setForm({})} disabled={!Object.keys(form).length}>
          Voltar ao padrão
        </button>
        <button type="button" className="primary" onClick={() => void save()}>Salvar configuração</button>
      </div>
    </div>
  );
}

/** Padrão geral — o que vale pra todo projeto sem configuração própria. */
function AutoSettingsModal({ onClose }: { onClose: () => void }) {
  const config = useAutoGenerationStore((s) => s.config);
  const loadConfig = useAutoGenerationStore((s) => s.loadConfig);
  const saveConfig = useAutoGenerationStore((s) => s.saveConfig);
  const refresh = useAutoGenerationStore((s) => s.refresh);
  const [form, setForm] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    void loadConfig().catch((e) => setStatus(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (config && !form) setForm({ ...config.effective });
  }, [config, form]);

  const field = (key: string) => (form?.[key] as string | undefined) ?? "";
  const setField = (key: string, value: unknown) => setForm((f) => ({ ...(f ?? {}), [key]: value }));
  const formats = (form?.formats as string[] | undefined) ?? ["xlsx"];

  const save = async () => {
    setStatus("Salvando...");
    try {
      await saveConfig(form ?? {});
      await refresh();
      setStatus("Padrão salvo. Vale pros próximos rascunhos de todo projeto sem configuração própria.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  };

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card auto-settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Padrão geral da geração automática</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar"><X size={18} strokeWidth={2} /></button>
        </div>
        <div className="modal-body">
          {!form && <p className="muted">Carregando...</p>}
          {form && (
            <section className="auto-settings-section">
              <p className="muted">Vale pra todo projeto que não tiver configuração própria (botão “Configuração” em cada projeto).</p>
              <div className="auto-settings-grid">
                <label>Relatório
                  <select value={field("mode")} onChange={(e) => setField("mode", e.target.value)}>
                    <option value="projeto">{MODE_LABELS.projeto}</option>
                    <option value="pacote">{MODE_LABELS.pacote}</option>
                  </select>
                </label>
                <label>Local da data
                  <input type="text" value={field("location")} onChange={(e) => setField("location", e.target.value)} />
                </label>
                <label>Assinante Schwaben
                  <input type="text" value={field("signer1_name")} onChange={(e) => setField("signer1_name", e.target.value)} placeholder="Nome de quem assina" />
                </label>
                <label>Empresa
                  <input type="text" value={field("signer1_company")} onChange={(e) => setField("signer1_company", e.target.value)} />
                </label>
                <label>Assinante do cliente
                  <input type="text" value={field("signer2_name")} onChange={(e) => setField("signer2_name", e.target.value)} placeholder="Nome de quem assina" />
                </label>
                <label>Empresa do cliente
                  <input type="text" value={field("signer2_company")} onChange={(e) => setField("signer2_company", e.target.value)} />
                </label>
                {config?.effective.number_model != null ? (
                  <label>Modelo do número
                    <input type="text" value={field("number_model")} onChange={(e) => setField("number_model", e.target.value)}
                      spellCheck={false} placeholder="SE.##.###" />
                    <span className="auto-field-hint"># = um dígito. “SE.##.###” aceita SE.26.053.</span>
                  </label>
                ) : (
                  <label>Formato do número (avançado)
                    <input type="text" value={field("number_pattern")} onChange={(e) => setField("number_pattern", e.target.value)} spellCheck={false} />
                    <span className="auto-field-hint">Regra escrita à mão (expressão regular).</span>
                  </label>
                )}
                {/* mesmos cartões do rodapé de "Gerar relatório" (Excel/PDF) */}
                <div className="auto-settings-files" role="group" aria-labelledby="auto-settings-files-label">
                  <span id="auto-settings-files-label" className="auto-settings-files-label">Arquivos</span>
                  <div className="auto-settings-files-row">
                    <FormatCheckboxes
                      value={new Set(formats as ReportFormat[])}
                      onChange={(next) => setField("formats", Array.from(next))}
                    />
                  </div>
                </div>
              </div>
              <p className="muted">Assinantes em branco usam os do último relatório aprovado de cada projeto.</p>
            </section>
          )}
          {status && <p className="muted" role="status">{status}</p>}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>Fechar</button>
          <button type="button" className="primary" onClick={() => void save()} disabled={!form}>Salvar padrão</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
