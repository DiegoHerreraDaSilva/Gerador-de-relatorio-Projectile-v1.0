import type { ReportHeader, WorkPackage } from "../api/types";
import { drawGroupsChart } from "./chart";
import { computeDefaultFileNameFor } from "./fileName";

export type ReportFormatValue = "xlsx" | "pdf";

function chartPng(groups: WorkPackage["groups"], type: "bar" | "pie"): string {
  const canvas = document.createElement("canvas");
  drawGroupsChart(canvas, groups, type);
  return canvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, "");
}

/** Payload de `/generate` (formato `GeneratePayload` do backend) a partir do
 * relatório aberto no editor — usado pelo "Gerar" do rodapé e pelo "Aprovar"
 * da geração automática, que precisam produzir exatamente o mesmo arquivo pro
 * mesmo conteúdo. Os gráficos são desenhados aqui (canvas do navegador). */
export function buildGeneratePayload(packages: WorkPackage[], header: ReportHeader, formats: ReportFormatValue[]) {
  return {
    packages: packages.map((pkg) => ({
      header: {
        project_code: pkg.projectCode,
        project_name: pkg.projectName,
        location_date: header.locationDate,
        month_label: header.monthLabel,
        signer1_name: header.signer1Name,
        signer1_company: header.signer1Company,
        signer2_name: header.signer2Name,
        signer2_company: header.signer2Company,
      },
      groups: pkg.groups.map((g) => ({
        name: g.name,
        performance: g.performance,
        activities: g.activities.map((a) => ({ description: a.description, hours: a.hours })),
      })),
      file_name:
        packages.length > 1
          ? pkg.fileNameEdited
            ? pkg.fileName
            : computeDefaultFileNameFor(pkg, header.monthLabel)
          : undefined,
      chart_image_bar: pkg.chartBar ? chartPng(pkg.groups, "bar") : undefined,
      chart_image_pie: pkg.chartPie ? chartPng(pkg.groups, "pie") : undefined,
      pacote_scope: pkg.pacoteScope,
      language: pkg.language,
    })),
    formats,
    // relatório nunca mostra Bruto/Performance (o backend também ignora)
    include_performance: false,
  };
}
