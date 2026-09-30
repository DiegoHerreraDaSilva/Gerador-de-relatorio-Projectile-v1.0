import { describeBlockView, CustomBlockView } from "../../utils/customScope";
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
} from "../../store/useAutoGenerationStore";
import { describeSchedule, formatScheduleAt } from "../../utils/autoSchedule";
import { confirmDialog } from "../ConfirmDialog";
import { MODE_LABELS, SPLIT_LABELS, competenceLabel, fmtDate, ownConfigChips } from "./format";
import { ProjectConfig } from "./ProjectConfig";

/** Os recortes de uma geração personalizada, um por linha, com nomes. */
export function CustomBlocksList({ blocks }: { blocks: CustomBlockView[] }) {
  if (!blocks.length) return null;
  return (
    <ul className="auto-request-blocks" aria-label="Recortes">
      {blocks.map((block, index) => (
        <li key={index}>
          {blocks.length > 1 && <span className="auto-request-block-n">Recorte {index + 1}</span>}
          <span>{describeBlockView(block)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Pedido de geração personalizada agendado — ainda não é rascunho. */
export function CustomRequestCard({ request }: { request: CustomRequestItem }) {
  const remove = useAutoGenerationStore((s) => s.deleteCustomRequest);
  const config = useAutoGenerationStore((s) => s.config);
  const schedule = useAutoGenerationStore((s) => s.schedule);
  const [showConfig, setShowConfig] = useState(false);
  const failed = request.status === "erro";
  const unit: CustomUnit = request.package_unit ?? "projeto";
  const configKey = JSON.stringify(request.config ?? {});
  const rule = useMemo<ProjectRule>(() => ({ ...JSON.parse(configKey), mode: unit }), [configKey, unit]);
  const chips = ownConfigChips(request.config);
  const name = request.title || "Geração personalizada";
  const generatesAt =
    schedule?.enabled && schedule.target === request.competence
      ? `${formatScheduleAt(schedule.next_at)}, junto com os automáticos`
      : `quando a rodada de ${competenceLabel(request.competence)} rodar`;
  const cancel = async () => {
    const ok = await confirmDialog({
      title: "Cancelar este pedido?",
      message: `"${name}" (${request.summary || request.label}) deixa de ser gerado na rodada do mês.`,
      confirmLabel: "Cancelar pedido",
      cancelLabel: "Manter",
      danger: true,
    });
    if (ok) void remove(request);
  };
  return (
    <article className={`card auto-card auto-request ${failed ? "auto-request-error" : ""}`} aria-label={name}>
      <div className="auto-card-row">
        <div className="auto-card-main">
          <div className="auto-card-title">
            <h3>{name}</h3>
            <span className="muted auto-custom-scope">{request.label}</span>
          </div>
          {request.blocks?.length ? (
            <CustomBlocksList blocks={request.blocks} />
          ) : (
            <p className="muted auto-custom-scope">{request.summary}</p>
          )}
          <div className="auto-badges">
            <span className="auto-badge auto-badge-custom">personalizado</span>
            {chips.map((chip) => (
              <span key={chip} className="auto-badge" title="Configuração própria deste pedido">
                {chip}
              </span>
            ))}
          </div>
          {failed && request.error && (
            <p className="error-text auto-error">
              A última rodada não gerou: {request.error} A próxima rodada tenta de novo.
            </p>
          )}
        </div>
        <div className="auto-card-data">
          <dl className="auto-card-facts">
            <div>
              <dt>Período</dt>
              <dd>{request.label}</dd>
            </div>
            <div>
              <dt>Lista</dt>
              <dd>{SPLIT_LABELS[request.split_by ?? "nenhum"]}</dd>
            </div>
            <div>
              <dt>Relatório</dt>
              <dd>{MODE_LABELS[unit]}</dd>
            </div>
            <div>
              <dt>Revisor</dt>
              <dd>{request.reviewer_name ?? "o do projeto, se houver"}</dd>
            </div>
            <div>
              <dt>Agendado</dt>
              <dd>
                {request.created_by_name ?? "—"}
                {request.created_at ? ` · ${fmtDate(request.created_at)}` : ""}
              </dd>
            </div>
            <div>
              <dt>Gera em</dt>
              <dd>{generatesAt}</dd>
            </div>
          </dl>
        </div>
        <div className="auto-card-side">
          <span className={`auto-status-pill ${failed ? "auto-status-erro" : "auto-status-em_revisao"}`}>
            {failed ? "Erro na rodada" : "Agendado"}
          </span>
          <div className="auto-card-actions">
            <button
              type="button"
              className="btn-secondary auto-delete-button"
              onClick={() => void cancel()}
              title="Cancela o pedido — nada foi gerado ainda"
            >
              <Trash2 size={14} strokeWidth={2} /> Cancelar
            </button>
            <button
              type="button"
              className="btn-secondary auto-config-toggle"
              aria-expanded={showConfig}
              onClick={() => setShowConfig((v) => !v)}
            >
              <SlidersHorizontal size={14} strokeWidth={2} /> Configuração{" "}
              <ChevronDown size={14} className={showConfig ? "flipped" : ""} />
            </button>
          </div>
        </div>
      </div>
      {showConfig && (
        <ProjectConfig
          familyKey=""
          rule={rule}
          effective={(config?.effective ?? {}) as unknown as EffectiveConfig}
          custom={{
            unit,
            onSave: (form) => useAutoGenerationStore.getState().saveCustomConfig({ requestId: request.id, unit }, form),
            savedMessage: "Salvo. Vale quando este pedido for gerado.",
          }}
        />
      )}
    </article>
  );
}
