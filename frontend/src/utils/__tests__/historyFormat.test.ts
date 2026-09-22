import { describe, expect, it } from "vitest";
import {
  formatAuditAction,
  formatCreatedFrom,
  formatDateTime,
  formatDurationMs,
  formatFileSize,
  formatGenerationStatus,
  parseBackendTimestamp,
} from "../historyFormat";

describe("parseBackendTimestamp", () => {
  it("trata timestamp sem sufixo de fuso como UTC", () => {
    const date = parseBackendTimestamp("2026-09-22T14:12:13");
    expect(date.toISOString()).toBe("2026-09-22T14:12:13.000Z");
  });

  it("preserva timestamp que já vem com Z", () => {
    const date = parseBackendTimestamp("2026-09-22T14:12:13Z");
    expect(date.toISOString()).toBe("2026-09-22T14:12:13.000Z");
  });

  it("preserva timestamp que já vem com offset explícito", () => {
    const date = parseBackendTimestamp("2026-09-22T11:12:13-03:00");
    expect(date.toISOString()).toBe("2026-09-22T14:12:13.000Z");
  });
});

describe("formatDateTime", () => {
  it("devolve o texto original se a data for inválida", () => {
    expect(formatDateTime("não é uma data")).toBe("não é uma data");
  });
});

describe("formatFileSize", () => {
  it("bytes pequenos ficam em B", () => {
    expect(formatFileSize(500)).toBe("500 B");
  });

  it("na casa de KB usa 1 decimal abaixo de 10", () => {
    expect(formatFileSize(2048)).toBe("2.0 KB");
  });

  it("na casa de MB usa 0 decimais a partir de 10", () => {
    expect(formatFileSize(15 * 1024 * 1024)).toBe("15 MB");
  });

  it("valor negativo ou não finito vira travessão", () => {
    expect(formatFileSize(-1)).toBe("—");
    expect(formatFileSize(NaN)).toBe("—");
  });
});

describe("formatDurationMs", () => {
  it("abaixo de 1s mostra em ms", () => {
    expect(formatDurationMs(450)).toBe("450 ms");
  });

  it("1s ou mais mostra em segundos com 1 decimal", () => {
    expect(formatDurationMs(1500)).toBe("1.5 s");
  });

  it("null vira travessão", () => {
    expect(formatDurationMs(null)).toBe("—");
  });
});

describe("labels traduzidos", () => {
  it("formatAuditAction traduz ações conhecidas e devolve a original se não conhecer", () => {
    expect(formatAuditAction("report_created")).toBe("Relatório criado");
    expect(formatAuditAction("acao_desconhecida")).toBe("acao_desconhecida");
  });

  it("formatGenerationStatus traduz status conhecidos", () => {
    expect(formatGenerationStatus("success")).toBe("Sucesso");
    expect(formatGenerationStatus("failed")).toBe("Falha");
  });

  it("formatCreatedFrom traduz origem conhecida", () => {
    expect(formatCreatedFrom("generate_endpoint")).toBe("Gerar relatório");
    expect(formatCreatedFrom("send_report_endpoint")).toBe("Enviar por e-mail");
  });
});
