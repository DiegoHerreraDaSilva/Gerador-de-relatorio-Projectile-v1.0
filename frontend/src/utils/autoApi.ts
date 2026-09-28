/** `fetch` das rotas da geração automática e de "Minhas revisões": erro vira
 * `ApiError` com o `detail` do FastAPI (409 traz `current_version`, 400 da
 * aprovação traz `errors`). */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...(init?.headers ?? {}) } : init?.headers,
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* corpo sem JSON */
    }
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: unknown }).message)
          : `Erro ${res.status}`;
    throw new ApiError(res.status, detail, message);
  }
  return res.json() as Promise<T>;
}

/** Mensagens de uma recusa de aprovação (`{message, errors: [...]}`). */
export function errorList(err: unknown): string[] {
  if (err instanceof ApiError && err.detail && typeof err.detail === "object" && "errors" in err.detail) {
    const errors = (err.detail as { errors: unknown }).errors;
    if (Array.isArray(errors)) return errors.map(String);
  }
  return [err instanceof Error ? err.message : String(err)];
}
