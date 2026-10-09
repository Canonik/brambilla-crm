import { request, type RequestOptions } from "./client";
import { mockRequest } from "./mock/router";

// The single switch between the real backend and the in-browser demo backend.
// It is read once at build time; production builds leave it off, and when it
// is on the app shell shows a visible "Demo data" badge so nobody mistakes it.
export const USING_MOCKS = String(import.meta.env.VITE_USE_MOCKS ?? "").toLowerCase() === "true";

export function call<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  return USING_MOCKS ? mockRequest<T>(path, opts) : request<T>(path, opts);
}
