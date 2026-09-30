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
import { STATUS_LABELS } from "./format";

// ordem das etapas na faixa de filtros (o caminho feliz primeiro)
export const STAGES: AutoStatus[] = ["em_revisao", "revisado", "devolvido", "aprovado", "enviado", "erro", "pulado"];

export function StatusPill({ status }: { status: AutoStatus }) {
  return <span className={`auto-status-pill auto-status-${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}
