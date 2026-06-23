const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export type ApiError = { status: number; message: string };

export async function api<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string | { msg: string }[] };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d) => d.msg).join(", ");
    } catch {
      /* no body */
    }
    const err: ApiError = { status: res.status, message };
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
