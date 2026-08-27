export function fmtNum(value: number): string {
  return (Math.round(value * 100) / 100).toString().replace(".", ",");
}

export function parseLocaleNumber(value: string | number): number {
  if (typeof value !== "string") return parseFloat(String(value));
  const trimmed = value.trim();
  if (trimmed.includes(",") && !trimmed.includes(".")) {
    return parseFloat(trimmed.replace(",", "."));
  }
  return parseFloat(trimmed);
}

export function parseExtraHoursInput(value: string): number | null {
  if (value === "") return null;
  const parsed = parseLocaleNumber(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}
