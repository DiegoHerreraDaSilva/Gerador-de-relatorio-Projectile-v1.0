export function sanitizeForFileName(text: string): string {
  return (text || "").replace(/[\\/:*?"<>|]/g, "-").trim();
}

export function computeDefaultFileName(
  monthLabel: string,
  packages: Array<{ projectCode: string; projectName: string }>
): string {
  const mesAno = (monthLabel || "").replace(/\//g, ".").trim();
  if (packages.length === 1) {
    const codigo = sanitizeForFileName(packages[0].projectCode);
    const projeto = sanitizeForFileName(packages[0].projectName);
    const prefixo = codigo ? `${codigo}_` : "";
    return `${prefixo}Relatório_Horas-${mesAno}-${projeto}`;
  }
  return `Relatórios_Horas-${mesAno}`;
}

export function computeDefaultFileNameFor(
  pkg: { projectCode: string; projectName: string },
  monthLabel: string
): string {
  const mesAno = (monthLabel || "").replace(/\//g, ".").trim();
  const codigo = sanitizeForFileName(pkg.projectCode);
  const projeto = sanitizeForFileName(pkg.projectName);
  const prefixo = codigo ? `${codigo}_` : "";
  return `${prefixo}Relatório_Horas-${mesAno}-${projeto}`;
}
