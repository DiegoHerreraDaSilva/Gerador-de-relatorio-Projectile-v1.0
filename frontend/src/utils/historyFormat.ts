/** Formatação/tradução de rótulos pra tela de Histórico de relatórios
 * (`HistoryPanel.tsx`). Extraído em funções puras pra ser testável — mesma
 * convenção de `fmt.ts`/`calc.ts`. */

const _HAS_TZ = /[Zz]|[+-]\d\d:?\d\d$/;

/** O backend grava `datetime.now(timezone.utc).replace(tzinfo=None)` em
 * `reports_db` — o JSON devolvido pelo FastAPI vem SEM sufixo de fuso
 * (`"2026-09-22T14:12:13"`), mas o valor É UTC. Sem tratar isso, o
 * `new Date(...)` do browser interpretaria a string como hora LOCAL,
 * exibindo tudo com o offset do fuso trocado (3h adiantado em
 * São Paulo/UTC-3). Sempre trata como UTC quando não há sufixo de fuso. */
export function parseBackendTimestamp(raw: string): Date {
  const iso = _HAS_TZ.test(raw) ? raw : `${raw}Z`;
  return new Date(iso);
}

export function formatDateTime(raw: string): string {
  const date = parseBackendTimestamp(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unitIndex]}`;
}

export function formatDurationMs(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

const AUDIT_ACTION_LABELS: Record<string, string> = {
  report_created: "Relatório criado",
  report_version_created: "Nova versão criada",
  report_generated: "Arquivo gerado",
  report_generation_failed: "Falha na geração",
  artifact_downloaded: "Arquivo baixado",
};

export function formatAuditAction(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action;
}

const GENERATION_STATUS_LABELS: Record<string, string> = {
  started: "Em andamento",
  success: "Sucesso",
  failed: "Falha",
};

export function formatGenerationStatus(status: string): string {
  return GENERATION_STATUS_LABELS[status] ?? status;
}

const CREATED_FROM_LABELS: Record<string, string> = {
  generate_endpoint: "Gerar relatório",
  send_report_endpoint: "Enviar por e-mail",
};

export function formatCreatedFrom(source: string): string {
  return CREATED_FROM_LABELS[source] ?? source;
}
