// The API expects `Authorization: Bearer <token>` on every call. The token can
// be baked in at build time (VITE_CRM_TOKEN) or entered once in the UI, where
// it is kept in localStorage. A 401 from the API clears it and brings the
// sign-in screen back.

const STORAGE_KEY = "brambilla.crm.token";

type Listener = (token: string | null) => void;
const listeners = new Set<Listener>();

function readStorage(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

let current: string | null = (import.meta.env.VITE_CRM_TOKEN as string | undefined)?.trim() || readStorage();

export function getToken(): string | null {
  return current;
}

export function setToken(token: string | null) {
  const next = token?.trim() || null;
  current = next;
  try {
    if (next) window.localStorage.setItem(STORAGE_KEY, next);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable: keep it in memory only.
  }
  listeners.forEach((l) => l(next));
}

export function clearToken() {
  setToken(null);
}

export function subscribeToken(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function tokenFromEnv(): boolean {
  return Boolean((import.meta.env.VITE_CRM_TOKEN as string | undefined)?.trim());
}
