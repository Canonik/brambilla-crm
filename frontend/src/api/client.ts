import { clearToken, getToken } from "@/auth/token";

export const API_BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  category?: string;
  body?: unknown;

  constructor(message: string, status: number, opts: { category?: string; body?: unknown } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.category = opts.category;
    this.body = opts.body;
  }

  get isNetwork() {
    return this.status === 0;
  }

  get isNotFound() {
    return this.status === 404;
  }
}

export type QueryValue = string | number | boolean | string[] | null | undefined;

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /** Skip the Authorization header (only /health is public). */
  anonymous?: boolean;
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const base = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length === 0) continue;
      params.set(key, value.join(","));
    } else {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

function messageFromBody(body: unknown, status: number): { message: string; category?: string } {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    const message =
      (typeof b.message === "string" && b.message) ||
      (typeof b.error === "string" && b.error) ||
      (typeof b.detail === "string" && b.detail) ||
      null;
    const category = typeof b.category === "string" ? b.category : undefined;
    if (message) return { message, category };
  }
  if (typeof body === "string" && body.trim()) return { message: body.trim().slice(0, 300) };
  return { message: defaultMessage(status) };
}

function defaultMessage(status: number) {
  switch (status) {
    case 400:
      return "The CRM rejected this request.";
    case 401:
      return "Your access token was not accepted.";
    case 403:
      return "You are not allowed to do this.";
    case 404:
      return "This record does not exist or was removed.";
    case 409:
      return "This conflicts with an existing record.";
    case 429:
      return "Too many requests. Try again in a moment.";
    default:
      return status >= 500 ? "The CRM hit an internal error." : `Request failed (${status}).`;
  }
}

export async function request<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal, anonymous = false } = opts;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (!anonymous) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Could not reach the CRM. Check your connection and that the service is up.", 0);
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let parsed: unknown = undefined;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!res.ok) {
    if (res.status === 401 && !anonymous) {
      clearToken();
      window.dispatchEvent(new CustomEvent("crm:unauthorized"));
    }
    const { message, category } = messageFromBody(parsed, res.status);
    throw new ApiError(message, res.status, { category, body: parsed });
  }

  return parsed as T;
}
