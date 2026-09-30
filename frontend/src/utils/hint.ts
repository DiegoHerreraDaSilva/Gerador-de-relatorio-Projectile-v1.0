/** Quantos valores o tooltip de um filtro de vários valores lista antes de resumir o resto. */
export const HINT_MAX_VALUES = 12;

/** Texto do tooltip instantâneo de um dropdown/filtro: "Rótulo: valor". Com vários valores
 * lista todos (o botão só mostra "3 selecionados"), cortando em `HINT_MAX_VALUES`. Sem
 * rótulo, só o valor; sem valor nenhum, o texto `empty` (ou só o rótulo). */
export function hintText(label: string | undefined, values: string[], empty?: string): string {
  const shown = values.filter((v) => v.trim());
  let value = "";
  if (shown.length > HINT_MAX_VALUES) {
    value = `${shown.slice(0, HINT_MAX_VALUES).join(", ")} e mais ${shown.length - HINT_MAX_VALUES}`;
  } else if (shown.length > 0) {
    value = shown.join(", ");
  } else if (empty) {
    value = empty;
  }
  if (label && value) return `${label}: ${value}`;
  return label || value;
}
