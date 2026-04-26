export type ApiEnvelope<T> = {
  success: boolean;
  message?: string | null;
  data?: T;
  errors?: { code: string; message: string; detail?: string | null }[];
};

function getCorrelationId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `cid-${Date.now()}`;
}

export function getApiBaseUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!base) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured.");
  }
  return base;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<ApiEnvelope<T>> {
  const correlationId = getCorrelationId();
  const url = `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Correlation-ID": correlationId,
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`Non-JSON response (${res.status}) from ${url}`);
  }
  if (!res.ok) {
    const msg =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail?: unknown }).detail)
        : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return body as ApiEnvelope<T>;
}
