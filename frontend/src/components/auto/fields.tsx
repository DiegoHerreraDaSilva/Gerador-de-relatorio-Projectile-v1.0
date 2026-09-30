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
import { ReviewerPicker } from "../ReviewerPicker";
import { useEffect, useMemo, useState } from "react";
import { useReportTabsStore } from "../../store/useReportTabsStore";
import { matchesNumberPattern, numberPatternLabel } from "../../utils/autoDraft";

/** Quem revisa este relatório. A lista vem do Projectile (engenharia com
 * login); o backend confere o login e grava o nome de lá. */
export function ReviewerField({ item, editable }: { item: AutoItem; editable: boolean }) {
  const reviewers = useAutoGenerationStore((s) => s.reviewers);
  const reviewersError = useAutoGenerationStore((s) => s.reviewersError);
  const busy = useAutoGenerationStore((s) => Boolean(s.busy[item.id]));
  const assign = useAutoGenerationStore((s) => s.assignReviewer);
  const current = item.reviewer_login ?? "";
  const hint = !current
    ? "Sem revisor: você revisa e aprova direto."
    : item.status === "em_revisao"
      ? `Com ${item.reviewer_name ?? current} pra revisar.`
      : item.status === "revisado"
        ? `${item.reviewer_name ?? current} mandou pra aprovação.`
        : item.status === "devolvido"
          ? `Devolvido pra ${item.reviewer_name ?? current}.`
          : null;

  if (!editable) {
    return current ? (
      <p className="auto-reviewer-readonly">
        <UserRound size={14} strokeWidth={2} aria-hidden="true" /> Revisado por {item.reviewer_name ?? current}
      </p>
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
      {hint && (
        <span id={`reviewer-hint-${item.id}`} className="muted auto-reviewer-hint">
          {hint}
        </span>
      )}
    </div>
  );
}

/** Mês em andamento (ainda sem rascunho): o revisor vai pra configuração do
 * projeto e o rascunho já nasce atribuído a ele — neste mês e nos próximos. */
export function PlannedReviewerField({
  familyKey,
  rule,
  remembered,
}: {
  familyKey: string;
  rule: ProjectRule;
  remembered: { login: string; name: string } | null;
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
      {error && (
        <span className="error-text auto-reviewer-hint" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

/** Devolver ao revisor: o comentário é obrigatório — é o que ele vai ver. */
export function ReturnForm({
  reviewerName,
  onSubmit,
  onCancel,
}: {
  reviewerName: string;
  onSubmit: (comment: string) => Promise<void>;
  onCancel: () => void;
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
        <textarea
          rows={3}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={2000}
          placeholder="Ex.: separe a reunião de alinhamento em outro grupo."
          autoFocus
        />
      </label>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      <div className="auto-config-actions">
        <button type="button" className="btn-secondary" onClick={onCancel} disabled={sending}>
          Cancelar
        </button>
        <button type="button" className="primary" onClick={() => void submit()} disabled={sending}>
          <Undo2 size={14} strokeWidth={2} /> {sending ? "Devolvendo…" : "Devolver ao revisor"}
        </button>
      </div>
    </div>
  );
}

/** Mês em andamento (ainda sem rascunho): o número do relatório já pode ser
 * digitado — fica guardado pra esta competência e vai pro rascunho quando ele
 * for gerado. Só cabe com UM relatório por projeto (com vários pacotes o
 * número é digitado depois, um por pacote). */
export function PlannedNumberField({
  preview,
  pattern,
  model,
}: {
  preview: PreviewProject;
  pattern?: string;
  model?: string | null;
}) {
  const setPlannedNumber = useAutoGenerationStore((s) => s.setPlannedNumber);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  if (preview.effective.mode !== "projeto") {
    return (
      <p className="muted auto-numbers-hint">
        Um relatório por pacote: os números são digitados depois de gerar, um por pacote.
      </p>
    );
  }
  const commit = async (code: string) => {
    setSaving(true);
    setError("");
    try {
      await setPlannedNumber(preview.project_id, code);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="auto-numbers">
      <span className="auto-numbers-label">Número do relatório</span>
      <NumberInput
        value={preview.planned_number ?? ""}
        suggested=""
        pattern={pattern}
        model={model}
        disabled={saving}
        onCommit={(code) => void commit(code)}
      />
      {error && (
        <span className="error-text auto-numbers-hint" role="alert">
          {error}
        </span>
      )}
      <span className="muted auto-numbers-hint">
        {preview.planned_number
          ? "Vai direto pro rascunho quando ele for gerado."
          : "Opcional — dá pra digitar depois de gerar."}
      </span>
    </div>
  );
}

export function NumbersField({
  item,
  editable,
  pattern,
  model,
}: {
  item: AutoItem;
  editable: boolean;
  pattern?: string;
  model?: string | null;
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
        <NumberInput
          key={id}
          label={ids.length > 1 ? names[i] : undefined}
          value={numbers[i] ?? ""}
          suggested={suggested[i] ?? ""}
          pattern={pattern}
          model={model}
          disabled={!canType || busy}
          onCommit={(code) => void setNumber(item, id, code)}
        />
      ))}
      {editable && open && <span className="muted auto-numbers-hint">Aberto no editor — digite o número lá.</span>}
    </div>
  );
}

export function NumberInput({
  label,
  value,
  suggested,
  pattern,
  model,
  disabled,
  onCommit,
}: {
  label?: string;
  value: string;
  suggested: string;
  pattern?: string;
  model?: string | null;
  disabled: boolean;
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
      {label && (
        <span className="auto-number-package" title={label}>
          {label}
        </span>
      )}
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
