// Thin fetch wrapper around the backend. Auth is JWT bearer in a header
// (no cookies), per backend/README.md.

const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

const TOKEN_KEY = "spyke_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

type Body =
  | { json: unknown; form?: never; formData?: never }
  | { form: URLSearchParams; json?: never; formData?: never }
  | { formData: FormData; json?: never; form?: never }
  | { json?: never; form?: never; formData?: never };

type RequestOptions = {
  method?: string;
  auth?: boolean;
} & Body;

export async function apiFetch<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const init: RequestInit = { method: opts.method ?? "GET", headers };

  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.json);
  } else if (opts.form !== undefined) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    init.body = opts.form.toString();
  } else if (opts.formData !== undefined) {
    // Don't set Content-Type: the browser adds the multipart boundary itself.
    init.body = opts.formData;
  }

  if (opts.auth !== false) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?");
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const data = text ? safeJson(text) : null;

  if (!res.ok) {
    throw new ApiError(res.status, errorMessage(data, res.status));
  }

  return data as T;
}

// Turn a FastAPI error body into a readable message. `detail` is a string for
// plain errors (e.g. "Incorrect email or password") but an array of objects
// for validation errors ([{ loc, msg, type }, ...]); the latter used to render
// as "[object Object]".
function errorMessage(data: unknown, status: number): string {
  const detail =
    data && typeof data === "object" && "detail" in data
      ? (data as { detail: unknown }).detail
      : undefined;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (!item || typeof item !== "object" || !("msg" in item)) return "";
        const rec = item as { msg: unknown; loc?: unknown };
        const field = Array.isArray(rec.loc)
          ? rec.loc.filter((p) => p !== "body").join(".")
          : "";
        const msg = String(rec.msg);
        return field ? `${field}: ${msg}` : msg;
      })
      .filter((s) => s.length > 0);
    if (parts.length) return parts.join("; ");
  }

  return `Request failed (${status})`;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
