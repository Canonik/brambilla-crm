import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, request } from "./client";
import { clearToken, setToken } from "@/auth/token";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("request", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    setToken("secret-token");
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    clearToken();
  });

  it("sends the bearer token and JSON body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    const result = await request<{ ok: boolean }>("/crm/v3/objects/companies/search", {
      method: "POST",
      body: { limit: 10 },
    });
    expect(result).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/crm/v3/objects/companies/search");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer secret-token");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ limit: 10 });
  });

  it("serialises query parameters and drops empty ones", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ results: [] }));
    await request("/crm/v3/objects/deals", {
      query: { limit: 50, after: undefined, properties: ["a", "b"], archived: false },
    });
    const [url] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/crm/v3/objects/deals?limit=50&properties=a%2Cb&archived=false");
  });

  it("returns undefined on 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(request("/__reset", { method: "POST" })).resolves.toBeUndefined();
  });

  it("throws an ApiError with the server message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { status: "error", message: "Company with this VAT number already exists", category: "CONFLICT" },
        { status: 409 },
      ),
    );
    const err = (await request("/crm/v3/objects/companies", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.message).toBe("Company with this VAT number already exists");
    expect(err.category).toBe("CONFLICT");
  });

  it("clears the token and notifies on 401", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ message: "nope" }, { status: 401 }));
    const handler = vi.fn();
    window.addEventListener("crm:unauthorized", handler);
    const err = (await request("/crm/v3/objects/companies").catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(401);
    expect(handler).toHaveBeenCalled();
    window.removeEventListener("crm:unauthorized", handler);
  });

  it("wraps network failures", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await request("/health").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/reach the CRM/i);
  });
});
