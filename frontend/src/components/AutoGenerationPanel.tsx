import {
  CUSTOM_KEY,
  EDITABLE_STATUSES,
  useAutoGenerationStore,
  AutoItem,
  AutoStatus,
  CustomConfigValues,
  CustomRequestItem,
  CustomUnit,
  EffectiveConfig,
  PreviewProject,
  ProjectRule,
} from "../store/useAutoGenerationStore";
import { useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  ChevronDown,
  Download,
  FilePen,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  SkipForward,
  SlidersHorizontal,
  Send,
  Trash2,
  Undo2,
  UserRound,
  X,
} from "lucide-react";
import { PageHeader } from "./PageHeader";
import { AppView } from "../appView";
import { fmtNum } from "../utils/fmt";
import { describeSchedule, formatScheduleAt } from "../utils/autoSchedule";
import { AutoSendModal, BulkSendModal } from "./AutoSendModal";
import { AutoCustomModal } from "./AutoCustomModal";
import { Select } from "./Select";
import { confirmDialog } from "./ConfirmDialog";
import { SELECTABLE, STATUS_LABELS, competenceLabel, fmtDate, reopenWarning } from "./auto/format";
import { STAGES } from "./auto/StatusPill";
import { CustomRequestCard } from "./auto/CustomRequestCard";
import { ProjectCard } from "./auto/ProjectCard";
import { AutoSettingsModal } from "./auto/AutoSettingsModal";
export { StatusPill } from "./auto/StatusPill";
export { competenceLabel, periodLabelOf } from "./auto/format";

/** Aba "Geração automática" (só gerente): um bloco por projeto da
 * competência, cada um com status, número, ações e a configuração
 * individual do projeto. A revisão/aprovação acontece no editor de sempre. */
export function AutoGenerationPanel({ onNavigate }: { onNavigate: (view: AppView) => void }) {
  const current = useAutoGenerationStore((s) => s.current);
  const previous = useAutoGenerationStore((s) => s.previous);
  const runs = useAutoGenerationStore((s) => s.runs);
  const selected = useAutoGenerationStore((s) => s.selected);
  const view = useAutoGenerationStore((s) => s.view);
  const customRequests = useAutoGenerationStore((s) => s.customRequests);
  const schedule = useAutoGenerationStore((s) => s.schedule);
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
  const [showCustom, setShowCustom] = useState(false);
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
  const isCustomTab = selected === CUSTOM_KEY;
  const running = view?.run?.status === "running";
  const term = search.trim().toLocaleLowerCase("pt-BR");
  const matches = (text: string) => !term || text.toLocaleLowerCase("pt-BR").includes(term);
  const items = useMemo(
    () =>
      (view?.items ?? []).filter(
        (i) => (stage === "all" || i.status === stage) && matches(`${i.project_name} ${i.client ?? ""}`),
      ),
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
    const reopenable = pickedItems;
    if (!reopenable.length) return;
    const sentCount = reopenable.filter((i) => i.status === "enviado").length;
    const ok = await confirmDialog({
      title: `Reabrir ${reopenable.length} relatório${reopenable.length === 1 ? "" : "s"}?`,
      message: `Voltam pra revisão. ${reopenWarning(sentCount)}`,
      confirmLabel: "Reabrir",
    });
    if (!ok) return;
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
            <button type="button" className="primary" onClick={() => setShowCustom(true)}>
              <Plus size={14} strokeWidth={2} /> Nova geração personalizada
            </button>
            <button type="button" className="btn-secondary" onClick={() => setShowSettings(true)}>
              <Settings size={14} strokeWidth={2} /> Padrão geral
            </button>
            <button type="button" className="btn-secondary" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} /> Atualizar
            </button>
          </>
        }
      />

      {schedule && (
        <p className={`auto-schedule-line ${schedule.enabled ? "" : "auto-schedule-line-off"}`}>
          <CalendarClock size={15} strokeWidth={2} aria-hidden="true" /> {describeSchedule(schedule)}
        </p>
      )}

      <div className="auto-competences" role="tablist" aria-label="Competência">
        {previous && (
          <button
            type="button"
            role="tab"
            aria-selected={selected === previous}
            className={selected === previous ? "active" : ""}
            onClick={() => void select(previous)}
          >
            <span className="auto-competence-kind">Mês passado</span>
            {competenceLabel(previous)}
          </button>
        )}
        {current && (
          <button
            type="button"
            role="tab"
            aria-selected={selected === current}
            className={selected === current ? "active" : ""}
            onClick={() => void select(current)}
          >
            <span className="auto-competence-kind">Mês atual</span>
            {competenceLabel(current)}
          </button>
        )}
        <button
          type="button"
          role="tab"
          aria-selected={isCustomTab}
          className={isCustomTab ? "active" : ""}
          onClick={() => void select(CUSTOM_KEY)}
        >
          <span className="auto-competence-kind">Recorte livre</span>
          Personalizados
        </button>
        {olderRuns.length > 0 && (
          <Select
            className="auto-older-select"
            ariaLabel="Competências anteriores"
            value={olderRuns.some((r) => r.competence === selected) ? (selected ?? "") : ""}
            onChange={(v) => v && void select(v)}
            options={[
              { value: "", label: "Anteriores…" },
              ...olderRuns.map((r) => ({ value: r.competence, label: competenceLabel(r.competence) })),
            ]}
          />
        )}
      </div>

      {error && (
        <div className="card">
          <p className="error-text">{error}</p>
        </div>
      )}
      {openError && (
        <div className="card">
          <p className="error-text">{openError}</p>
        </div>
      )}
      {loading && !view && (
        <div className="card">
          <p className="muted">Carregando...</p>
        </div>
      )}

      {view && !view.run && (
        <div className="card auto-run-card">
          <div>
            <h3>
              {view.competence === current
                ? `${view.month_label} ainda está em andamento`
                : `Nenhum rascunho de ${view.month_label} ainda`}
            </h3>
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

      {isCustomTab && customRequests.length > 0 && (
        <section className="auto-requests" aria-label="Pedidos agendados">
          <h3>
            Agendados <span className="muted">— nascem junto com os automáticos, quando o mês fecha</span>
          </h3>
          {customRequests.map((r) => (
            <CustomRequestCard key={r.id} request={r} />
          ))}
        </section>
      )}

      {isCustomTab && view && view.items.length === 0 && customRequests.length > 0 && !loading && (
        <div className="card auto-requests-note" role="status">
          <p>
            <strong>Nenhum relatório gerado ainda.</strong>{" "}
            {schedule?.enabled && customRequests.some((r) => r.competence === schedule.target)
              ? `Os pedidos acima viram relatórios na geração automática de ${formatScheduleAt(schedule.next_at)}, junto com os do mês.`
              : "Os pedidos acima viram relatórios quando a rodada do mês deles rodar — automaticamente na data agendada ou pelo botão “Gerar rascunhos” da competência, depois que o mês fechar."}
          </p>
        </div>
      )}

      {isCustomTab && view && view.items.length === 0 && customRequests.length === 0 && !loading && (
        <div className="card auto-run-card">
          <div>
            <h3>Nenhuma geração personalizada ainda</h3>
            <p className="muted">
              Agende relatórios de um colaborador, de um cliente ou de uma mistura de projetos e pacotes do mês atual.
              Eles são gerados junto com os automáticos, quando o mês fecha, e seguem a mesma esteira: revisão,
              aprovação e envio ao cliente.
            </p>
          </div>
          <button type="button" className="primary" onClick={() => setShowCustom(true)}>
            <Plus size={14} strokeWidth={2} /> Nova geração personalizada
          </button>
        </div>
      )}

      {view?.run && !isCustomTab && (running || view.run.status === "failed") && (
        <div className="card auto-run-card" role="status" aria-live="polite">
          {running ? (
            <p>
              <RefreshCw size={14} strokeWidth={2} className="spin" /> Gerando os rascunhos de {view.month_label}… a
              lista atualiza sozinha.
            </p>
          ) : (
            <p className="error-text">
              A última geração falhou: {view.run.error}. Os rascunhos já criados continuam aqui; gere de novo pra
              completar.
              {schedule?.enabled &&
                " Com a geração automática ligada, o agendador tenta de novo sozinho (de hora em hora, até 5 vezes)."}
            </p>
          )}
        </div>
      )}

      {view?.run && !isCustomTab && view.run.status === "done" && view.run.triggered_by === "sistema" && (
        <p className="auto-run-note muted">
          Rodada gerada automaticamente pelo agendador
          {view.run.finished_at ? ` em ${fmtDate(view.run.finished_at)}` : ""}.
        </p>
      )}

      {(view?.run || preview) && !(isCustomTab && view?.items.length === 0) && (
        <div className="auto-toolbar">
          <div className="send-status-search">
            <Search size={14} strokeWidth={2} />
            <input
              type="text"
              placeholder="Buscar por projeto ou cliente..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          {view?.run && (
            <div className="send-status-tabs auto-stages">
              {/* sem "Todos": nada marcado = lista inteira; clicar de novo na etapa marcada desfaz o filtro */}
              {STAGES.filter((s) => view.counts[s] || stage === s).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={stage === s ? "active" : ""}
                  aria-pressed={stage === s}
                  data-hint={stage === s ? "Clique de novo pra ver todos" : undefined}
                  onClick={() => setStage((current) => (current === s ? "all" : s))}
                >
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
            <ProjectCard
              key={item.id}
              title={item.project_name}
              client={item.client ?? ""}
              familyKey={item.family_key}
              rule={item.rule}
              effective={item.effective}
              item={item}
              onOpen={() => void openInEditor(item)}
              selected={picked.has(item.id)}
              onToggleSelect={SELECTABLE.includes(item.status) ? () => togglePick(item.id) : undefined}
            />
          ))}
          {items.length === 0 && (!isCustomTab || (view?.items.length ?? 0) > 0) && (
            <div className="card">
              <p className="muted">Nenhum projeto nesse filtro.</p>
            </div>
          )}
        </div>
      )}

      {preview && !view?.run && (
        <div className="auto-cards">
          {previewProjects.map((p) => (
            <ProjectCard
              key={p.project_id}
              title={p.name}
              client={p.client}
              familyKey={p.family_key}
              rule={p.rule}
              effective={p.effective}
              preview={p}
            />
          ))}
          {previewProjects.length === 0 && (
            <div className="card">
              <p className="muted">Nenhum projeto com horas ainda.</p>
            </div>
          )}
        </div>
      )}

      {view?.run && view.new_projects.length > 0 && !running && (
        <div className="card auto-new-projects">
          <div>
            <h3>
              {view.new_projects.length} projeto{view.new_projects.length === 1 ? "" : "s"} com horas depois da geração
            </h3>
            <p className="muted">{view.new_projects.map((p) => `${p.name} (${fmtNum(p.hours)} h)`).join(" · ")}</p>
          </div>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void run(view.new_projects.map((p) => p.project_id))}
          >
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
            <button
              type="button"
              className="auto-link-button"
              onClick={() => setPicked(new Set(selectableVisible.map((i) => i.id)))}
            >
              Selecionar todos os {selectableVisible.length}
            </button>
          )}
          <button type="button" className="auto-link-button" onClick={() => setPicked(new Set())}>
            Limpar
          </button>
          <div className="auto-bulk-actions">
            <button type="button" className="primary" onClick={() => setBulkSend(pickedItems)} disabled={bulkBusy}>
              <Send size={14} strokeWidth={2} /> Enviar ao cliente
            </button>
            <button type="button" className="btn-secondary" onClick={() => void bulkView()} disabled={bulkBusy}>
              <FilePen size={14} strokeWidth={2} /> Ver
            </button>
            <a
              className="btn-secondary"
              href={`/auto-generation/files?${pickedItems.map((i) => `ids=${encodeURIComponent(i.id)}`).join("&")}`}
            >
              <Download size={14} strokeWidth={2} /> Baixar
            </a>
            <button type="button" className="btn-secondary" onClick={() => void bulkReopen()} disabled={bulkBusy}>
              <RotateCcw size={14} strokeWidth={2} /> Reabrir
            </button>
          </div>
        </div>
      )}
      {bulkSend && (
        <BulkSendModal
          items={bulkSend}
          onClose={() => {
            setBulkSend(null);
            setPicked(new Set());
          }}
        />
      )}

      {showSettings && <AutoSettingsModal onClose={() => setShowSettings(false)} />}
      {showCustom && <AutoCustomModal onClose={() => setShowCustom(false)} />}
    </div>
  );
}
