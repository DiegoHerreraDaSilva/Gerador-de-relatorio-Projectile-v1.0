/** Texto pronto pra comparar em busca: sem acento e sem diferenciar maiúsculas. */
export function normalizeForSearch(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** `query` vazia casa tudo; senão, cada palavra dela precisa aparecer no texto (em qualquer ordem). */
export function matchesQuery(text: string, query: string): boolean {
  const words = normalizeForSearch(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = normalizeForSearch(text);
  return words.every((word) => haystack.includes(word));
}
