import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useAutoGenerationStore, type AutoItem } from "../../store/useAutoGenerationStore";
import { confirmDialog } from "../ConfirmDialog";
import { fmtDate } from "./format";

/** Envio sem desfecho: o e-mail pode ter chegado ao cliente (falha do banco ou do Graph depois do
 * envio). O sistema bloqueia novos envios até o gerente dizer o que aconteceu — reenviar às cegas
 * poderia duplicar o que o cliente recebe. */
export function UncertainSend({ item, busy }: { item: AutoItem; busy: boolean }) {
  const resolveSend = useAutoGenerationStore((s) => s.resolveSend);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const attempt = item.send_uncertain;
  if (!attempt) return null;

  async function resolve(resolution: "sent" | "not_sent") {
    const arrived = resolution === "sent";
    const ok = await confirmDialog({
      title: arrived ? "O e-mail chegou?" : "O e-mail não chegou?",
      message: arrived
        ? "O relatório será marcado como enviado, sem mandar nada de novo."
        : "Você poderá enviar de novo. Confira antes na caixa de saída de quem enviou.",
      confirmLabel: arrived ? "Chegou" : "Não chegou",
    });
    if (!ok) return;
    setWorking(true);
    setError(null);
    try {
      await resolveSend(item, resolution);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível registrar.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="auto-uncertain" role="alert">
      <p>
        <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
        <span>
          Envio sem confirmação ({fmtDate(attempt.created_at)}
          {attempt.actor_name ? `, por ${attempt.actor_name}` : ""}) pra {[...attempt.to, ...attempt.cc].join(", ")}. O
          e-mail pode já ter chegado ao cliente — confira na caixa de saída antes de enviar de novo.
        </span>
      </p>
      <div className="auto-uncertain-actions">
        <button type="button" className="btn-secondary" disabled={busy || working} onClick={() => resolve("sent")}>
          Chegou
        </button>
        <button type="button" className="btn-secondary" disabled={busy || working} onClick={() => resolve("not_sent")}>
          Não chegou
        </button>
      </div>
      {error && <p className="auto-error">{error}</p>}
    </div>
  );
}
