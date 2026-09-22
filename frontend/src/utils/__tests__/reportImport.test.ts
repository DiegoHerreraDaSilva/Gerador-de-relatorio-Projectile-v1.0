import { describe, expect, it } from "vitest";
import { getReportImportActionState } from "../reportImport";

describe("getReportImportActionState", () => {
  it("mantém a validação local desabilitada até existir um arquivo", () => {
    expect(getReportImportActionState({
      source: "file",
      hasFile: false,
      busy: false,
      byClient: false,
      hasClient: false,
      selectedProjectCount: 0,
    })).toEqual({ disabled: true, label: "Validar planilha" });
  });

  it("permite buscar os próprios dados sem cliente ou projeto", () => {
    expect(getReportImportActionState({
      source: "db",
      hasFile: false,
      busy: false,
      byClient: false,
      hasClient: false,
      selectedProjectCount: 0,
    }).disabled).toBe(false);
  });

  it("exige cliente e ao menos um projeto na busca por cliente", () => {
    const base = {
      source: "db" as const,
      hasFile: false,
      busy: false,
      byClient: true,
    };

    expect(getReportImportActionState({ ...base, hasClient: false, selectedProjectCount: 0 }).disabled).toBe(true);
    expect(getReportImportActionState({ ...base, hasClient: true, selectedProjectCount: 0 }).disabled).toBe(true);
    expect(getReportImportActionState({ ...base, hasClient: true, selectedProjectCount: 2 }).disabled).toBe(false);
  });

  it("bloqueia a ação e troca o rótulo durante o processamento", () => {
    expect(getReportImportActionState({
      source: "db",
      hasFile: false,
      busy: true,
      byClient: false,
      hasClient: false,
      selectedProjectCount: 0,
    })).toEqual({ disabled: true, label: "Buscando..." });
  });
});
