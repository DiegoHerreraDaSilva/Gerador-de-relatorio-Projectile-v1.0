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
import { fmtNum } from "../../utils/fmt";
import { ReviewNote } from "../MyReviewsPanel";
import { AutoSendModal, BulkSendModal } from "../AutoSendModal";
import { confirmDialog } from "../ConfirmDialog";
import { CUSTOM_UNIT_LABELS, MODE_LABELS, PLANNED_LABELS, SELECTABLE, fmtDate, reopenWarning } from "./format";
import { StatusPill } from "./StatusPill";
import { UncertainSend } from "./UncertainSend";
import { NumbersField, PlannedNumberField, PlannedReviewerField, ReturnForm, ReviewerField } from "./fields";
import { CustomBlocksList } from "./CustomRequestCard";
import { ProjectConfig } from "./ProjectConfig";

/** Um projeto: o rascunho (quando já gerado) ou a prévia do mês em
 * andamento, e a configuração individual. */
export function ProjectCard({
  title,
  client,
  familyKey,
  rule,
  effective,
  item,
  preview,
  onOpen,
  selected = false,
  onToggleSelect,
}: {
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
  // personalizado: recorte livre, sem família (nada de configuração individual nem "modo desatualizado")
  const isCustom = item?.kind === "avulso";
  // configuração própria do personalizado (memoizada: o formulário do painel se reinicia quando `rule` muda)
  const customUnit: CustomUnit = item?.scope_json?.package_unit ?? item?.badges?.mode ?? "projeto";
  const customConfigKey = JSON.stringify(item?.scope_json?.config ?? {});
  const customRule = useMemo<ProjectRule>(
    () => ({ ...JSON.parse(customConfigKey), mode: customUnit }),
    [customConfigKey, customUnit],
  );
  // o bloco mostra como o rascunho FOI gerado; a configuração pode ter mudado depois
  const draftMode = item ? (badges.mode ?? effective.mode) : effective.mode;
  const modeOutdated = !isCustom && Boolean(item && badges.mode && badges.mode !== effective.mode);

  const confirmRegenerate = async () => {
    if (!item) return;
    if (editable) {
      const ok = await confirmDialog({
        title: "Gerar de novo?",
        message: `"${title}" será gerado de novo a partir do Projectile. As edições feitas no rascunho serão descartadas.`,
        confirmLabel: "Gerar de novo",
        danger: true,
      });
      if (!ok) return;
    }
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
            {isCustom && item?.scope_json && (
              <span className="muted auto-custom-scope" title={item.scope_json.summary}>
                {item.scope_json.label}
                {item.scope_json.summary ? ` · ${item.scope_json.summary}` : ""}
              </span>
            )}
            {isCustom && (item?.scope_json?.blocks?.length ?? 0) > 0 && (
              <CustomBlocksList blocks={item!.scope_json!.blocks!} />
            )}
          </div>
          <div className="auto-badges">
            {isCustom && (
              <span className="auto-badge auto-badge-custom" title="Recorte livre, fora da rodada mensal">
                personalizado
              </span>
            )}
            {badges.partial && (
              <span
                className="auto-badge auto-badge-warn"
                title="Não cobre o projeto (ou pacote) inteiro — no Diagnóstico aparece como envio parcial e nunca fecha o projeto"
              >
                recorte parcial
              </span>
            )}
            {badges.memory_applied && (
              <span
                className="auto-badge"
                title="Nomes de grupo, performance, descrições e assinantes do último relatório aprovado deste projeto"
              >
                memória do mês anterior
              </span>
            )}
            {badges.hours_changed && (
              <span
                className="auto-badge auto-badge-warn"
                title="As horas do Projectile mudaram depois que o rascunho foi gerado"
              >
                horas mudaram
              </span>
            )}
            {(badges.missing_hours ?? 0) > 0 && (
              <span
                className="auto-badge auto-badge-warn"
                title="Lançamentos sem descrição no Projectile não entram no relatório — aparecem como aviso no editor, onde dá pra adicionar como atividade"
              >
                {fmtNum(badges.missing_hours ?? 0)} h sem descrição
              </span>
            )}
            {badges.skip_reason && <span className="auto-badge">{badges.skip_reason}</span>}
            {hasRule && (
              <span className="auto-badge" title="Este projeto tem configuração própria">
                configuração própria
              </span>
            )}
          </div>
          {item?.status === "erro" && item.error && <p className="error-text auto-error">{item.error}</p>}
        </div>

        <div className="auto-card-data">
          <dl className="auto-card-facts">
            <div>
              <dt>Horas</dt>
              <dd>
                {item?.source_hours != null
                  ? `${fmtNum(item.source_hours)} h`
                  : preview
                    ? `${fmtNum(preview.hours)} h até agora`
                    : "—"}
                {badges.hours_changed && item?.hours_now != null && (
                  <span className="muted"> · {fmtNum(item.hours_now)} h agora</span>
                )}
              </dd>
            </div>
            <div>
              <dt>Relatório</dt>
              <dd>
                {(isCustom ? CUSTOM_UNIT_LABELS : MODE_LABELS)[draftMode] ?? draftMode}
                {(badges.packages ?? 0) > 1 ? ` · ${badges.packages} relatórios` : ""}
              </dd>
            </div>
          </dl>
          {modeOutdated && (
            <p className="auto-mode-hint">
              Gerado como “{MODE_LABELS[draftMode].toLowerCase()}”; a configuração agora é “
              {MODE_LABELS[effective.mode].toLowerCase()}”.
              {editable && (
                <button type="button" className="auto-link-button" onClick={confirmRegenerate} disabled={busy}>
                  Regenerar pra aplicar
                </button>
              )}
            </p>
          )}
          {item && (badges.package_ids?.length ?? 0) > 0 && (
            <NumbersField
              item={item}
              editable={editable}
              pattern={effective.number_pattern}
              model={effective.number_model}
            />
          )}
          {item && status !== "erro" && status !== "pulado" && <ReviewerField item={item} editable={editable} />}
          {item?.last_comment?.comment && <ReviewNote comment={item.last_comment} />}
          {sent && item?.last_sent && (
            <p className="auto-sent-info">
              <Send size={14} strokeWidth={2} aria-hidden="true" />
              <span>
                Enviado {fmtDate(item.last_sent.created_at)}
                {item.last_sent.actor_name ? ` por ${item.last_sent.actor_name}` : ""} pra{" "}
                {[...item.last_sent.to, ...item.last_sent.cc].join(", ")}
              </span>
            </p>
          )}
          {item?.send_uncertain && <UncertainSend item={item} busy={busy} />}
          {preview && preview.planned === "sera_gerado" && (
            <PlannedNumberField preview={preview} pattern={effective.number_pattern} model={effective.number_model} />
          )}
          {preview && preview.planned === "sera_gerado" && (
            <PlannedReviewerField familyKey={familyKey} rule={rule} remembered={preview.remembered_reviewer} />
          )}
        </div>

        <div className="auto-card-side">
          {status ? (
            <StatusPill status={status} />
          ) : (
            preview && (
              <span className={`auto-status-pill ${preview.planned === "sera_gerado" ? "auto-status-em_revisao" : ""}`}>
                {PLANNED_LABELS[preview.planned]}
              </span>
            )
          )}
          <div className="auto-card-actions">
            {canReturn && (
              <button
                type="button"
                className="btn-secondary"
                aria-expanded={showReturn}
                onClick={() => setShowReturn((v) => !v)}
                disabled={busy}
              >
                <Undo2 size={14} strokeWidth={2} /> Devolver
              </button>
            )}
            {item && !item.send_uncertain && (item.status === "aprovado" || sent) && (
              <button
                type="button"
                className={sent ? "btn-secondary" : "primary"}
                onClick={() => setShowSend(true)}
                disabled={busy}
              >
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
            {item && (item.status === "aprovado" || sent) && (
              <button
                type="button"
                className="btn-secondary"
                disabled={busy}
                onClick={async () => {
                  const ok = await confirmDialog({
                    title: "Reabrir pra revisão?",
                    message: reopenWarning(sent ? 1 : 0),
                    confirmLabel: "Reabrir",
                  });
                  if (ok) void action(item, "reopen");
                }}
              >
                <RotateCcw size={14} strokeWidth={2} /> Reabrir
              </button>
            )}
            {item && (editable || item.status === "erro" || item.status === "pulado") && (
              <button
                type="button"
                className="btn-secondary"
                onClick={confirmRegenerate}
                disabled={busy}
                title={
                  item.status === "pulado"
                    ? "Gerar o rascunho deste projeto"
                    : "Gerar de novo a partir do Projectile, com a configuração atual"
                }
              >
                <RefreshCw size={14} strokeWidth={2} /> {item.status === "pulado" ? "Gerar" : "Regenerar"}
              </button>
            )}
            {item && (editable || item.status === "erro") && (
              <button
                type="button"
                className="btn-secondary"
                disabled={busy}
                onClick={async () => {
                  const ok = await confirmDialog({
                    title: "Pular este relatório?",
                    message: isCustom ? `"${title}" será pulado.` : `"${title}" será pulado neste mês.`,
                    confirmLabel: "Pular",
                  });
                  if (ok) void action(item, "skip");
                }}
              >
                <SkipForward size={14} strokeWidth={2} /> Pular
              </button>
            )}
            {item && isCustom && !SELECTABLE.includes(item.status) && item.status !== "gerando" && (
              <button
                type="button"
                className="btn-secondary auto-delete-button"
                disabled={busy}
                title="Apaga este relatório personalizado e a linha do tempo dele"
                onClick={async () => {
                  const ok = await confirmDialog({
                    title: "Apagar este relatório?",
                    message: `"${title}": o rascunho e a linha do tempo dele serão apagados. Não dá pra desfazer.`,
                    confirmLabel: "Apagar",
                    danger: true,
                  });
                  if (ok) void useAutoGenerationStore.getState().deleteCustom(item);
                }}
              >
                <Trash2 size={14} strokeWidth={2} /> Apagar
              </button>
            )}
            {!onToggleSelect && (
              <button
                type="button"
                className="btn-secondary auto-config-toggle"
                aria-expanded={showConfig}
                onClick={() => setShowConfig((v) => !v)}
              >
                <SlidersHorizontal size={14} strokeWidth={2} /> Configuração{" "}
                <ChevronDown size={14} className={showConfig ? "flipped" : ""} />
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
        <ReturnForm
          reviewerName={item.reviewer_name ?? ""}
          onCancel={() => setShowReturn(false)}
          onSubmit={async (comment) => {
            await useAutoGenerationStore.getState().returnToReviewer(item.id, comment);
            setShowReturn(false);
          }}
        />
      )}
      {showSend && item && <AutoSendModal item={item} onClose={() => setShowSend(false)} />}
      {showConfig && !onToggleSelect && isCustom && item && (
        <ProjectConfig
          familyKey=""
          rule={customRule}
          effective={effective}
          item={item}
          onRegenerate={editable ? confirmRegenerate : undefined}
          custom={{
            unit: customUnit,
            onSave: (form) =>
              useAutoGenerationStore.getState().saveCustomConfig({ reportId: item.id, unit: customUnit }, form),
            savedMessage: "Salvo. O rascunho não muda sozinho: regenere pra aplicar.",
          }}
        />
      )}
      {showConfig && !onToggleSelect && !isCustom && (
        <ProjectConfig
          familyKey={familyKey}
          rule={rule}
          effective={effective}
          item={item}
          onRegenerate={item && editable ? confirmRegenerate : undefined}
        />
      )}
    </article>
  );
}
