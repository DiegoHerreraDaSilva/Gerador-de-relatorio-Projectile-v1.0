export type ReportImportSource = "file" | "db";

export type ReportImportActionInput = {
  source: ReportImportSource;
  hasFile: boolean;
  busy: boolean;
  byClient: boolean;
  hasClient: boolean;
  selectedProjectCount: number;
};

export function getReportImportActionState(input: ReportImportActionInput) {
  if (input.source === "file") {
    return {
      disabled: input.busy || !input.hasFile,
      label: input.busy ? "Validando..." : "Validar planilha",
    };
  }

  const missingClientSelection =
    input.byClient && (!input.hasClient || input.selectedProjectCount === 0);

  return {
    disabled: input.busy || missingClientSelection,
    label: input.busy ? "Buscando..." : "Buscar dados",
  };
}
