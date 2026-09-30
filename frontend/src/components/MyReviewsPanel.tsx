import { useEffect, useState, type ReactNode } from "react";
import { ClipboardCheck, FilePen, MessageSquareText, RefreshCw } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { StatusPill, periodLabelOf } from "./AutoGenerationPanel";
import type { AppView } from "../appView";
import { useAutoGenerationStore } from "../store/useAutoGenerationStore";
import { useMyReviewsStore, type ReviewItem } from "../store/useMyReviewsStore";
import { fmtNum } from "../utils/fmt";
import { ErrorState, LoadingState } from "./PageStates";

/** "Minhas revisões": os relatórios da geração automática que o gerente
 * atribuiu a quem está logado. Revisa no editor de sempre e manda pra
 * aprovação; o número do relatório e a aprovação continuam com o gerente. */
export function MyReviewsPanel({ onNavigate }: { onNavigate: (view: AppView) => void }) {
  const toReview = useMyReviewsStore((s) => s.toReview);
  const awaiting = useMyReviewsStore((s) => s.awaitingApproval);
  const done = useMyReviewsStore((s) => s.done);
  const loaded = useMyReviewsStore((s) => s.loaded);
  const loading = useMyReviewsStore((s) => s.loading);
  const error = useMyReviewsStore((s) => s.error);
  const load = useMyReviewsStore((s) => s.load);
  const [openError, setOpenError] = useState("");

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const open = async (item: ReviewItem) => {
    setOpenError("");
    try {
      await useAutoGenerationStore.getState().openInEditor(item.id, "reviewer");
      onNavigate("report");
    } catch (e) {
      setOpenError(e instanceof Error ? e.message : String(e));
    }
  };

  const empty = loaded && !toReview.length && !awaiting.length && !done.length;

  return (
    <div className="auto-panel page-container">
      <PageHeader
        title="Minhas revisões"
        description="Relatórios que o gerente pediu pra você revisar. Abra no editor, ajuste o que precisar e mande pra aprovação."
        icon={<ClipboardCheck size={20} strokeWidth={1.8} />}
        actions={
          <button type="button" className="btn-secondary" onClick={() => void load()} disabled={loading}>
            <RefreshCw size={14} strokeWidth={2} className={loading ? "spin" : ""} /> Atualizar
          </button>
        }
      />

      {error && (
        <div className="card">
          <ErrorState message={error} onRetry={() => void load()} busy={loading} />
        </div>
      )}
      {openError && (
        <div className="card">
          <p className="error-text">{openError}</p>
        </div>
      )}
      {loading && !loaded && (
        <div className="card">
          <LoadingState label="Carregando revisões..." rows={4} />
        </div>
      )}
      {empty && (
        <div className="card auto-run-card">
          <div>
            <h3>Nada pra revisar agora</h3>
            <p className="muted">Quando o gerente atribuir um relatório a você, ele aparece aqui e no menu.</p>
          </div>
        </div>
      )}

      {toReview.length > 0 && (
        <ReviewSection title="Pra revisar" hint="Edite no editor; as alterações são salvas sozinhas.">
          {toReview.map((item) => (
            <ReviewCard key={item.id} item={item} onOpen={() => void open(item)} primary />
          ))}
        </ReviewSection>
      )}
      {awaiting.length > 0 && (
        <ReviewSection
          title="Aguardando o gerente"
          hint="Você mandou pra aprovação. Se ele devolver, o relatório volta pra cima."
        >
          {awaiting.map((item) => (
            <ReviewCard key={item.id} item={item} onOpen={() => void open(item)} />
          ))}
        </ReviewSection>
      )}
      {done.length > 0 && (
        <ReviewSection title="Aprovados">
          {done.map((item) => (
            <ReviewCard key={item.id} item={item} />
          ))}
        </ReviewSection>
      )}
    </div>
  );
}

function ReviewSection({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="auto-review-section" aria-label={title}>
      <div className="auto-review-section-head">
        <h2>{title}</h2>
        {hint && <p className="muted">{hint}</p>}
      </div>
      <div className="auto-cards">{children}</div>
    </section>
  );
}

function ReviewCard({ item, onOpen, primary = false }: { item: ReviewItem; onOpen?: () => void; primary?: boolean }) {
  const missing = item.badges.missing_hours ?? 0;
  const comment = item.last_comment;
  return (
    <article className={`card auto-card auto-card-${item.status}`} aria-label={item.project_name}>
      <div className="auto-card-row">
        <div className="auto-card-main">
          <div className="auto-card-title">
            <h3 title={item.project_name}>{item.project_name}</h3>
            <span className="muted">
              {item.client ?? ""} · {periodLabelOf(item)}
            </span>
          </div>
          {missing > 0 && (
            <div className="auto-badges">
              <span
                className="auto-badge auto-badge-warn"
                title="Lançamentos sem descrição no Projectile — aparecem como aviso no editor, onde dá pra adicionar como atividade"
              >
                {fmtNum(missing)} h sem descrição
              </span>
            </div>
          )}
        </div>
        <div className="auto-card-data">
          <dl className="auto-card-facts">
            <div>
              <dt>Horas</dt>
              <dd>{item.source_hours != null ? `${fmtNum(item.source_hours)} h` : "—"}</dd>
            </div>
          </dl>
          {comment?.comment && <ReviewNote comment={comment} />}
        </div>
        <div className="auto-card-side">
          <StatusPill status={item.status} />
          {onOpen && (
            <div className="auto-card-actions">
              <button type="button" className={primary ? "primary" : "btn-secondary"} onClick={onOpen}>
                <FilePen size={14} strokeWidth={2} /> {primary ? "Abrir no editor" : "Ver"}
              </button>
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

/** Observação de quem revisou ou o pedido da devolução. */
export function ReviewNote({
  comment,
}: {
  comment: { action: string; comment: string | null; actor_name: string | null };
}) {
  const returned = comment.action === "returned";
  return (
    <p className={`auto-review-note ${returned ? "auto-review-note-returned" : ""}`}>
      <MessageSquareText size={14} strokeWidth={2} aria-hidden="true" />
      <span>
        <strong>
          {returned ? "Devolvido" : "Observação"}
          {comment.actor_name ? ` por ${comment.actor_name}` : ""}:
        </strong>{" "}
        {comment.comment}
      </span>
    </p>
  );
}
