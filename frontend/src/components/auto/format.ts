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

export const MONTHS = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

export function competenceLabel(competence: string | null | undefined): string {
  if (!competence) return "";
  const [year, month] = competence.split("-");
  return `${MONTHS[Number(month) - 1] ?? month}/${year}`;
}

/** Período de um relatório da lista: o do recorte nos personalizados
 * ("Julho a Novembro/2026"), o mês da competência nos demais. */
export function periodLabelOf(item: { competence: string; scope_json?: { label?: string } | null }): string {
  return item.scope_json?.label ?? competenceLabel(item.competence);
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

export const MODE_LABELS = { projeto: "Um relatório pro projeto", pacote: "Um relatório por pacote" } as const;

// no personalizado o "modo" é o que vira pacote DENTRO do relatório (o recorte pode juntar vários projetos)
export const CUSTOM_UNIT_LABELS = {
  projeto: "Um relatório por projeto",
  pacote: "Um relatório por pacote de trabalho",
} as const;

export const SPLIT_LABELS = {
  nenhum: "Tudo junto (1 item na lista)",
  projeto: "Um item por projeto",
  pacote: "Um item por pacote de trabalho",
  colaborador: "Um item por colaborador",
} as const;

export const FORMAT_LABELS: Record<string, string> = { xlsx: "XLSX", pdf: "PDF" };

/** O que a configuração PRÓPRIA do pedido define, em chips ("assinante Schwaben: Diego", "arquivos: PDF"). */
export function ownConfigChips(config: CustomConfigValues | undefined): string[] {
  const out: string[] = [];
  if (config?.signer1_name) out.push(`assinante Schwaben: ${config.signer1_name}`);
  if (config?.signer1_company) out.push(`empresa Schwaben: ${config.signer1_company}`);
  if (config?.signer2_name) out.push(`assinante do cliente: ${config.signer2_name}`);
  if (config?.signer2_company) out.push(`empresa do cliente: ${config.signer2_company}`);
  if (config?.formats) out.push(`arquivos: ${config.formats.map((f) => FORMAT_LABELS[f] ?? f).join(" + ")}`);
  return out;
}

/** O que a confirmação de "Reabrir" avisa — enviado já está com o cliente. */
export function reopenWarning(sentCount: number): string {
  const base = "A aprovação é desfeita (o que foi pro histórico continua lá).";
  if (!sentCount) return base;
  return (
    `${base}\n\n${sentCount === 1 ? "Ele já foi enviado" : `${sentCount} já foram enviados`} ao cliente: ` +
    "depois de corrigir, aprove e envie de novo — o cliente só tem a versão anterior."
  );
}

export function fmtDate(value: string): string {
  // o backend grava UTC sem fuso ("2026-09-28T14:05:00")
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export const PLANNED_LABELS = {
  sera_gerado: "Será gerado",
  fechado: "Fechado no Diagnóstico",
  desativado: "Desligado neste projeto",
} as const;

export const SELECTABLE: AutoStatus[] = ["aprovado", "enviado"];
